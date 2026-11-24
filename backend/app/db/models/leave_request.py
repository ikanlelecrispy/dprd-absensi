import uuid
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class LeaveRequest(Base):
    """Catatan izin harian peserta magang (1 baris per peserta per tanggal)."""

    __tablename__ = "leave_requests"
    __table_args__ = (
        UniqueConstraint("participant_id", "leave_date", name="uq_leave_requests_participant_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    leave_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    participant: Mapped["Participant"] = relationship(  # noqa: F821
        "Participant", back_populates="leave_requests"
    )
