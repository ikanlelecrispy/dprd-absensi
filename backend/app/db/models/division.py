import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class Division(Base):
    """Divisi/bagian di DPRD — dinamis, bisa diedit admin."""
    __tablename__ = "divisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    supervisor_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationship
    participants: Mapped[list["Participant"]] = relationship(
        "Participant", back_populates="division"
    )
