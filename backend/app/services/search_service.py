from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Document


def fulltext_search(db: Session, query: str):
    stmt = (
        select(Document)
        .where(Document.search_vector.op("@@")(func.plainto_tsquery("simple", query)))
        .order_by(Document.event_date.desc().nulls_last())
    )
    return db.execute(stmt).scalars().all()
