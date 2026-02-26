from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models import UserRole


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthUser(BaseModel):
    id: str
    username: str
    role: UserRole


class LoginResponse(BaseModel):
    user: AuthUser
    logged_in_at: datetime


class LogoutResponse(BaseModel):
    status: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: UserRole = UserRole.VIEWER


class UserSummary(BaseModel):
    id: str
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class UsersListResponse(BaseModel):
    items: list[UserSummary]
    page: int = 1
    size: int = 50
    total: int = 0


class UpdateUserRequest(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class DeleteUserResponse(BaseModel):
    id: str
    username: str
    deleted: bool = True
    nullified_refs: dict[str, int] = Field(default_factory=dict)
