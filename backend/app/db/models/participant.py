import uuid
from datetime import datetime, date
from sqlalchemy import String, Date, Boolean, DateTime, ForeignKey, Text, func, Enum as PgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
import enum


class ParticipantStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"      # Magang sudah selesai
    SUSPENDED = "suspended"    # Dinonaktifkan sementara


class Participant(Base):
    """Peserta magang DPRD Surakarta."""
    __tablename__ = "participants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # ID internal (mis: "MGG-2024-001")
    intern_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    institution: Mapped[str | None] = mapped_column(String(200), nullable=True)  # Universitas/sekolah asal

    division_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("divisions.id"), nullable=False
    )
    internship_start: Mapped[date] = mapped_column(Date, nullable=False)
    internship_end: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[ParticipantStatus] = mapped_column(
        PgEnum(ParticipantStatus, name="participant_status"),
        default=ParticipantStatus.ACTIVE,
        nullable=False,
    )

    # Consent untuk data biometrik (UU PDP)
    biometric_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Notes dari admin
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    # Siapa admin yang mendaftarkan
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Relationships
    division: Mapped["Division"] = relationship("Division", back_populates="participants")
    embeddings: Mapped[list["FaceEmbedding"]] = relationship(
        "FaceEmbedding", back_populates="participant", cascade="all, delete-orphan"
    )
    attendances: Mapped[list["Attendance"]] = relationship(
        "Attendance", back_populates="participant"
    )
    pin: Mapped["ParticipantPin | None"] = relationship(
        "ParticipantPin", back_populates="participant", uselist=False, cascade="all, delete-orphan"
    )
    leave_requests: Mapped[list["LeaveRequest"]] = relationship(
        "LeaveRequest", back_populates="participant", cascade="all, delete-orphan"
    )
