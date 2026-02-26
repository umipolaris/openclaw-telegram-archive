from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Category, DocumentTag, Tag


def normalize_slug(text: str) -> str:
    return text.strip().lower().replace(" ", "-")


def upsert_category(db: Session, category_name: str | None) -> Category | None:
    if not category_name:
        return None

    normalized = category_name.strip()
    if not normalized:
        return None

    slug = normalize_slug(normalized)
    existing = db.execute(select(Category).where(Category.slug == slug)).scalar_one_or_none()
    if existing:
        return existing

    category = Category(name=normalized, slug=slug, is_active=True)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        category = db.execute(select(Category).where(Category.slug == slug)).scalar_one_or_none()

    if category:
        db.refresh(category)
    return category


def upsert_tags(db: Session, names: list[str]) -> list[Tag]:
    tags: list[Tag] = []

    for raw in names:
        name = raw.strip()
        if not name:
            continue

        slug = normalize_slug(name)
        tag = db.execute(select(Tag).where(Tag.slug == slug)).scalar_one_or_none()
        if not tag:
            tag = Tag(name=name, slug=slug)
            db.add(tag)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                tag = db.execute(select(Tag).where(Tag.slug == slug)).scalar_one_or_none()

        if tag:
            tags.append(tag)

    return tags


def replace_document_tags(db: Session, document_id, tag_names: list[str]) -> list[str]:
    db.query(DocumentTag).filter(DocumentTag.document_id == document_id).delete(synchronize_session=False)

    tags = upsert_tags(db, tag_names)
    for tag in tags:
        db.add(DocumentTag(document_id=document_id, tag_id=tag.id))

    db.commit()
    return [t.name for t in tags]
