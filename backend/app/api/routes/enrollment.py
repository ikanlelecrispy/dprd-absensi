import base64
import uuid
from datetime import datetime, date, timedelta
import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models.division import Division
from app.db.models.participant import Participant, ParticipantStatus
from app.db.models.face_embedding import FaceEmbedding
from app.db.models.participant_pin import ParticipantPin
import bcrypt
from app.core.security import security_service
from app.core.quality_checker import quality_checker
from app.core.face_processor import face_processor
from app.core.matcher import matcher
from app.schemas.enrollment import PhotoInput, EnrollmentPhotoReport

router = APIRouter(prefix="/enrollment", tags=["Enrollment"])


class AtomicEnrollmentRequest(BaseModel):
    intern_id: str = Field(..., description="Nomor Induk Magang")
    full_name: str = Field(..., description="Nama Lengkap")
    institution: str | None = None
    division_id: uuid.UUID
    pin: str | None = Field(default="123456", min_length=4, max_length=8, description="PIN cadangan mandiri peserta")
    biometric_consent: bool = True
    photos: list[PhotoInput] = Field(..., min_length=3, max_length=5)


@router.post("/register")
def register_and_enroll_atomic(data: AtomicEnrollmentRequest, db: Session = Depends(get_db)):
    """
    ENDPOINT PENDAFTARAN ATOMIK:
    Membuat peserta dan mendaftarkan biometrik wajah dalam 1 transaksi DB.
    Jika wajah tidak terdeteksi atau kualitas buruk, TIDAK ADA data peserta
    yang tersimpan di database, sehingga pendaftaran tidak menggantung.
    """
    if not data.biometric_consent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pendaftaran biometrik wajib menyetujui ketentuan UU PDP.",
        )

    # 1. Cek apakah ID sudah terdaftar dengan wajah aktif
    existing = db.query(Participant).filter(Participant.intern_id == data.intern_id).first()
    if existing:
        active_embs = [e for e in existing.embeddings if e.is_active]
        if active_embs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Peserta dengan ID '{data.intern_id}' sudah terdaftar dan aktif ({existing.full_name}).",
            )
        else:
            # Hapus data menggantung dari percobaan sebelumnya yang gagal
            db.delete(existing)
            db.commit()

    # 2. Cek Divisi
    div = db.query(Division).filter(Division.id == data.division_id).first()
    if not div:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Divisi yang dipilih tidak valid.")

    # 3. Proses & Validasi Foto Wajah Terlebih Dahulu
    extracted_embeddings = []
    metadata_list = []

    for idx, photo_item in enumerate(data.photos, 1):
        raw_b64 = photo_item.photo_b64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]

        try:
            img_bytes = base64.b64decode(raw_b64)
            nparr = np.frombuffer(img_bytes, np.uint8)
            frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Format citra pada foto {idx} ({photo_item.angle}) rusak / tidak valid.",
            )

        if frame_bgr is None or frame_bgr.size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Foto {idx} ({photo_item.angle}) kosong. Pastikan kamera menyala.",
            )

        # Proses ekstraksi wajah dengan quality check
        res = face_processor.process_frame(frame_bgr, enforce_quality=True)

        if not res.success or res.embedding is None:
            angle_label = {
                "front": "1. Hadap Depan",
                "left": "2. Toleh Kiri",
                "right": "3. Toleh Kanan",
            }.get(photo_item.angle, photo_item.angle)

            err_msg = res.error_message or "Wajah tidak terdeteksi dengan jelas."
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Validasi Gagal pada Foto [{angle_label}]: {err_msg}. Silakan ambil ulang foto tersebut.",
            )

        extracted_embeddings.append(res.embedding)
        metadata_list.append({
            "angle": photo_item.angle,
            "quality_score": min(1.0, res.quality.blur_score / 50.0),
        })

    # 4. Cek Pendaftaran Ganda (Duplicate Check)
    mean_candidate = np.mean(extracted_embeddings, axis=0)
    dup_check = matcher.check_duplicate(mean_candidate)
    if dup_check.is_duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ditolak: Wajah ini sangat identik ({dup_check.similarity_score:.2f}) dengan peserta terdaftar: {dup_check.existing_name}!",
        )

    # 5. SEMUA VALIDASI LOLOS -> Simpan Peserta dan Embedding dalam 1 Transaksi
    now = datetime.now()
    participant = Participant(
        intern_id=data.intern_id,
        full_name=data.full_name,
        institution=data.institution,
        division_id=div.id,
        internship_start=date.today(),
        internship_end=date.today() + timedelta(days=90),
        biometric_consent=True,
        consent_given_at=now,
        status=ParticipantStatus.ACTIVE,
    )
    db.add(participant)
    db.flush()

    for idx, emb_vec in enumerate(extracted_embeddings):
        meta = metadata_list[idx]
        encrypted_bytes = security_service.encrypt_embedding(emb_vec)

        db_row = FaceEmbedding(
            participant_id=participant.id,
            embedding_encrypted=encrypted_bytes,
            photo_angle=meta["angle"],
            quality_score=meta["quality_score"],
            is_active=True,
        )
        db.add(db_row)

    # Simpan PIN Cadangan Peserta (Self-Service)
    pin_val = data.pin or "123456"
    hashed_pin = bcrypt.hashpw(pin_val.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    pin_row = ParticipantPin(
        participant_id=participant.id,
        hashed_pin=hashed_pin,
        is_active=True,
    )
    db.add(pin_row)

    db.commit()

    # 6. Daftarkan langsung ke in-memory matcher
    matcher.register_participant(
        participant_id=participant.id,
        intern_id=participant.intern_id,
        full_name=participant.full_name,
        embedding_vectors=extracted_embeddings,
    )

    return {
        "success": True,
        "participant_id": str(participant.id),
        "intern_id": participant.intern_id,
        "full_name": participant.full_name,
        "enrolled_count": len(extracted_embeddings),
        "message": f"Pendaftaran berhasil! Wajah {participant.full_name} ({participant.intern_id}) telah terdaftar dan siap presensi.",
    }
