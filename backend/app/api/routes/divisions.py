import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

from app.db.session import get_db
from app.db.models.division import Division

router = APIRouter(prefix="/divisions", tags=["Divisions"])


class DivisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    description: str | None
    supervisor_name: str | None
    is_active: bool


@router.get("", response_model=list[DivisionResponse])
def get_divisions(db: Session = Depends(get_db)):
    """Mengambil daftar seluruh divisi aktif di DPRD Surakarta."""
    return db.query(Division).filter(Division.is_active == True).order_by(Division.name).all()
