from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.models import AuditLog, SavedFilter, User, UserRole
from app.db.session import get_db
from app.schemas.saved_filter import (
    SavedFilterCreateRequest,
    SavedFiltersListResponse,
    SavedFilterSummary,
    SavedFilterUpdateRequest,
)

router = APIRouter()


def _normalize_name(raw_name: str) -> str:
    name = raw_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    return name


def _to_saved_filter_summary(
    row: SavedFilter,
    username: str,
    current_user: CurrentUser,
) -> SavedFilterSummary:
    return SavedFilterSummary(
        id=row.id,
        user_id=row.user_id,
        username=username,
        name=row.name,
        filter_json=row.filter_json,
        is_shared=row.is_shared,
        is_owner=row.user_id == current_user.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/saved-filters", response_model=SavedFiltersListResponse)
def list_saved_filters(
    include_shared: bool = Query(True),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(
        require_roles(UserRole.VIEWER, UserRole.REVIEWER, UserRole.EDITOR, UserRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> SavedFiltersListResponse:
    visibility_expr = SavedFilter.user_id == current_user.id
    if include_shared:
        visibility_expr = or_(visibility_expr, SavedFilter.is_shared.is_(True))

    count_stmt = select(func.count(SavedFilter.id)).where(visibility_expr)
    total = db.execute(count_stmt).scalar_one()

    rows = db.execute(
        select(SavedFilter, User.username)
        .join(User, User.id == SavedFilter.user_id)
        .where(visibility_expr)
        .order_by(SavedFilter.updated_at.desc(), SavedFilter.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    return SavedFiltersListResponse(
        items=[_to_saved_filter_summary(saved_filter, username, current_user) for saved_filter, username in rows],
        page=page,
        size=size,
        total=total,
    )


@router.post("/saved-filters", response_model=SavedFilterSummary, status_code=status.HTTP_201_CREATED)
def create_saved_filter(
    req: SavedFilterCreateRequest,
    current_user: CurrentUser = Depends(
        require_roles(UserRole.VIEWER, UserRole.REVIEWER, UserRole.EDITOR, UserRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> SavedFilterSummary:
    name = _normalize_name(req.name)

    exists = db.execute(
        select(SavedFilter.id).where(
            SavedFilter.user_id == current_user.id,
            SavedFilter.name == name,
        )
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="saved filter name already exists")

    saved_filter = SavedFilter(
        user_id=current_user.id,
        name=name,
        filter_json=req.filter_json,
        is_shared=req.is_shared,
        created_by=current_user.id,
    )
    db.add(saved_filter)
    db.commit()
    db.refresh(saved_filter)

    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="SAVED_FILTER_CREATE",
            target_type="saved_filter",
            target_id=saved_filter.id,
            after_json={
                "name": saved_filter.name,
                "is_shared": saved_filter.is_shared,
                "filter_json": saved_filter.filter_json,
            },
        )
    )
    db.commit()

    return _to_saved_filter_summary(saved_filter, current_user.username, current_user)


@router.patch("/saved-filters/{saved_filter_id}", response_model=SavedFilterSummary)
def update_saved_filter(
    saved_filter_id: UUID,
    req: SavedFilterUpdateRequest,
    current_user: CurrentUser = Depends(
        require_roles(UserRole.VIEWER, UserRole.REVIEWER, UserRole.EDITOR, UserRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> SavedFilterSummary:
    row = db.execute(
        select(SavedFilter, User.username)
        .join(User, User.id == SavedFilter.user_id)
        .where(SavedFilter.id == saved_filter_id)
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="saved filter not found")

    saved_filter, username = row
    is_owner = saved_filter.user_id == current_user.id
    if not is_owner and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="forbidden")

    if req.name is None and req.filter_json is None and req.is_shared is None:
        raise HTTPException(status_code=400, detail="nothing to update")

    before_json = {
        "name": saved_filter.name,
        "is_shared": saved_filter.is_shared,
        "filter_json": saved_filter.filter_json,
    }

    if req.name is not None:
        normalized_name = _normalize_name(req.name)
        exists = db.execute(
            select(SavedFilter.id).where(
                SavedFilter.user_id == saved_filter.user_id,
                SavedFilter.name == normalized_name,
                SavedFilter.id != saved_filter.id,
            )
        ).scalar_one_or_none()
        if exists:
            raise HTTPException(status_code=409, detail="saved filter name already exists")
        saved_filter.name = normalized_name

    if req.filter_json is not None:
        saved_filter.filter_json = req.filter_json

    if req.is_shared is not None:
        saved_filter.is_shared = req.is_shared

    db.add(saved_filter)
    db.commit()
    db.refresh(saved_filter)

    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="SAVED_FILTER_UPDATE",
            target_type="saved_filter",
            target_id=saved_filter.id,
            before_json=before_json,
            after_json={
                "name": saved_filter.name,
                "is_shared": saved_filter.is_shared,
                "filter_json": saved_filter.filter_json,
            },
        )
    )
    db.commit()

    return _to_saved_filter_summary(saved_filter, username, current_user)


@router.delete("/saved-filters/{saved_filter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_filter(
    saved_filter_id: UUID,
    current_user: CurrentUser = Depends(
        require_roles(UserRole.VIEWER, UserRole.REVIEWER, UserRole.EDITOR, UserRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> None:
    saved_filter = db.get(SavedFilter, saved_filter_id)
    if not saved_filter:
        raise HTTPException(status_code=404, detail="saved filter not found")

    if saved_filter.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="forbidden")

    before_json = {
        "name": saved_filter.name,
        "is_shared": saved_filter.is_shared,
        "filter_json": saved_filter.filter_json,
        "user_id": str(saved_filter.user_id),
    }
    db.delete(saved_filter)
    db.commit()

    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="SAVED_FILTER_DELETE",
            target_type="saved_filter",
            target_id=saved_filter_id,
            before_json=before_json,
        )
    )
    db.commit()

