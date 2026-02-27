"""add pinned fields to documents

Revision ID: 0004_document_pinned_fields
Revises: 0003_security_policy_table
Create Date: 2026-02-26 18:30:00

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0004_document_pinned_fields"
down_revision = "0003_security_policy_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table documents add column if not exists is_pinned boolean not null default false")
    op.execute("alter table documents add column if not exists pinned_at timestamptz")
    op.execute(
        """
        create index if not exists idx_documents_pinned_category_ingested
        on documents (is_pinned, category_id, pinned_at desc nulls last, ingested_at desc)
        """
    )


def downgrade() -> None:
    op.execute("drop index if exists idx_documents_pinned_category_ingested")
    op.execute("alter table documents drop column if exists pinned_at")
    op.execute("alter table documents drop column if exists is_pinned")
