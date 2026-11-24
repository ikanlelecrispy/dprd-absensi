import uuid
from dataclasses import dataclass
import numpy as np
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import security_service
from app.db.models.participant import Participant, ParticipantStatus
from app.db.models.face_embedding import FaceEmbedding


@dataclass
class MatchResult:
    is_matched: bool
    participant_id: uuid.UUID | None
    intern_id: str | None
    full_name: str | None
    similarity_score: float
    is_suspicious: bool
    suspicious_reason: str | None


@dataclass
class DuplicateCheckResult:
    is_duplicate: bool
    existing_participant_id: uuid.UUID | None
    existing_name: str | None
    similarity_score: float


class FaceMatcher:
    """
    In-memory vector matching engine menggunakan Cosine Similarity.
    
    Karena DPRD Surakarta hanya memiliki ~30 peserta aktif, seluruh matriks
    embedding (30 × 512 float32 = ~60 KB) disimpan di RAM.
    Operasi dot-product matriks 30x512 dengan vektor query 512 selesai dalam <0.1ms di CPU.
    """
    def __init__(self):
        self.settings = get_settings()
        # Mapping participant_id -> normalized mean embedding (shape: (512,))
        self._index: dict[uuid.UUID, np.ndarray] = {}
        # Metadata cache untuk response instan
        self._meta: dict[uuid.UUID, dict] = {}

    def normalize(self, vec: np.ndarray) -> np.ndarray:
        """L2 Normalization vektor agar dot-product ekuivalen dengan Cosine Similarity."""
        norm = np.linalg.norm(vec)
        if norm == 0:
            return vec
        return vec / norm

    def load_from_db(self, db: Session) -> int:
        """
        Muat semua embedding peserta berstatus ACTIVE dari database ke memori.
        Didekripsi dari field embedding_encrypted.
        """
        active_participants = (
            db.query(Participant)
            .filter(Participant.status == ParticipantStatus.ACTIVE)
            .all()
        )

        new_index = {}
        new_meta = {}

        for p in active_participants:
            # Ambil semua embedding aktif milik peserta ini
            active_embs = [e for e in p.embeddings if e.is_active]
            if not active_embs:
                continue

            decrypted_vectors = []
            for emb_row in active_embs:
                try:
                    vec = security_service.decrypt_embedding(emb_row.embedding_encrypted)
                    norm_vec = self.normalize(vec)
                    decrypted_vectors.append(norm_vec)
                except Exception:
                    continue

            if decrypted_vectors:
                # Mean pooling: rata-rata seluruh sudut foto enrollment
                mean_vec = np.mean(decrypted_vectors, axis=0)
                mean_norm = self.normalize(mean_vec)

                new_index[p.id] = mean_norm
                new_meta[p.id] = {
                    "intern_id": p.intern_id,
                    "full_name": p.full_name,
                    "division_name": p.division.name if p.division else None,
                }

        self._index = new_index
        self._meta = new_meta
        return len(self._index)

    def register_participant(self, participant_id: uuid.UUID, intern_id: str, full_name: str, embedding_vectors: list[np.ndarray]):
        """Menambahkan atau memperbarui peserta langsung di in-memory cache."""
        if not embedding_vectors:
            return
        normalized = [self.normalize(v) for v in embedding_vectors]
        mean_vec = np.mean(normalized, axis=0)
        self._index[participant_id] = self.normalize(mean_vec)
        self._meta[participant_id] = {
            "intern_id": intern_id,
            "full_name": full_name,
        }

    def remove_participant(self, participant_id: uuid.UUID):
        """Hapus peserta dari in-memory cache saat magang dinonaktifkan/selesai."""
        self._index.pop(participant_id, None)
        self._meta.pop(participant_id, None)

    def match(self, query_embedding: np.ndarray, threshold: float | None = None) -> MatchResult:
        """
        Mencocokkan query_embedding dengan seluruh peserta terdaftar.
        """
        target_threshold = threshold if threshold is not None else self.settings.similarity_threshold

        if not self._index:
            return MatchResult(
                is_matched=False,
                participant_id=None,
                intern_id=None,
                full_name=None,
                similarity_score=0.0,
                is_suspicious=False,
                suspicious_reason="Tidak ada data peserta terdaftar dalam sistem.",
            )

        norm_query = self.normalize(query_embedding)

        participant_ids = list(self._index.keys())
        # Matriks shape (N, 512)
        matrix = np.array([self._index[pid] for pid in participant_ids], dtype=np.float32)

        # Dot product menghasilkan cosine similarity langsung karena vektor sudah ternormalisasi L2
        scores = np.dot(matrix, norm_query)
        best_idx = int(np.argmax(scores))
        best_score = float(scores[best_idx])
        best_id = participant_ids[best_idx]

        if best_score >= target_threshold:
            meta = self._meta.get(best_id, {})
            # Cek apakah skor mepet dengan threshold (zona abu-abu)
            margin = self.settings.suspicious_similarity_margin
            is_suspicious = target_threshold <= best_score < (target_threshold + margin)
            suspicious_reason = (
                f"Skor kemiripan ({best_score:.3f}) mendekati batas ambang ({target_threshold})."
                if is_suspicious else None
            )

            return MatchResult(
                is_matched=True,
                participant_id=best_id,
                intern_id=meta.get("intern_id"),
                full_name=meta.get("full_name"),
                similarity_score=best_score,
                is_suspicious=is_suspicious,
                suspicious_reason=suspicious_reason,
            )

        return MatchResult(
            is_matched=False,
            participant_id=None,
            intern_id=None,
            full_name=None,
            similarity_score=best_score,
            is_suspicious=False,
            suspicious_reason=None,
        )

    def check_duplicate(self, candidate_embedding: np.ndarray) -> DuplicateCheckResult:
        """
        Pencegahan pendaftaran ganda:
        Memeriksa apakah wajah calon peserta baru sudah sangat mirip (> duplicate_enrollment_threshold)
        dengan salah satu peserta yang sudah ada di database.
        """
        if not self._index:
            return DuplicateCheckResult(
                is_duplicate=False,
                existing_participant_id=None,
                existing_name=None,
                similarity_score=0.0,
            )

        norm_candidate = self.normalize(candidate_embedding)
        participant_ids = list(self._index.keys())
        matrix = np.array([self._index[pid] for pid in participant_ids], dtype=np.float32)

        scores = np.dot(matrix, norm_candidate)
        max_idx = int(np.argmax(scores))
        max_score = float(scores[max_idx])

        if max_score >= self.settings.duplicate_enrollment_threshold:
            dup_id = participant_ids[max_idx]
            meta = self._meta.get(dup_id, {})
            return DuplicateCheckResult(
                is_duplicate=True,
                existing_participant_id=dup_id,
                existing_name=meta.get("full_name"),
                similarity_score=max_score,
            )

        return DuplicateCheckResult(
            is_duplicate=False,
            existing_participant_id=None,
            existing_name=None,
            similarity_score=max_score,
        )


matcher = FaceMatcher()
