from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Literal

from minio.commonconfig import CopySource
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.services.storage_minio import ensure_bucket, get_minio_client

BackupKind = Literal["db", "objects", "config"]
ConfigRestoreMode = Literal["preview", "apply"]

_DB_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_BACKUP_FORMAT = "archive-backup-v1"
_OBJECTS_LAYOUT = "object-keys-v1"
_PG_RESTORE_COMPAT_MSG = 'unrecognized configuration parameter "transaction_timeout"'


@dataclass
class BackupFileInfo:
    kind: BackupKind
    filename: str
    size_bytes: int
    created_at: datetime
    sha256: str | None


@dataclass
class ConfigRestorePreview:
    files: list[str]
    total_files: int


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _backup_root(settings: Settings) -> Path:
    root = Path(settings.backup_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _backup_dir(settings: Settings, kind: BackupKind) -> Path:
    out = _backup_root(settings) / kind
    out.mkdir(parents=True, exist_ok=True)
    return out


def _timestamp() -> str:
    return _now().strftime("%Y%m%d_%H%M%S")


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _write_meta(path: Path, values: dict[str, str]) -> None:
    lines = [f"{k}={v}" for k, v in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_meta(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        data[key.strip()] = value.strip()
    return data


def _cleanup_old_files(dir_path: Path, *, retention_days: int) -> None:
    if retention_days <= 0:
        return
    cutoff = _now().timestamp() - (retention_days * 86400)
    for path in dir_path.iterdir():
        if not path.is_file():
            continue
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)


def _resolve_backup_file(settings: Settings, kind: BackupKind, filename: str) -> Path:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError("invalid backup filename")
    path = _backup_dir(settings, kind) / filename
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"backup file not found: {filename}")
    return path


def _meta_path(path: Path) -> Path:
    return Path(f"{path}.meta")


def _load_backup_meta(path: Path) -> dict[str, str]:
    return _read_meta(_meta_path(path))


def _normalize_archive_member_path(name: str) -> str:
    normalized = PurePosixPath(name)
    if normalized.is_absolute():
        raise RuntimeError("unsafe archive path")
    parts = normalized.parts
    if not parts:
        raise RuntimeError("empty archive member path")
    if any(part in {"", ".", ".."} for part in parts):
        raise RuntimeError("unsafe archive path")
    return "/".join(parts)


def _verify_backup_checksum(path: Path, meta: dict[str, str], *, kind: BackupKind) -> None:
    expected = meta.get("sha256")
    if not expected:
        raise RuntimeError(f"{kind} backup metadata missing sha256")
    actual = _sha256(path)
    if actual != expected:
        raise RuntimeError(f"{kind} backup checksum mismatch for {path.name}")


def _is_supported_object_backup_meta(meta: dict[str, str]) -> bool:
    if meta.get("kind") != "objects":
        return False

    backup_format = meta.get("format")
    objects_layout = meta.get("objects_layout")
    if backup_format and backup_format != _BACKUP_FORMAT:
        return False
    if objects_layout and objects_layout != _OBJECTS_LAYOUT:
        return False

    # Legacy API backups had no explicit format/layout keys.
    if not backup_format and not objects_layout:
        if "storage_backend" not in meta and "bucket" not in meta:
            return False

    return True


def list_backup_files(settings: Settings, kind: BackupKind, *, limit: int = 200) -> list[BackupFileInfo]:
    target_dir = _backup_dir(settings, kind)
    patterns = {
        "db": "*.dump",
        "objects": "*.tar.gz",
        "config": "*.tar.gz",
    }
    pattern = patterns[kind]
    rows: list[BackupFileInfo] = []
    for path in sorted(target_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True):
        meta = _load_backup_meta(path)
        if kind == "objects" and not _is_supported_object_backup_meta(meta):
            continue
        rows.append(
            BackupFileInfo(
                kind=kind,
                filename=path.name,
                size_bytes=int(path.stat().st_size),
                created_at=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
                sha256=meta.get("sha256"),
            )
        )
        if len(rows) >= limit:
            break
    return rows


def get_backup_file_path(settings: Settings, kind: BackupKind, filename: str) -> Path:
    return _resolve_backup_file(settings, kind, filename)


def delete_backup_file(settings: Settings, kind: BackupKind, filename: str) -> tuple[str, bool]:
    target = _resolve_backup_file(settings, kind, filename)
    meta_path = Path(f"{target}.meta")
    target.unlink(missing_ok=False)
    meta_deleted = False
    if meta_path.exists():
        meta_path.unlink(missing_ok=True)
        meta_deleted = True
    return target.name, meta_deleted


def _db_connection_params(settings: Settings) -> dict[str, str]:
    parsed = make_url(settings.database_url)
    return {
        "host": parsed.host or "postgres",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "archive",
        "password": parsed.password or "",
        "database": parsed.database or "archive",
    }


def create_db_backup(settings: Settings) -> BackupFileInfo:
    output_dir = _backup_dir(settings, "db")
    ts = _timestamp()
    db_params = _db_connection_params(settings)
    out_file = output_dir / f"archive_{db_params['database']}_{ts}.dump"
    tmp_file = Path(f"{out_file}.tmp")
    meta_file = Path(f"{out_file}.meta")

    cmd = [
        "pg_dump",
        "-h",
        db_params["host"],
        "-p",
        db_params["port"],
        "-U",
        db_params["user"],
        "-d",
        db_params["database"],
        "-Fc",
        "--no-owner",
        "--no-privileges",
    ]
    env = dict(os.environ)
    env["PGPASSWORD"] = db_params["password"]
    try:
        with tmp_file.open("wb") as fp:
            subprocess.run(cmd, check=True, stdout=fp, stderr=subprocess.PIPE, env=env)
    except FileNotFoundError as exc:
        raise RuntimeError("pg_dump not found; install postgresql-client in api image") from exc
    except subprocess.CalledProcessError as exc:
        err_text = (exc.stderr or b"").decode("utf-8", errors="ignore")
        raise RuntimeError(f"pg_dump failed: {err_text.strip()}") from exc

    tmp_file.replace(out_file)
    digest = _sha256(out_file)
    _write_meta(
        meta_file,
        {
            "timestamp": ts,
            "kind": "db",
            "format": _BACKUP_FORMAT,
            "file": out_file.name,
            "sha256": digest,
            "database": db_params["database"],
        },
    )
    _cleanup_old_files(output_dir, retention_days=settings.backup_retention_days)
    return BackupFileInfo(
        kind="db",
        filename=out_file.name,
        size_bytes=int(out_file.stat().st_size),
        created_at=_now(),
        sha256=digest,
    )


def create_objects_backup(settings: Settings) -> BackupFileInfo:
    output_dir = _backup_dir(settings, "objects")
    ts = _timestamp()
    suffix = "minio" if settings.storage_backend == "minio" else "disk"
    out_file = output_dir / f"objects_{suffix}_{ts}.tar.gz"
    tmp_file = Path(f"{out_file}.tmp")
    meta_file = Path(f"{out_file}.meta")

    object_count = 0
    total_bytes = 0

    if settings.storage_backend == "minio":
        client = get_minio_client(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        ensure_bucket(client, settings.storage_bucket)
        with tarfile.open(tmp_file, "w:gz") as tar:
            for obj in client.list_objects(settings.storage_bucket, recursive=True):
                if not obj.object_name:
                    continue
                object_count += 1
                total_bytes += int(obj.size or 0)
                resp = client.get_object(settings.storage_bucket, obj.object_name)
                try:
                    info = tarfile.TarInfo(name=obj.object_name)
                    info.size = int(obj.size or 0)
                    info.mtime = int((obj.last_modified or _now()).timestamp())
                    info.mode = 0o644
                    tar.addfile(info, resp)
                finally:
                    resp.close()
                    resp.release_conn()
    else:
        root = Path(settings.storage_disk_root)
        if not root.exists():
            raise RuntimeError(f"disk storage root not found: {root}")
        with tarfile.open(tmp_file, "w:gz") as tar:
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                tar.add(path, arcname=rel, recursive=False)
                object_count += 1
                total_bytes += int(path.stat().st_size)

    tmp_file.replace(out_file)
    digest = _sha256(out_file)
    _write_meta(
        meta_file,
        {
            "timestamp": ts,
            "kind": "objects",
            "format": _BACKUP_FORMAT,
            "objects_layout": _OBJECTS_LAYOUT,
            "file": out_file.name,
            "sha256": digest,
            "storage_backend": settings.storage_backend,
            "bucket": settings.storage_bucket,
            "object_count": str(object_count),
            "total_bytes": str(total_bytes),
        },
    )
    _cleanup_old_files(output_dir, retention_days=settings.backup_retention_days)
    return BackupFileInfo(
        kind="objects",
        filename=out_file.name,
        size_bytes=int(out_file.stat().st_size),
        created_at=_now(),
        sha256=digest,
    )


def create_config_backup(settings: Settings) -> BackupFileInfo:
    output_dir = _backup_dir(settings, "config")
    ts = _timestamp()
    out_file = output_dir / f"config_{ts}.tar.gz"
    tmp_file = Path(f"{out_file}.tmp")
    meta_file = Path(f"{out_file}.meta")

    config_root = Path(settings.backup_config_root)
    sources: list[Path] = []
    for rel in ("env", "monitoring", "docker-compose.yml"):
        candidate = config_root / rel
        if candidate.exists():
            sources.append(candidate)
    if not sources:
        raise RuntimeError(f"no config files found under {config_root}")

    with tarfile.open(tmp_file, "w:gz") as tar:
        for src in sources:
            tar.add(src, arcname=src.relative_to(config_root).as_posix())

    tmp_file.replace(out_file)
    digest = _sha256(out_file)
    _write_meta(
        meta_file,
        {
            "timestamp": ts,
            "kind": "config",
            "format": _BACKUP_FORMAT,
            "file": out_file.name,
            "sha256": digest,
            "config_root": str(config_root),
        },
    )
    _cleanup_old_files(output_dir, retention_days=settings.backup_retention_days)
    return BackupFileInfo(
        kind="config",
        filename=out_file.name,
        size_bytes=int(out_file.stat().st_size),
        created_at=_now(),
        sha256=digest,
    )


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _cleanup_minio_prefix(client, bucket: str, prefix: str) -> None:  # type: ignore[no-untyped-def]
    for obj in client.list_objects(bucket, recursive=True, prefix=prefix):
        if obj.object_name:
            client.remove_object(bucket, obj.object_name)


def _remove_disk_objects_not_in_set(disk_root: Path, keep_rel_paths: set[str]) -> None:
    for path in disk_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(disk_root).as_posix()
        if rel not in keep_rel_paths:
            path.unlink(missing_ok=True)

    for path in sorted(disk_root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass


def _restore_db_compat_filtered_sql(
    *,
    source_path: Path,
    db_params: dict[str, str],
    target_db: str,
    env: dict[str, str],
) -> None:
    dump_cmd = [
        "pg_restore",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--file",
        "-",
        str(source_path),
    ]
    psql_cmd = [
        "psql",
        "-h",
        db_params["host"],
        "-p",
        db_params["port"],
        "-U",
        db_params["user"],
        "-d",
        target_db,
        "-v",
        "ON_ERROR_STOP=1",
    ]

    try:
        dump_proc = subprocess.Popen(dump_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        psql_proc = subprocess.Popen(psql_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    except FileNotFoundError as exc:
        raise RuntimeError("pg_restore/psql not found; install postgresql-client in api image") from exc

    assert dump_proc.stdout is not None
    assert dump_proc.stderr is not None
    assert psql_proc.stdin is not None
    assert psql_proc.stderr is not None

    broken_pipe = False
    for line in dump_proc.stdout:
        if line.strip().lower().startswith(b"set transaction_timeout"):
            continue
        try:
            psql_proc.stdin.write(line)
        except BrokenPipeError:
            broken_pipe = True
            break

    try:
        psql_proc.stdin.close()
    except Exception:  # noqa: BLE001
        pass
    dump_proc.stdout.close()

    dump_err = dump_proc.stderr.read()
    psql_err = psql_proc.stderr.read()
    dump_rc = dump_proc.wait()
    psql_rc = psql_proc.wait()

    if broken_pipe or dump_rc != 0 or psql_rc != 0:
        dump_msg = dump_err.decode("utf-8", errors="ignore").strip()
        psql_msg = psql_err.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(f"compat restore failed: pg_restore={dump_msg or dump_rc}, psql={psql_msg or psql_rc}")


def restore_db_backup(settings: Settings, *, filename: str, target_db: str) -> str:
    if not _DB_NAME_PATTERN.fullmatch(target_db):
        raise ValueError("target_db must contain only letters, numbers, '_' or '-'")

    db_params = _db_connection_params(settings)
    current_db = db_params["database"]
    if target_db == current_db:
        raise ValueError("web restore cannot target current running database; use a separate target_db")

    source_path = _resolve_backup_file(settings, "db", filename)
    meta = _load_backup_meta(source_path)
    _verify_backup_checksum(source_path, meta, kind="db")

    env = dict(os.environ)
    env["PGPASSWORD"] = db_params["password"]
    target_ident = _quote_ident(target_db)

    admin_cmd = [
        "psql",
        "-h",
        db_params["host"],
        "-p",
        db_params["port"],
        "-U",
        db_params["user"],
        "-d",
        "postgres",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='{target_db}' AND pid <> pg_backend_pid();",
        "-c",
        f"DROP DATABASE IF EXISTS {target_ident};",
        "-c",
        f"CREATE DATABASE {target_ident};",
    ]
    try:
        subprocess.run(admin_cmd, check=True, stderr=subprocess.PIPE, env=env)
    except FileNotFoundError as exc:
        raise RuntimeError("psql not found; install postgresql-client in api image") from exc
    except subprocess.CalledProcessError as exc:
        err_text = (exc.stderr or b"").decode("utf-8", errors="ignore")
        raise RuntimeError(f"failed to prepare target db: {err_text.strip()}") from exc

    restore_cmd = [
        "pg_restore",
        "-h",
        db_params["host"],
        "-p",
        db_params["port"],
        "-U",
        db_params["user"],
        "-d",
        target_db,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        str(source_path),
    ]
    try:
        subprocess.run(restore_cmd, check=True, stderr=subprocess.PIPE, env=env)
    except FileNotFoundError as exc:
        raise RuntimeError("pg_restore not found; install postgresql-client in api image") from exc
    except subprocess.CalledProcessError as exc:
        err_text = (exc.stderr or b"").decode("utf-8", errors="ignore")
        if _PG_RESTORE_COMPAT_MSG in err_text:
            _restore_db_compat_filtered_sql(
                source_path=source_path,
                db_params=db_params,
                target_db=target_db,
                env=env,
            )
        else:
            raise RuntimeError(f"pg_restore failed: {err_text.strip()}") from exc

    return target_db


def restore_objects_backup(settings: Settings, *, filename: str, replace_existing: bool) -> int:
    source_path = _resolve_backup_file(settings, "objects", filename)
    meta = _load_backup_meta(source_path)
    if not _is_supported_object_backup_meta(meta):
        raise RuntimeError("unsupported objects backup format; use backups created by /admin/backups/run/objects")
    _verify_backup_checksum(source_path, meta, kind="objects")

    if settings.storage_backend == "minio":
        client = get_minio_client(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        ensure_bucket(client, settings.storage_bucket)
        stage_prefix = f"__restore_staging__/{_timestamp()}_{os.getpid()}/"
        restored_keys: set[str] = set()
        restored = 0
        try:
            with tarfile.open(source_path, "r:gz") as tar:
                for member in tar.getmembers():
                    if not member.isfile():
                        continue
                    object_name = _normalize_archive_member_path(member.name)
                    stream = tar.extractfile(member)
                    if stream is None:
                        continue
                    stage_object_name = f"{stage_prefix}{object_name}"
                    client.put_object(
                        bucket_name=settings.storage_bucket,
                        object_name=stage_object_name,
                        data=stream,
                        length=member.size,
                        part_size=10 * 1024 * 1024,
                    )
                    restored_keys.add(object_name)

            for object_name in sorted(restored_keys):
                client.copy_object(
                    settings.storage_bucket,
                    object_name,
                    CopySource(settings.storage_bucket, f"{stage_prefix}{object_name}"),
                )
                restored += 1

            if replace_existing:
                for obj in client.list_objects(settings.storage_bucket, recursive=True):
                    if not obj.object_name:
                        continue
                    if obj.object_name.startswith(stage_prefix):
                        continue
                    if obj.object_name not in restored_keys:
                        client.remove_object(settings.storage_bucket, obj.object_name)
        finally:
            _cleanup_minio_prefix(client, settings.storage_bucket, stage_prefix)
        return restored

    disk_root = Path(settings.storage_disk_root)
    disk_root.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix="objects_restore_", dir=str(disk_root.parent)))
    restored_rel_paths: set[str] = set()
    restored = 0
    try:
        with tarfile.open(source_path, "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                rel = _normalize_archive_member_path(member.name)
                stage_path = (stage_dir / rel).resolve()
                if stage_dir.resolve() not in stage_path.parents:
                    raise RuntimeError("unsafe object archive path")
                stage_path.parent.mkdir(parents=True, exist_ok=True)
                stream = tar.extractfile(member)
                if stream is None:
                    continue
                with stage_path.open("wb") as out:
                    shutil.copyfileobj(stream, out, length=1024 * 1024)
                restored_rel_paths.add(rel)

        for rel in sorted(restored_rel_paths):
            src = stage_dir / rel
            dst = disk_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=dst.parent, delete=False) as tmp:
                with src.open("rb") as in_fp:
                    shutil.copyfileobj(in_fp, tmp, length=1024 * 1024)
                tmp_path = Path(tmp.name)
            tmp_path.replace(dst)
            restored += 1

        if replace_existing:
            _remove_disk_objects_not_in_set(disk_root, restored_rel_paths)
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
    return restored


def restore_config_backup(settings: Settings, *, filename: str, mode: ConfigRestoreMode) -> ConfigRestorePreview:
    source_path = _resolve_backup_file(settings, "config", filename)
    meta = _load_backup_meta(source_path)
    _verify_backup_checksum(source_path, meta, kind="config")

    config_root = Path(settings.backup_config_root).resolve()
    config_root.mkdir(parents=True, exist_ok=True)

    files: list[str] = []
    with tarfile.open(source_path, "r:gz") as tar:
        members = [m for m in tar.getmembers() if m.isfile()]
        files = [member.name for member in members]
        if mode == "apply":
            for member in members:
                target = (config_root / member.name).resolve()
                if config_root not in target.parents and target != config_root:
                    raise RuntimeError("unsafe config archive path")
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = tar.extractfile(member)
                if stream is None:
                    continue
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
                    shutil.copyfileobj(stream, tmp, length=1024 * 1024)
                    tmp_path = Path(tmp.name)
                tmp_path.replace(target)

    return ConfigRestorePreview(files=files[:200], total_files=len(files))
