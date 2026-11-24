import uuid
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, EmailStr
from app.db.models.participant import ParticipantStatus


class ParticipantBase(BaseModel):
    intern_id: str
    full_name: str
    email: EmailStr | None = None
    phone: str | None = None
    institution: str | None = None
    division_id: uuid.UUID
    internship_start: date
    internship_end: date
    biometric_consent: bool = False
    notes: str | None = None


class ParticipantCreate(ParticipantBase):
    pass


class ParticipantUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    institution: str | None = None
    division_id: uuid.UUID | None = None
    internship_start: date | None = None
    internship_end: date | None = None
    status: ParticipantStatus | None = None
    notes: str | None = None


class ParticipantResponse(ParticipantBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ParticipantStatus
    consent_given_at: datetime | None
    created_at: datetime
    updated_at: datetime
    active_embeddings_count: int = 0
