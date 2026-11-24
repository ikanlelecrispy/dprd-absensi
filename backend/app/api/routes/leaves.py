import uuid
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.schedule import get_server_now
from app.db.models.attendance import Attendance
from app.db.models.leave_request import LeaveRequest
from app.db.models.participant import Participant, ParticipantStatus
from app.db.session import get_db

router = APIRouter(prefix="/leaves", tags=["Leave Requests"])


class LeaveSubmitRequest(BaseModel):
    participant_id: uuid.UUID
    leave_date: date | None = Field(default=None, description="Tanggal izin (default hari ini WIB)")
    reason: str = Field(..., min_length=5, max_length=500, description="Alasan izin harian")


@router.get("/participants")
def list_active_participants_for_leave(response: Response, db: Session = Depends(get_db)):
    """Daftar ringkas peserta aktif untuk dropdown pengisian izin harian di halaman mobile."""
    server_now = get_server_now()
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

    participants = (
        db.query(Participant)
        .filter(Participant.status == ParticipantStatus.ACTIVE)
        .order_by(Participant.full_name.asc())
        .all()
    )

    return {
        "server_date": server_now.date().isoformat(),
        "server_time": server_now.strftime("%H:%M WIB"),
        "participants": [
            {
                "id": str(p.id),
                "intern_id": p.intern_id,
                "full_name": p.full_name,
                "division": p.division.name if p.division else "-",
            }
            for p in participants
        ],
    }


INDONESIAN_MONTHS_SHORT = (
    "",
    "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
    "Jul", "Agu", "Sep", "Okt", "Nov", "Des",
)


def _format_short_date(d: date) -> str:
    return f"{d.day} {INDONESIAN_MONTHS_SHORT[d.month]} {d.year}"


def _initials(full_name: str) -> str:
    parts = [w for w in (full_name or "").strip().split() if w]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


@router.get("/student/{participant_id}")
def get_student_leave_portal(
    participant_id: uuid.UUID,
    response: Response,
    db: Session = Depends(get_db),
):
    """Data ringkasan mahasiswa aktif untuk tampilan portal izin mobile (tanpa data kontak sensitif)."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    server_now = get_server_now()
    today_date = server_now.date()

    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if not participant or participant.status != ParticipantStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Peserta magang tidak ditemukan atau sudah tidak aktif.",
        )

    month_start = today_date.replace(day=1)
    if today_date.month == 12:
        next_month_start = date(today_date.year + 1, 1, 1)
    else:
        next_month_start = date(today_date.year, today_date.month + 1, 1)

    month_dt_start = datetime.combine(month_start, datetime.min.time(), tzinfo=server_now.tzinfo)
    month_dt_end = datetime.combine(next_month_start, datetime.min.time(), tzinfo=server_now.tzinfo)

    month_attendances = (
        db.query(Attendance)
        .filter(
            Attendance.participant_id == participant.id,
            Attendance.checked_at >= month_dt_start,
            Attendance.checked_at < month_dt_end,
        )
        .order_by(Attendance.checked_at.desc())
        .all()
    )

    present_dates: set[date] = set()
    late_dates: set[date] = set()
    today_in_time: str | None = None
    today_out_time: str | None = None

    for rec in month_attendances:
        local_dt = rec.checked_at.astimezone(server_now.tzinfo) if rec.checked_at.tzinfo else rec.checked_at
        d = local_dt.date()
        present_dates.add(d)
        if rec.is_late:
            late_dates.add(d)
        if d == today_date:
            t_str = local_dt.strftime("%H:%M WIB")
            if rec.attendance_type.value == "check_in":
                today_in_time = t_str
            elif rec.attendance_type.value == "check_out" and not today_out_time:
                today_out_time = t_str

    month_leaves = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.participant_id == participant.id,
            LeaveRequest.leave_date >= month_start,
            LeaveRequest.leave_date < next_month_start,
        )
        .all()
    )

    today_leave = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.participant_id == participant.id,
            LeaveRequest.leave_date == today_date,
        )
        .first()
    )

    if today_date in present_dates:
        today_status_code = "present"
        today_status_label = "Sudah Presensi"
    elif today_leave is not None:
        today_status_code = "leave"
        today_status_label = "Sudah Izin"
    else:
        today_status_code = "none"
        today_status_label = "Belum Presensi"

    recent_leaves = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.participant_id == participant.id)
        .order_by(LeaveRequest.leave_date.desc(), LeaveRequest.created_at.desc())
        .limit(8)
        .all()
    )

    recent_attendances = (
        db.query(Attendance)
        .filter(Attendance.participant_id == participant.id)
        .order_by(Attendance.checked_at.desc())
        .limit(8)
        .all()
    )

    return {
        "server_date": today_date.isoformat(),
        "server_date_display": _format_short_date(today_date),
        "participant": {
            "id": str(participant.id),
            "intern_id": participant.intern_id,
            "full_name": participant.full_name,
            "initials": _initials(participant.full_name),
            "division": participant.division.name if participant.division else "-",
            "institution": participant.institution or "-",
            "internship_period": f"{_format_short_date(participant.internship_start)} - {_format_short_date(participant.internship_end)}",
        },
        "today": {
            "date_iso": today_date.isoformat(),
            "status_code": today_status_code,
            "status_label": today_status_label,
            "check_in_time": today_in_time,
            "check_out_time": today_out_time,
            "leave_reason": today_leave.reason if today_leave else None,
        },
        "month_summary": {
            "month_label": f"{INDONESIAN_MONTHS_SHORT[today_date.month]} {today_date.year}",
            "present_days": len(present_dates),
            "leave_days": len(month_leaves),
            "late_days": len(late_dates),
        },
        "recent_leaves": [
            {
                "id": str(lv.id),
                "leave_date": lv.leave_date.isoformat(),
                "leave_date_display": _format_short_date(lv.leave_date),
                "reason": lv.reason,
                "submitted_at": (
                    lv.created_at.astimezone(server_now.tzinfo)
                    if lv.created_at.tzinfo
                    else lv.created_at
                ).strftime("%d/%m/%Y %H:%M WIB"),
            }
            for lv in recent_leaves
        ],
        "recent_attendances": [
            {
                "date_display": _format_short_date(
                    (rec.checked_at.astimezone(server_now.tzinfo) if rec.checked_at.tzinfo else rec.checked_at).date()
                ),
                "attendance_type": "Masuk" if rec.attendance_type.value == "check_in" else "Pulang",
                "time_str": (
                    rec.checked_at.astimezone(server_now.tzinfo) if rec.checked_at.tzinfo else rec.checked_at
                ).strftime("%H:%M WIB"),
                "is_late": bool(rec.is_late),
                "late_minutes": int(rec.late_minutes or 0),
            }
            for rec in recent_attendances
        ],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def submit_daily_leave(data: LeaveSubmitRequest, db: Session = Depends(get_db)):
    """
    Pengisian izin harian mandiri (pilih nama -> isi alasan -> submit):
    Otomatis masuk sebagai catatan izin pada tanggal yang dipilih tanpa approval admin.
    """
    server_now = get_server_now()
    target_date = data.leave_date or server_now.date()
    clean_reason = " ".join((data.reason or "").split())

    if len(clean_reason) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alasan izin wajib diisi minimal 5 karakter.",
        )

    participant = db.query(Participant).filter(Participant.id == data.participant_id).first()
    if not participant or participant.status != ParticipantStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Peserta magang tidak ditemukan atau sudah tidak aktif.",
        )

    date_display = target_date.strftime("%d/%m/%Y")

    existing_leave = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.participant_id == participant.id,
            LeaveRequest.leave_date == target_date,
        )
        .first()
    )
    if existing_leave:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{participant.full_name} sudah tercatat izin pada tanggal {date_display}.",
        )

    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=server_now.tzinfo)
    day_end = day_start + timedelta(days=1)
    existing_att = (
        db.query(Attendance)
        .filter(
            Attendance.participant_id == participant.id,
            Attendance.checked_at >= day_start,
            Attendance.checked_at < day_end,
        )
        .first()
    )
    if existing_att:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{participant.full_name} sudah mencatat presensi pada tanggal {date_display}, sehingga tidak dapat mengajukan izin di tanggal yang sama.",
        )

    leave = LeaveRequest(
        participant_id=participant.id,
        leave_date=target_date,
        reason=clean_reason,
    )
    db.add(leave)
    db.commit()
    db.refresh(leave)

    local_created = (
        leave.created_at.astimezone(server_now.tzinfo)
        if leave.created_at.tzinfo
        else leave.created_at
    )

    return {
        "success": True,
        "id": str(leave.id),
        "participant_id": str(participant.id),
        "full_name": participant.full_name,
        "intern_id": participant.intern_id,
        "division": participant.division.name if participant.division else "-",
        "leave_date": target_date.isoformat(),
        "leave_date_display": date_display,
        "reason": leave.reason,
        "submitted_at": local_created.strftime("%d/%m/%Y %H:%M WIB"),
        "message": f"Izin harian untuk {participant.full_name} pada {date_display} berhasil dicatat.",
    }
