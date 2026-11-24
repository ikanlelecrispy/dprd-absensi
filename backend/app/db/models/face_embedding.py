import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Integer, func, LargeBinary, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy import REAL
from app.db.base import Base


class FaceEmbedding(Base):
    """
    Menyimpan embedding wajah peserta.
    
    DESAIN:
    - Satu peserta bisa punya beberapa embedding (dari foto berbeda sudut).
    - Matching menggunakan rata-rata embedding (mean pooling) yang di-load ke memory.
    - Embedding disimpan ter-enkripsi (Fernet) sebagai bytes, di-decode saat startup.
    - JANGAN simpan foto enrollment di sini — foto dihapus setelah embedding dihitung.
    """
    __tablename__ = "face_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Embedding ter-enkripsi (Fernet encrypted numpy array, 512 float32 = 2048 bytes)
    embedding_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # Metadata foto sumber embedding
    photo_angle: Mapped[str] = mapped_column(
        String(20), nullable=False
        # 'front', 'left', 'right', 'up', 'down'
    )
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0-1.0

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    enrolled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Relationship
    participant: Mapped["Participant"] = relationship("Participant", back_populates="embeddings")
