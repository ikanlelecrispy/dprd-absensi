import uuid
from datetime import datetime
from sqlalchemy import (
    String, DateTime, ForeignKey, Float, Boolean,
    Text, Integer, func, Enum as PgEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
import enum


class AttendanceType(str, enum.Enum):
    CHECK_IN = "check_in"
    CHECK_OUT = "check_out"


class AttendanceStatus(str, enum.Enum):
    VERIFIED = "verified"           # Berhasil via face recognition
    MANUAL = "manual"               # Diinput manual oleh admin
    FALLBACK_PIN = "fallback_pin"   # Via PIN fallback
    FALLBACK_QR = "fallback_qr"     # Via QR fallback
    FLAGGED = "flagged"             # Similarity mepet threshold, perlu review
    SYNCED_OFFLINE = "synced_offline"  # Dari antrian offline


class Attendance(Base):
    """
    Rekaman presensi peserta.

    CATATAN:
    - evidence_photo_path: path relatif, bukan URL lengkap.
    - similarity_score: null jika bukan via face recognition.
    - Foto bukti otomatis dihapus setelah EVIDENCE_RETENTION_DAYS.
    """
    __tablename__ = "attendance"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), nullable=False, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )

    attendance_type: Mapped[AttendanceType] = mapped_column(
        PgEnum(AttendanceType, name="attendance_type"), nullable=False
    )
    status: Mapped[AttendanceStatus] = mapped_column(
        PgEnum(AttendanceStatus, name="attendance_status"), nullable=False
    )

    # Waktu presensi (timezone-aware)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Face recognition metadata
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    liveness_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Lokasi GPS saat presensi
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Path relatif ke foto bukti (mis: "2024/01/15/uuid.jpg")
    evidence_photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Flag untuk review admin
    is_suspicious: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    suspicious_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Penanda keterlambatan (dihitung otomatis dari batas akhir Presensi Masuk)
    is_late: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    # Untuk manual attendance
    manual_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Untuk offline sync
    client_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
        # Waktu di tablet saat presensi offline (mungkin berbeda dari server)
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    participant: Mapped["Participant"] = relationship("Participant", back_populates="attendances")
    device: Mapped["Device | None"] = relationship("Device")
    location: Mapped["Location | None"] = relationship("Location")
    approver: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by])
