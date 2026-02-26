from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import User, UserRole
from app.db.session import get_db


@dataclass
class CurrentUser:
    id: UUID
    username: str
    role: UserRole


def get_current_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    session = request.session
    user_id = session.get("user_id") if isinstance(session, dict) else None
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")

    user = db.get(User, UUID(str(user_id)))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session")

    return CurrentUser(id=user.id, username=user.username, role=user.role)


def require_roles(*allowed_roles: UserRole):
    def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return current_user

    return dependency
