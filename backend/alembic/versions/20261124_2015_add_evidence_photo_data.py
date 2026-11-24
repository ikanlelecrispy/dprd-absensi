"""add_evidence_photo_data

Revision ID: b7c2d9e4a105
Revises: a4b91e6f3d02
Create Date: 2026-11-24 20:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c2d9e4a105"
down_revision: Union[str, None] = "a4b91e6f3d02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS evidence_photo_data BYTEA")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_attendance_evidence_photo_path "
        "ON attendance (evidence_photo_path) WHERE evidence_photo_path IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_attendance_evidence_photo_path")
    op.drop_column("attendance", "evidence_photo_data")
