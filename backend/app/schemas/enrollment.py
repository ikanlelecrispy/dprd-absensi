import uuid
from pydantic import BaseModel, Field


class PhotoInput(BaseModel):
    photo_b64: str = Field(..., description="Foto dalam format Base64 (data URI atau raw base64)")
    angle: str = Field(..., description="Sudut pengambilan foto: 'front', 'left', 'right'")


class EnrollmentRequest(BaseModel):
    participant_id: uuid.UUID
    photos: list[PhotoInput] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="3 hingga 5 foto wajah dari berbagai sudut (depan, sedikit kiri, sedikit kanan)",
    )


class EnrollmentPhotoReport(BaseModel):
    angle: str
    is_valid: bool
    blur_score: float
    brightness_score: float
    message: str


class EnrollmentResponse(BaseModel):
    success: bool
    participant_id: uuid.UUID
    enrolled_count: int
    message: str
    reports: list[EnrollmentPhotoReport]
