from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_roles
from app.db.models import Document
from app.db.models import UserRole
from app.db.session import get_db
from app.schemas.document import TimelineBucket, TimelineResponse

router = APIRouter()


_SCALE_TO_TRUNC = {
    "year": "year",
    "quarter": "quarter",
    "month": "month",
    "day": "day",
}


@router.get("/timeline", response_model=TimelineResponse)
def get_timeline(
    scale: str = Query("month", pattern="^(year|quarter|month|day)$"),
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    _: CurrentUser = Depends(require_roles(UserRole.VIEWER, UserRole.REVIEWER, UserRole.EDITOR, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> TimelineResponse:
    trunc = _SCALE_TO_TRUNC[scale]
    bucket_col = func.date_trunc(trunc, Document.event_date)

    stmt = select(bucket_col.label("bucket"), func.count(Document.id).label("count")).where(Document.event_date.is_not(None))
    if from_date:
        stmt = stmt.where(Document.event_date >= from_date)
    if to_date:
        stmt = stmt.where(Document.event_date <= to_date)

    stmt = stmt.group_by(bucket_col).order_by(bucket_col.asc())

    rows = db.execute(stmt).all()
    buckets = [TimelineBucket(bucket=row.bucket.date().isoformat(), count=row.count) for row in rows]
    return TimelineResponse(scale=scale, buckets=buckets)
