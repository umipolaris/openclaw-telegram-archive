"""add dashboard task list range settings

Revision ID: 0014_task_list_range
Revises: 0013_backup_schedule_settings
Create Date: 2026-03-09 09:30:00

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0014_task_list_range"
down_revision = "0013_backup_schedule_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        alter table dashboard_task_settings
        add column if not exists list_range_past_days integer not null default 7
        """
    )
    op.execute(
        """
        alter table dashboard_task_settings
        add column if not exists list_range_future_months integer not null default 2
        """
    )
    op.execute(
        """
        update dashboard_task_settings
        set list_range_past_days = least(greatest(coalesce(list_range_past_days, 7), 0), 365),
            list_range_future_months = least(greatest(coalesce(list_range_future_months, 2), 0), 24)
        """
    )


def downgrade() -> None:
    op.execute("alter table dashboard_task_settings drop column if exists list_range_future_months")
    op.execute("alter table dashboard_task_settings drop column if exists list_range_past_days")
