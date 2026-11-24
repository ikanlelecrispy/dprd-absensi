import math
from dataclasses import dataclass
from sqlalchemy.orm import Session
from app.db.models.location import Location


@dataclass
class GeofenceResult:
    allowed: bool
    enforced: bool
    location: Location | None = None
    distance_meters: float | None = None
    reason: str | None = None


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Hitung jarak permukaan bumi antara dua titik koordinat (dalam meter)."""
    earth_radius_m = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(d_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return earth_radius_m * c


def validate_geofence(
    db: Session,
    latitude: float | None,
    longitude: float | None,
) -> GeofenceResult:
    """
    Validasi apakah koordinat berada dalam radius salah satu lokasi aktif.
    Jika tidak ada lokasi aktif di database, validasi lokasi dilewati (allowed=True).
    """
    active_locations = db.query(Location).filter(Location.is_active == True).all()

    if not active_locations:
        return GeofenceResult(allowed=True, enforced=False)

    if latitude is None or longitude is None:
        return GeofenceResult(
            allowed=False,
            enforced=True,
            reason="Izin lokasi (GPS) wajib aktif karena pembatasan area presensi sedang diberlakukan.",
        )

    nearest_loc: Location | None = None
    nearest_dist: float | None = None

    for loc in active_locations:
        dist = haversine_distance_meters(latitude, longitude, loc.latitude, loc.longitude)
        if nearest_dist is None or dist < nearest_dist:
            nearest_dist = dist
            nearest_loc = loc

    assert nearest_loc is not None and nearest_dist is not None
    rounded_dist = round(nearest_dist, 1)

    if nearest_dist <= nearest_loc.radius_meters:
        return GeofenceResult(
            allowed=True,
            enforced=True,
            location=nearest_loc,
            distance_meters=rounded_dist,
        )

    return GeofenceResult(
        allowed=False,
        enforced=True,
        location=nearest_loc,
        distance_meters=rounded_dist,
        reason=(
            f"Di luar jangkauan '{nearest_loc.name}' "
            f"(jarak {int(round(nearest_dist))} m, maks radius {nearest_loc.radius_meters} m)."
        ),
    )
