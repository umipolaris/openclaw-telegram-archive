from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

BackupKind = Literal["db", "objects", "config"]
ConfigRestoreMode = Literal["preview", "apply"]


class BackupFileItem(BaseModel):
    kind: BackupKind
    filename: str
    size_bytes: int
    created_at: datetime
    sha256: str | None = None
    download_url: str


class BackupFilesResponse(BaseModel):
    kind: BackupKind
    items: list[BackupFileItem] = Field(default_factory=list)


class BackupRunResponse(BaseModel):
    kind: BackupKind
    filename: str
    size_bytes: int
    created_at: datetime
    sha256: str | None = None


class BackupRunAllResponse(BaseModel):
    items: list[BackupRunResponse] = Field(default_factory=list)


class BackupDeleteResponse(BaseModel):
    status: str
    kind: BackupKind
    filename: str
    meta_deleted: bool = False


class BackupRestoreDbRequest(BaseModel):
    filename: str
    target_db: str = "archive_restore"
    confirm: bool = False


class BackupRestoreObjectsRequest(BaseModel):
    filename: str
    replace_existing: bool = True
    confirm: bool = False


class BackupRestoreConfigRequest(BaseModel):
    filename: str
    mode: ConfigRestoreMode = "preview"
    confirm: bool = False


class BackupRestoreDbResponse(BaseModel):
    status: str
    filename: str
    target_db: str


class BackupRestoreObjectsResponse(BaseModel):
    status: str
    filename: str
    restored_count: int
    replace_existing: bool


class BackupRestoreConfigResponse(BaseModel):
    status: str
    filename: str
    mode: ConfigRestoreMode
    total_files: int
    files: list[str] = Field(default_factory=list)
