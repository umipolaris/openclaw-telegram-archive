"""auth security fields

Revision ID: 0002_auth_security_fields
Revises: 0001_initial_schema
Create Date: 2026-02-26 12:55:00

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0002_auth_security_fields"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        alter table users
          add column if not exists failed_login_attempts int not null default 0,
          add column if not exists locked_until timestamptz,
          add column if not exists password_changed_at timestamptz
        """
    )
    op.execute("update users set failed_login_attempts = 0 where failed_login_attempts is null")


def downgrade() -> None:
    op.execute("alter table users drop column if exists password_changed_at")
    op.execute("alter table users drop column if exists locked_until")
    op.execute("alter table users drop column if exists failed_login_attempts")
