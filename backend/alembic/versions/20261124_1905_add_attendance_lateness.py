"""add_attendance_lateness

Revision ID: a4b91e6f3d02
Revises: 7c3a92b1e410
Create Date: 2026-11-24 19:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a4b91e6f3d02"
down_revision: Union[str, None] = "7c3a92b1e410"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS is_late BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS late_minutes INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.drop_column("attendance", "late_minutes")
    op.drop_column("attendance", "is_late")
