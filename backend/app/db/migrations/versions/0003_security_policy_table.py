"""security policy table

Revision ID: 0003_security_policy_table
Revises: 0002_auth_security_fields
Create Date: 2026-02-26 13:40:00

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0003_security_policy_table"
down_revision = "0002_auth_security_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists security_policies (
          scope varchar(32) primary key,
          password_min_length int not null default 10,
          require_uppercase boolean not null default true,
          require_lowercase boolean not null default true,
          require_digit boolean not null default true,
          require_special boolean not null default true,
          max_failed_attempts int not null default 5,
          lockout_seconds int not null default 900,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          created_by uuid references users(id)
        )
        """
    )


def downgrade() -> None:
    op.execute("drop table if exists security_policies")
