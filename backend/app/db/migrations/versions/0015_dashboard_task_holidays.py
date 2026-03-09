"""add dashboard task holidays

Revision ID: 0015_task_holidays
Revises: 0014_task_list_range
Create Date: 2026-03-09 11:10:00

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0015_task_holidays"
down_revision = "0014_task_list_range"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        alter table dashboard_task_settings
        add column if not exists holidays_json jsonb not null default '{}'::jsonb
        """
    )
    op.execute(
        """
        update dashboard_task_settings
        set holidays_json = coalesce(holidays_json, '{}'::jsonb)
        """
    )


def downgrade() -> None:
    op.execute("alter table dashboard_task_settings drop column if exists holidays_json")
