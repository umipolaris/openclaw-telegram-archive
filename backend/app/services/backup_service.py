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
from typing import Literal

from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.services.storage_minio import ensure_bucket, get_minio_client

BackupKind = Literal["db", "objects", "config"]
ConfigRestoreMode = Literal["preview", "apply"]

_DB_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


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


def list_backup_files(settings: Settings, kind: BackupKind, *, limit: int = 200) -> list[BackupFileInfo]:
    target_dir = _backup_dir(settings, kind)
    patterns = {
        "db": "*.dump",
        "objects": "*.tar.gz",
        "config": "*.tar.gz",
    }
    pattern = patterns[kind]
    rows: list[BackupFileInfo] = []
    for path in sorted(target_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        meta = _read_meta(Path(f"{path}.meta"))
        rows.append(
            BackupFileInfo(
                kind=kind,
                filename=path.name,
                size_bytes=int(path.stat().st_size),
                created_at=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
                sha256=meta.get("sha256"),
            )
        )
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


def restore_db_backup(settings: Settings, *, filename: str, target_db: str) -> str:
    if not _DB_NAME_PATTERN.fullmatch(target_db):
        raise ValueError("target_db must contain only letters, numbers, '_' or '-'")

    db_params = _db_connection_params(settings)
    current_db = db_params["database"]
    if target_db == current_db:
        raise ValueError("web restore cannot target current running database; use a separate target_db")

    source_path = _resolve_backup_file(settings, "db", filename)
    env = dict(os.environ)
    env["PGPASSWORD"] = db_params["password"]

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
        f"DROP DATABASE IF EXISTS {target_db};",
        "-c",
        f"CREATE DATABASE {target_db};",
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
        raise RuntimeError(f"pg_restore failed: {err_text.strip()}") from exc

    return target_db


def restore_objects_backup(settings: Settings, *, filename: str, replace_existing: bool) -> int:
    source_path = _resolve_backup_file(settings, "objects", filename)

    if settings.storage_backend == "minio":
        client = get_minio_client(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        ensure_bucket(client, settings.storage_bucket)
        if replace_existing:
            for obj in client.list_objects(settings.storage_bucket, recursive=True):
                client.remove_object(settings.storage_bucket, obj.object_name)

        restored = 0
        with tarfile.open(source_path, "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                stream = tar.extractfile(member)
                if stream is None:
                    continue
                client.put_object(
                    bucket_name=settings.storage_bucket,
                    object_name=member.name,
                    data=stream,
                    length=member.size,
                    part_size=10 * 1024 * 1024,
                )
                restored += 1
        return restored

    disk_root = Path(settings.storage_disk_root)
    disk_root.mkdir(parents=True, exist_ok=True)
    if replace_existing:
        for child in disk_root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)

    restored = 0
    with tarfile.open(source_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            target_path = (disk_root / member.name).resolve()
            if disk_root.resolve() not in target_path.parents and target_path != disk_root.resolve():
                raise RuntimeError("unsafe object archive path")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            stream = tar.extractfile(member)
            if stream is None:
                continue
            with target_path.open("wb") as out:
                shutil.copyfileobj(stream, out, length=1024 * 1024)
            restored += 1
    return restored


def restore_config_backup(settings: Settings, *, filename: str, mode: ConfigRestoreMode) -> ConfigRestorePreview:
    source_path = _resolve_backup_file(settings, "config", filename)
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
