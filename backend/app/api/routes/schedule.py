from datetime import datetime, time
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin
from app.db.session import get_db
from app.core.schedule import (
    get_or_create_schedule,
    resolve_current_session,
    format_hhmm,
)

router = APIRouter(prefix="/schedule", tags=["Attendance Schedule"])


class ScheduleUpdateRequest(BaseModel):
    check_in_start: str = Field(..., pattern=r"^\d{2}:\d{2}$", examples=["06:00"])
    check_in_end: str = Field(..., pattern=r"^\d{2}:\d{2}$", examples=["09:00"])
    check_out_start: str = Field(..., pattern=r"^\d{2}:\d{2}$", examples=["14:00"])
    check_out_end: str = Field(..., pattern=r"^\d{2}:\d{2}$", examples=["16:00"])


def _parse_hhmm(val: str, field_label: str) -> time:
    try:
        return datetime.strptime(val, "%H:%M").time()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Format waktu '{field_label}' tidak valid (gunakan HH:MM).",
        )


def _serialize_schedule(sched) -> dict:
    return {
        "id": str(sched.id),
        "check_in_start": format_hhmm(sched.check_in_start),
        "check_in_end": format_hhmm(sched.check_in_end),
        "check_out_start": format_hhmm(sched.check_out_start),
        "check_out_end": format_hhmm(sched.check_out_end),
        "is_active": sched.is_active,
        "updated_at": sched.updated_at.isoformat() if sched.updated_at else None,
    }


@router.get("", dependencies=[Depends(get_current_admin)])
def get_schedule(db: Session = Depends(get_db)):
    """Ambil konfigurasi jadwal presensi aktif untuk halaman Admin."""
    sched = get_or_create_schedule(db)
    return _serialize_schedule(sched)


@router.put("", dependencies=[Depends(get_current_admin)])
def update_schedule(data: ScheduleUpdateRequest, db: Session = Depends(get_db)):
    """Perbarui rentang waktu Presensi Masuk dan Presensi Pulang oleh Admin."""
    ci_start = _parse_hhmm(data.check_in_start, "Mulai Presensi Masuk")
    ci_end = _parse_hhmm(data.check_in_end, "Selesai Presensi Masuk")
    co_start = _parse_hhmm(data.check_out_start, "Mulai Presensi Pulang")
    co_end = _parse_hhmm(data.check_out_end, "Selesai Presensi Pulang")

    if ci_start >= ci_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Jam selesai Presensi Masuk harus lebih besar dari jam mulai.",
        )

    if co_start >= co_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Jam selesai Presensi Pulang harus lebih besar dari jam mulai.",
        )

    # Pastikan rentang Masuk dan Pulang tidak saling bertabrakan
    if not (ci_end < co_start or co_end < ci_start):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rentang jam Presensi Masuk dan Presensi Pulang tidak boleh saling tumpang tindih.",
        )

    sched = get_or_create_schedule(db)
    sched.check_in_start = ci_start
    sched.check_in_end = ci_end
    sched.check_out_start = co_start
    sched.check_out_end = co_end
    db.commit()
    db.refresh(sched)

    res = resolve_current_session(db)
    return {
        "success": True,
        "message": (
            f"Jadwal presensi diperbarui! "
            f"Masuk: {format_hhmm(ci_start)}–{format_hhmm(ci_end)} WIB | "
            f"Pulang: {format_hhmm(co_start)}–{format_hhmm(co_end)} WIB."
        ),
        "schedule": _serialize_schedule(sched),
        "current_session": {
            "session_code": res.session_code,
            "is_open": res.is_open,
            "is_late": res.is_late,
            "late_minutes": res.late_minutes,
            "label": res.label,
            "short_label": res.short_label,
            "message": res.message,
            "server_time": res.server_now.strftime("%H:%M:%S WIB"),
        },
    }


@router.get("/current")
def get_current_session(db: Session = Depends(get_db)):
    """
    Endpoint real-time sisi pengguna (Kiosk):
    Mengembalikan waktu server dan status sesi presensi aktif saat ini.
    """
    res = resolve_current_session(db)
    return {
        "session_code": res.session_code,
        "is_open": res.is_open,
        "is_late": res.is_late,
        "late_minutes": res.late_minutes,
        "attendance_type": res.attendance_type.value if res.attendance_type else None,
        "label": res.label,
        "short_label": res.short_label,
        "message": res.message,
        "server_time_iso": res.server_now.isoformat(),
        "server_time_ms": int(res.server_now.timestamp() * 1000),
        "server_time_str": res.server_now.strftime("%H:%M:%S"),
        "server_date_str": res.server_now.strftime("%Y-%m-%d"),
        "schedule": _serialize_schedule(res.schedule),
    }
