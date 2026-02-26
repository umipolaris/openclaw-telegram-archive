from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SavedFilterSummary(BaseModel):
    id: UUID
    user_id: UUID
    username: str
    name: str
    filter_json: dict[str, Any] = Field(default_factory=dict)
    is_shared: bool
    is_owner: bool
    created_at: datetime
    updated_at: datetime


class SavedFiltersListResponse(BaseModel):
    items: list[SavedFilterSummary]
    page: int
    size: int
    total: int


class SavedFilterCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    filter_json: dict[str, Any] = Field(default_factory=dict)
    is_shared: bool = False


class SavedFilterUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    filter_json: dict[str, Any] | None = None
    is_shared: bool | None = None
