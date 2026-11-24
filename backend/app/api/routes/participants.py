import uuid
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin
from app.db.session import get_db
from app.db.models.division import Division
from app.db.models.participant import Participant, ParticipantStatus
from app.db.models.face_embedding import FaceEmbedding
from app.core.matcher import matcher
from app.schemas.participant import ParticipantCreate, ParticipantUpdate, ParticipantResponse

router = APIRouter(
    prefix="/participants",
    tags=["Participants"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("", response_model=list[ParticipantResponse])
def get_participants(
    status_filter: ParticipantStatus | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Participant)
    if status_filter:
        query = query.filter(Participant.status == status_filter)
    participants = query.order_by(Participant.created_at.desc()).all()

    result = []
    for p in participants:
        resp = ParticipantResponse.model_validate(p)
        resp.active_embeddings_count = len([e for e in p.embeddings if e.is_active])
        result.append(resp)
    return result


@router.post("", response_model=ParticipantResponse, status_code=status.HTTP_201_CREATED)
def create_participant(data: ParticipantCreate, db: Session = Depends(get_db)):
    # Cek ID unik
    existing = db.query(Participant).filter(Participant.intern_id == data.intern_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Peserta dengan ID '{data.intern_id}' sudah terdaftar ({existing.full_name}).",
        )

    # Cek divisi ada
    div = db.query(Division).filter(Division.id == data.division_id).first()
    if not div:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Divisi tidak ditemukan.",
        )

    participant = Participant(
        intern_id=data.intern_id,
        full_name=data.full_name,
        email=data.email,
        phone=data.phone,
        institution=data.institution,
        division_id=data.division_id,
        internship_start=data.internship_start,
        internship_end=data.internship_end,
        biometric_consent=data.biometric_consent,
        consent_given_at=datetime.now() if data.biometric_consent else None,
        notes=data.notes,
        status=ParticipantStatus.ACTIVE,
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)

    resp = ParticipantResponse.model_validate(participant)
    resp.active_embeddings_count = 0
    return resp


@router.delete("/{participant_id}", status_code=status.HTTP_200_OK)
def deactivate_and_purge_participant(participant_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Kepatuhan UU PDP:
    1. Status peserta diubah ke INACTIVE.
    2. Semua FaceEmbedding di-hard delete dari DB.
    3. Peserta dihapus dari in-memory matcher RAM.
    """
    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if not participant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Peserta tidak ditemukan.")

    participant.status = ParticipantStatus.INACTIVE
    participant.updated_at = datetime.now()

    # Hard delete data biometrik
    deleted_count = (
        db.query(FaceEmbedding)
        .filter(FaceEmbedding.participant_id == participant_id)
        .delete()
    )

    db.commit()

    # Hapus dari memori matcher
    matcher.remove_participant(participant_id)

    return {
        "success": True,
        "message": f"Peserta '{participant.full_name}' telah dinonaktifkan.",
        "biometric_purged_count": deleted_count,
    }
