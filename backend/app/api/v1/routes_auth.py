from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user, require_roles
from app.core.security import hash_password, verify_password
from app.db.models import AuditLog, User, UserRole
from app.db.session import get_db
from app.schemas.auth import (
    AuthUser,
    CreateUserRequest,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    UpdateUserRequest,
    UserSummary,
    UsersListResponse,
)

router = APIRouter()


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


@router.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.execute(select(User).where(User.username == req.username)).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    request.session["user_id"] = str(user.id)
    request.session["username"] = user.username
    request.session["role"] = user.role.value

    user.last_login_at = _now()
    db.add(user)
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="AUTH_LOGIN",
            target_type="user",
            target_id=user.id,
            after_json={"username": user.username, "role": user.role.value},
        )
    )
    db.commit()

    return LoginResponse(
        user=AuthUser(id=str(user.id), username=user.username, role=user.role),
        logged_in_at=user.last_login_at,
    )


@router.post("/auth/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LogoutResponse:
    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="AUTH_LOGOUT",
            target_type="user",
            target_id=current_user.id,
            after_json={"username": current_user.username},
        )
    )
    db.commit()

    request.session.clear()
    return LogoutResponse(status="ok")


@router.get("/auth/me", response_model=AuthUser)
def me(current_user: CurrentUser = Depends(get_current_user)) -> AuthUser:
    return AuthUser(id=str(current_user.id), username=current_user.username, role=current_user.role)


@router.get(
    "/admin/users",
    response_model=UsersListResponse,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def list_users(
    q: str | None = Query(None),
    role: UserRole | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> UsersListResponse:
    stmt = select(User)
    count_stmt = select(func.count(User.id))

    if q:
        expr = User.username.ilike(f"%{q.strip()}%")
        stmt = stmt.where(expr)
        count_stmt = count_stmt.where(expr)
    if role is not None:
        expr = User.role == role
        stmt = stmt.where(expr)
        count_stmt = count_stmt.where(expr)
    if is_active is not None:
        expr = User.is_active == is_active
        stmt = stmt.where(expr)
        count_stmt = count_stmt.where(expr)

    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        stmt.order_by(User.created_at.asc()).offset((page - 1) * size).limit(size)
    ).scalars().all()

    return UsersListResponse(
        items=[
            UserSummary(
                id=str(u.id),
                username=u.username,
                role=u.role,
                is_active=u.is_active,
                created_at=u.created_at,
                last_login_at=u.last_login_at,
            )
            for u in rows
        ],
        page=page,
        size=size,
        total=total,
    )


@router.post(
    "/admin/users",
    response_model=UserSummary,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def create_user(
    req: CreateUserRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSummary:
    existing = db.execute(select(User).where(User.username == req.username)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="username already exists")

    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        role=req.role,
        is_active=True,
        created_by=current_user.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="USER_CREATE",
            target_type="user",
            target_id=user.id,
            after_json={"username": user.username, "role": user.role.value},
        )
    )
    db.commit()

    return UserSummary(
        id=str(user.id),
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.patch(
    "/admin/users/{user_id}",
    response_model=UserSummary,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def update_user(
    user_id: UUID,
    req: UpdateUserRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSummary:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")

    if req.role is None and req.is_active is None and req.password is None:
        raise HTTPException(status_code=400, detail="nothing to update")

    if req.is_active is False and str(user.id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="cannot deactivate current user")

    before = {
        "role": user.role.value,
        "is_active": user.is_active,
    }
    masked_fields: list[str] = []

    if req.role is not None:
        user.role = req.role
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.password is not None:
        user.password_hash = hash_password(req.password)
        masked_fields.append("password")

    db.add(user)
    db.commit()
    db.refresh(user)

    db.add(
        AuditLog(
            actor_user_id=current_user.id,
            action="USER_UPDATE",
            target_type="user",
            target_id=user.id,
            before_json=before,
            after_json={
                "role": user.role.value,
                "is_active": user.is_active,
                "password_updated": req.password is not None,
            },
            masked_fields=masked_fields,
        )
    )
    db.commit()

    return UserSummary(
        id=str(user.id),
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )
