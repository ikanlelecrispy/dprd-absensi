import uuid
from datetime import datetime, time
from sqlalchemy import Time, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class AttendanceSchedule(Base):
    """
    Konfigurasi jadwal rentang waktu Presensi Masuk dan Presensi Pulang.

    Diubah secara dinamis oleh Admin melalui Dashboard Admin dan dibaca
    secara real-time menggunakan waktu server untuk menentukan sesi aktif.
    """
    __tablename__ = "attendance_schedules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Rentang waktu Presensi Masuk (default: 06:00 - 09:00)
    check_in_start: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(6, 0)
    )
    check_in_end: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(9, 0)
    )

    # Rentang waktu Presensi Pulang (default: 14:00 - 16:00)
    check_out_start: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(14, 0)
    )
    check_out_end: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(16, 0)
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
