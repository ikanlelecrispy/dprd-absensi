import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base


class AuditLog(Base):
    """
    Audit trail untuk semua aksi sensitif.
    Immutable — tidak ada UPDATE/DELETE di tabel ini.
    """
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 'user' atau 'system' atau 'device'
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # UUID as string
    actor_name: Mapped[str | None] = mapped_column(String(150), nullable=True)

    action: Mapped[str] = mapped_column(String(100), nullable=False)
    # Contoh: 'participant.create', 'attendance.manual', 'embedding.delete'

    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Detail perubahan (before/after atau metadata tambahan)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
