from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import File


def find_by_checksum(db: Session, checksum_sha256: str) -> File | None:
    stmt = select(File).where(File.checksum_sha256 == checksum_sha256)
    return db.execute(stmt).scalar_one_or_none()
