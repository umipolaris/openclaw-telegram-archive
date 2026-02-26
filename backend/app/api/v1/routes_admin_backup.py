from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.auth import CurrentUser, require_roles
from app.core.config import get_settings
from app.db.models import AuditLog, UserRole
from app.db.session import get_db
from app.schemas.admin_backup import (
    BackupDeleteResponse,
    BackupFilesResponse,
    BackupRestoreConfigRequest,
    BackupRestoreConfigResponse,
    BackupRestoreDbRequest,
    BackupRestoreDbResponse,
    BackupRestoreObjectsRequest,
    BackupRestoreObjectsResponse,
    BackupRunAllResponse,
    BackupRunResponse,
)
from app.services.backup_service import (
    BackupKind,
    create_config_backup,
    create_db_backup,
    create_objects_backup,
    delete_backup_file,
    get_backup_file_path,
    list_backup_files,
    restore_config_backup,
    restore_db_backup,
    restore_objects_backup,
)
from sqlalchemy.orm import Session

router = APIRouter()


def _download_url(kind: BackupKind, filename: str) -> str:
    return f"/admin/backups/files/{kind}/{filename}/download"


def _create_backup_for_kind(kind: BackupKind) -> BackupRunResponse:
    settings = get_settings()
    if kind == "db":
        created = create_db_backup(settings)
    elif kind == "objects":
        created = create_objects_backup(settings)
    else:
        created = create_config_backup(settings)
    return BackupRunResponse(
        kind=created.kind,
        filename=created.filename,
        size_bytes=created.size_bytes,
        created_at=created.created_at,
        sha256=created.sha256,
    )


@router.get(
    "/admin/backups/files",
    response_model=BackupFilesResponse,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def get_backup_files(
    kind: BackupKind = Query("db"),
):
    settings = get_settings()
    try:
        rows = list_backup_files(settings, kind, limit=200)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return BackupFilesResponse(
        kind=kind,
        items=[
            {
                "kind": row.kind,
                "filename": row.filename,
                "size_bytes": row.size_bytes,
                "created_at": row.created_at,
                "sha256": row.sha256,
                "download_url": _download_url(row.kind, row.filename),
            }
            for row in rows
        ],
    )


@router.get(
    "/admin/backups/files/{kind}/{filename}/download",
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def download_backup_file(
    kind: BackupKind,
    filename: str,
):
    settings = get_settings()
    try:
        path = get_backup_file_path(settings, kind, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(path=str(path), media_type="application/octet-stream", filename=path.name)


@router.delete("/admin/backups/files/{kind}/{filename}", response_model=BackupDeleteResponse)
def remove_backup_file(
    kind: BackupKind,
    filename: str,
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> BackupDeleteResponse:
    settings = get_settings()
    try:
        deleted_name, meta_deleted = delete_backup_file(settings, kind, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = BackupDeleteResponse(
        status="deleted",
        kind=kind,
        filename=deleted_name,
        meta_deleted=meta_deleted,
    )
    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="BACKUP_DELETE_FILE",
            target_type="backup",
            after_json=result.model_dump(mode="json"),
        )
    )
    db.commit()
    return result


@router.post("/admin/backups/run/{kind}", response_model=BackupRunResponse)
def run_backup(
    kind: BackupKind,
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> BackupRunResponse:
    try:
        result = _create_backup_for_kind(kind)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="BACKUP_RUN",
            target_type="backup",
            after_json=result.model_dump(mode="json"),
        )
    )
    db.commit()
    return result


@router.post("/admin/backups/run-all", response_model=BackupRunAllResponse)
def run_backup_all(
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> BackupRunAllResponse:
    results: list[BackupRunResponse] = []
    for kind in ("db", "objects", "config"):
        try:
            results.append(_create_backup_for_kind(kind))  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"{kind} backup failed: {exc}") from exc

    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="BACKUP_RUN_ALL",
            target_type="backup",
            after_json={"items": [r.model_dump(mode="json") for r in results]},
        )
    )
    db.commit()
    return BackupRunAllResponse(items=results)


@router.post("/admin/backups/restore/db", response_model=BackupRestoreDbResponse)
def restore_backup_db(
    req: BackupRestoreDbRequest,
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> BackupRestoreDbResponse:
    if not req.confirm:
        raise HTTPException(status_code=400, detail="confirm=true required")
    try:
        restored_target = restore_db_backup(get_settings(), filename=req.filename, target_db=req.target_db)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    result = BackupRestoreDbResponse(status="ok", filename=req.filename, target_db=restored_target)
    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="BACKUP_RESTORE_DB",
            target_type="backup_restore",
            after_json=result.model_dump(mode="json"),
        )
    )
    db.commit()
    return result


@router.post("/admin/backups/restore/objects", response_model=BackupRestoreObjectsResponse)
def restore_backup_objects(
    req: BackupRestoreObjectsRequest,
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> BackupRestoreObjectsResponse:
    if not req.confirm:
        raise HTTPException(status_code=400, detail="confirm=true required")
    try:
        restored_count = restore_objects_backup(
            get_settings(),
            filename=req.filename,
            replace_existing=req.replace_existing,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    result = BackupRestoreObjectsResponse(
        status="ok",
        filename=req.filename,
        restored_count=restored_count,
        replace_existing=req.replace_existing,
    )
    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="BACKUP_RESTORE_OBJECTS",
            target_type="backup_restore",
            after_json=result.model_dump(mode="json"),
        )
    )
    db.commit()
    return result


@router.post("/admin/backups/restore/config", response_model=BackupRestoreConfigResponse)
def restore_backup_config(
    req: BackupRestoreConfigRequest,
    current_user: CurrentUser = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> BackupRestoreConfigResponse:
    if req.mode == "apply" and not req.confirm:
        raise HTTPException(status_code=400, detail="confirm=true required for apply mode")
    try:
        preview = restore_config_backup(get_settings(), filename=req.filename, mode=req.mode)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    result = BackupRestoreConfigResponse(
        status="ok",
        filename=req.filename,
        mode=req.mode,
        total_files=preview.total_files,
        files=preview.files,
    )
    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="BACKUP_RESTORE_CONFIG",
            target_type="backup_restore",
            after_json=result.model_dump(mode="json"),
        )
    )
    db.commit()
    return result
