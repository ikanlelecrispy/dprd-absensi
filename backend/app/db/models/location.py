import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, Float, Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class Location(Base):
    """
    Titik lokasi lingkup presensi (Geofence).

    Admin dapat mengatur koordinat (latitude, longitude) serta radius jangkauan
    dalam meter melalui peta interaktif pada Dashboard Admin.
    Jika ada minimal satu lokasi dengan is_active=True, presensi hanya
    diizinkan di dalam radius salah satu lokasi aktif tersebut.
    """
    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)

    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    radius_meters: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
