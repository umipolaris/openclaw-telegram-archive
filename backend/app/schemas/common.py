from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class Pagination(BaseModel):
    page: int
    size: int
    total: int


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    dependencies: dict[str, str]
