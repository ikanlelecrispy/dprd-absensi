import uuid
import secrets
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class Device(Base):
    """
    Kiosk tablet yang terdaftar.

    Device binding: setiap request presensi harus menyertakan device_token
    yang valid. Token disimpan di localStorage browser tablet.

    KEAMANAN: device_token adalah secret — hash-nya yang disimpan di DB.
    """
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # mis: "Kiosk Resepsionis"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Token yang di-hash (SHA-256), yang asli diberikan ke tablet sekali saja
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # IP yang diizinkan (opsional, untuk keamanan tambahan)
    allowed_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
