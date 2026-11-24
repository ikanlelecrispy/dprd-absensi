import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin
from app.db.session import get_db
from app.db.models.location import Location
from app.core.geofence import validate_geofence

router = APIRouter(prefix="/locations", tags=["Locations (Geofence)"])


class LocationCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    address: str | None = Field(default=None)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    radius_meters: int = Field(default=100, ge=10, le=50000)
    is_active: bool = Field(default=True)


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    address: str | None = Field(default=None)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    radius_meters: int | None = Field(default=None, ge=10, le=50000)
    is_active: bool | None = Field(default=None)


class LocationCheckRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)


def _serialize_location(loc: Location) -> dict:
    return {
        "id": str(loc.id),
        "name": loc.name,
        "address": loc.address,
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "radius_meters": loc.radius_meters,
        "is_active": loc.is_active,
        "created_at": loc.created_at.isoformat() if loc.created_at else None,
        "updated_at": loc.updated_at.isoformat() if loc.updated_at else None,
    }


@router.get("", dependencies=[Depends(get_current_admin)])
def list_locations(db: Session = Depends(get_db)):
    """Daftar seluruh titik lokasi presensi."""
    locations = db.query(Location).order_by(Location.created_at.asc()).all()
    return [_serialize_location(loc) for loc in locations]


@router.get("/active")
def get_active_locations(db: Session = Depends(get_db)):
    """Status pembatasan lokasi saat ini untuk kiosk/client."""
    active = (
        db.query(Location)
        .filter(Location.is_active == True)
        .order_by(Location.created_at.asc())
        .all()
    )
    return {
        "enforced": len(active) > 0,
        "locations": [_serialize_location(loc) for loc in active],
    }


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(get_current_admin)])
def create_location(data: LocationCreate, db: Session = Depends(get_db)):
    """Tambah titik lokasi & radius baru."""
    loc = Location(
        name=data.name.strip(),
        address=data.address.strip() if data.address else None,
        latitude=data.latitude,
        longitude=data.longitude,
        radius_meters=data.radius_meters,
        is_active=data.is_active,
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return _serialize_location(loc)


@router.put("/{location_id}", dependencies=[Depends(get_current_admin)])
def update_location(location_id: uuid.UUID, data: LocationUpdate, db: Session = Depends(get_db)):
    """Perbarui koordinat, radius, nama, atau status aktif lokasi."""
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lokasi tidak ditemukan.")

    if data.name is not None:
        loc.name = data.name.strip()
    if data.address is not None:
        loc.address = data.address.strip() or None
    if data.latitude is not None:
        loc.latitude = data.latitude
    if data.longitude is not None:
        loc.longitude = data.longitude
    if data.radius_meters is not None:
        loc.radius_meters = data.radius_meters
    if data.is_active is not None:
        loc.is_active = data.is_active

    db.commit()
    db.refresh(loc)
    return _serialize_location(loc)


@router.delete("/{location_id}", dependencies=[Depends(get_current_admin)])
def delete_location(location_id: uuid.UUID, db: Session = Depends(get_db)):
    """Hapus titik lokasi."""
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lokasi tidak ditemukan.")

    name = loc.name
    db.delete(loc)
    db.commit()
    return {"success": True, "message": f"Lokasi '{name}' berhasil dihapus."}


@router.post("/check")
def check_coordinate(data: LocationCheckRequest, db: Session = Depends(get_db)):
    """Uji koordinat terhadap lokasi aktif (preview geofence)."""
    res = validate_geofence(db, data.latitude, data.longitude)
    return {
        "allowed": res.allowed,
        "enforced": res.enforced,
        "distance_meters": res.distance_meters,
        "location_name": res.location.name if res.location else None,
        "radius_meters": res.location.radius_meters if res.location else None,
        "reason": res.reason,
    }
