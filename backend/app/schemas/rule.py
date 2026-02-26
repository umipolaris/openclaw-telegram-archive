from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RuleTestSample(BaseModel):
    caption: str | None = None
    title: str | None = None
    description: str | None = None
    filename: str | None = None
    body_text: str | None = None


class RuleTestRequest(BaseModel):
    rule_version_id: UUID
    sample: RuleTestSample


class RuleTestResponse(BaseModel):
    category: str
    tags: list[str]
    event_date: date | None
    review_needed: bool


class BackfillFilter(BaseModel):
    category_id: UUID | None = None
    from_date: date | None = Field(default=None, alias="from")
    to_date: date | None = Field(default=None, alias="to")
    review_only: bool = False


class BackfillRequest(BaseModel):
    rule_version_id: UUID
    filter: BackfillFilter | None = None
    batch_size: int = 500


class BackfillAcceptedResponse(BaseModel):
    job_id: str
    status: str


class RulesetCreateRequest(BaseModel):
    name: str
    description: str | None = None


class RulesetUpdateRequest(BaseModel):
    description: str | None = None
    is_active: bool | None = None


class RuleVersionCreateRequest(BaseModel):
    rules_json: dict


class RuleVersionActivateResponse(BaseModel):
    rule_version_id: UUID
    ruleset_id: UUID
    published_at: datetime
    is_active: bool


class RuleVersionSummary(BaseModel):
    id: UUID
    ruleset_id: UUID
    version_no: int
    is_active: bool
    published_at: datetime | None
    created_at: datetime


class RulesetSummary(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_active: bool
    current_version_id: UUID | None
    created_at: datetime
    updated_at: datetime


class RulesetDetailResponse(BaseModel):
    ruleset: RulesetSummary
    versions: list[RuleVersionSummary]


class RulesetsListResponse(BaseModel):
    items: list[RulesetSummary]


class RuleVersionDetailResponse(BaseModel):
    id: UUID
    ruleset_id: UUID
    version_no: int
    rules_json: dict
    checksum_sha256: str
    is_active: bool
    published_at: datetime | None
    created_at: datetime


class RulesetExportResponse(BaseModel):
    ruleset: RulesetSummary
    versions: list[RuleVersionDetailResponse]


class RulesImportRequest(BaseModel):
    ruleset_name: str
    description: str | None = None
    versions: list[dict]
    activate_latest: bool = True


class RulesImportResponse(BaseModel):
    ruleset_id: UUID
    imported_versions: int
    activated_version_id: UUID | None = None


class RuleSimulationRequest(BaseModel):
    rule_version_id: UUID
    baseline_rule_version_id: UUID | None = None
    limit: int = 200
    filter: BackfillFilter | None = None


class RuleSimulationSample(BaseModel):
    document_id: UUID
    title: str
    current_category: str | None = None
    predicted_category: str
    current_event_date: date | None = None
    predicted_event_date: date | None = None
    current_tags: list[str] = Field(default_factory=list)
    predicted_tags: list[str] = Field(default_factory=list)
    changed: bool
    changed_fields: list[str] = Field(default_factory=list)


class RuleSimulationResponse(BaseModel):
    rule_version_id: UUID
    baseline_rule_version_id: UUID | None = None
    scanned: int
    changed: int
    unchanged: int
    samples: list[RuleSimulationSample] = Field(default_factory=list)
    generated_at: datetime


class RuleConflictItem(BaseModel):
    source_field: str
    keyword: str
    categories: list[str] = Field(default_factory=list)


class RuleConflictResponse(BaseModel):
    rule_version_id: UUID
    total_conflicts: int
    conflicts: list[RuleConflictItem] = Field(default_factory=list)
