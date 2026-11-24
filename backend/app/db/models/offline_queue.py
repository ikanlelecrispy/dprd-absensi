import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, Text, func, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base


class OfflineQueueItem(Base):
    """
    Antrian presensi yang dikumpulkan saat tablet offline.

    ALUR:
    1. Tablet detect koneksi putus → simpan ke IndexedDB lokal
    2. Koneksi pulih → tablet kirim batch ke POST /api/attendance/sync
    3. Backend proses satu per satu, simpan ke sini dulu
    4. Background task proses antrian dan buat Attendance records
    5. Tablet mendapat konfirmasi → hapus dari IndexedDB

    IDEMPOTENCY:
    - client_uuid di-generate tablet menggunakan UUID v4
    - Jika tablet retry karena timeout, server cek client_uuid dulu
    - Jika sudah ada: kembalikan status existing tanpa proses ulang
    """
    __tablename__ = "offline_queue"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # UUID yang di-generate tablet — untuk idempotency
    client_uuid: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Payload JSON dari tablet (sama struktur dengan request presensi normal)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Waktu di tablet saat data dibuat (mungkin berbeda dari server saat disync)
    client_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
