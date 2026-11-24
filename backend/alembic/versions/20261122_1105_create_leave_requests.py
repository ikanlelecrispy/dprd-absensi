"""create_leave_requests

Revision ID: 7c3a92b1e410
Revises: 1cbd3c076b34
Create Date: 2026-11-22 11:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7c3a92b1e410"
down_revision: Union[str, None] = "1cbd3c076b34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leave_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("participant_id", sa.UUID(), nullable=False),
        sa.Column("leave_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name=op.f("fk_leave_requests_participant_id_participants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_requests")),
        sa.UniqueConstraint(
            "participant_id",
            "leave_date",
            name="uq_leave_requests_participant_date",
        ),
    )
    op.create_index(
        op.f("ix_leave_requests_participant_id"),
        "leave_requests",
        ["participant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_leave_requests_leave_date"),
        "leave_requests",
        ["leave_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_leave_requests_leave_date"), table_name="leave_requests")
    op.drop_index(op.f("ix_leave_requests_participant_id"), table_name="leave_requests")
    op.drop_table("leave_requests")
