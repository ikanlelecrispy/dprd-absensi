import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, Integer, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class ParticipantPin(Base):
    """
    PIN fallback untuk presensi jika face recognition gagal 5x berturut-turut.

    KEAMANAN:
    - PIN 6 digit di-hash dengan bcrypt (cost factor 12)
    - BUKAN SHA/MD5 — PIN pendek (6 digit) rentan terhadap rainbow table
    - Rate limiting: setelah 3x salah → locked_until (cooldown 10 menit)
    - Admin yang set PIN awal, lalu peserta bisa ganti via kiosk dengan verifikasi

    ALUR PENGGUNAAN:
    1. Face recognition gagal 5x → kiosk tampilkan opsi PIN
    2. Peserta masukkan intern_id + PIN 6 digit
    3. Backend cek PIN (dengan rate limiting)
    4. Catat attendance dengan status 'fallback_pin'
    5. Reset fail counter jika berhasil
    """
    __tablename__ = "participant_pins"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # bcrypt hash dari PIN 6 digit
    hashed_pin: Mapped[str] = mapped_column(String(255), nullable=False)

    # Rate limiting
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    participant: Mapped["Participant"] = relationship(  # noqa: F821
        "Participant", back_populates="pin"
    )
