from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MindMapCategoryNode(BaseModel):
    category: str
    document_count: int
    latest_event_date: date | None = None


class MindMapTagNode(BaseModel):
    tag: str
    document_count: int
    latest_event_date: date | None = None


class MindMapDocumentNode(BaseModel):
    id: UUID
    title: str
    category: str
    event_date: date | None = None
    updated_at: datetime
    file_count: int = 0
    tags: list[str] = Field(default_factory=list)


class MindMapTreeResponse(BaseModel):
    generated_at: datetime
    selected_category: str | None = None
    selected_tag: str | None = None
    categories: list[MindMapCategoryNode] = Field(default_factory=list)
    tags: list[MindMapTagNode] = Field(default_factory=list)
    documents: list[MindMapDocumentNode] = Field(default_factory=list)
    page: int = 1
    size: int = 20
    total_documents: int = 0

