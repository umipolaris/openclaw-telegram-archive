"""add document comments table

Revision ID: 0005_document_comments
Revises: 0004_document_pinned_fields
Create Date: 2026-02-27 23:30:00

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0005_document_comments"
down_revision = "0004_document_pinned_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists document_comments (
          id uuid primary key default gen_random_uuid(),
          document_id uuid not null references documents(id) on delete cascade,
          content text not null,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id)
        )
        """
    )
    op.execute(
        """
        create index if not exists idx_document_comments_document_created
        on document_comments (document_id, created_at desc)
        """
    )


def downgrade() -> None:
    op.execute("drop index if exists idx_document_comments_document_created")
    op.execute("drop table if exists document_comments")
