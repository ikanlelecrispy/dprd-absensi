import uuid
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.schedule import AttendanceSchedule
from app.db.models.attendance import Attendance, AttendanceType

settings = get_settings()


@dataclass
class SessionResolution:
    session_code: str          # "check_in" | "late_check_in" | "check_out" | "closed"
    is_open: bool
    attendance_type: AttendanceType | None
    label: str                 # e.g. "Sesi Aktif: Presensi Masuk"
    short_label: str           # "Masuk" | "Terlambat" | "Pulang" | "Tutup"
    message: str
    server_now: datetime
    schedule: AttendanceSchedule
    is_late: bool = False
    late_minutes: int = 0


def get_server_now() -> datetime:
    """Mengembalikan waktu server saat ini (timezone-aware sesuai konfigurasi server)."""
    tz = ZoneInfo(settings.timezone)
    return datetime.now(tz)


def format_hhmm(t: time) -> str:
    return t.strftime("%H:%M")


def get_or_create_schedule(db: Session) -> AttendanceSchedule:
    """Ambil konfigurasi jadwal presensi aktif, atau buat default (06:00-09:00 & 14:00-16:00)."""
    sched = (
        db.query(AttendanceSchedule)
        .filter(AttendanceSchedule.is_active == True)
        .order_by(AttendanceSchedule.created_at.asc())
        .first()
    )
    if not sched:
        sched = AttendanceSchedule(
            check_in_start=time(6, 0),
            check_in_end=time(9, 0),
            check_out_start=time(14, 0),
            check_out_end=time(16, 0),
            is_active=True,
        )
        db.add(sched)
        db.commit()
        db.refresh(sched)
    return sched


def resolve_current_session(
    db: Session,
    now: datetime | None = None,
) -> SessionResolution:
    """
    Cocokkan waktu server saat ini dengan jadwal dari database.
    Menentukan otomatis apakah sesi sedang Masuk, Pulang, atau Tutup.
    """
    server_now = now or get_server_now()
    sched = get_or_create_schedule(db)
    current_hm = server_now.time().replace(tzinfo=None, second=0, microsecond=0)

    ci_start = sched.check_in_start
    ci_end = sched.check_in_end
    co_start = sched.check_out_start
    co_end = sched.check_out_end

    if ci_start <= current_hm <= ci_end:
        return SessionResolution(
            session_code="check_in",
            is_open=True,
            attendance_type=AttendanceType.CHECK_IN,
            label="Sesi Aktif: Presensi Masuk",
            short_label="Masuk",
            message=f"Sesi Presensi Masuk sedang dibuka ({format_hhmm(ci_start)} - {format_hhmm(ci_end)} WIB).",
            server_now=server_now,
            schedule=sched,
            is_late=False,
            late_minutes=0,
        )

    if ci_end < current_hm < co_start:
        late_mins = (current_hm.hour * 60 + current_hm.minute) - (ci_end.hour * 60 + ci_end.minute)
        return SessionResolution(
            session_code="late_check_in",
            is_open=True,
            attendance_type=AttendanceType.CHECK_IN,
            label="Sesi Aktif: Masuk (Terlambat)",
            short_label="Terlambat",
            message=f"Terlambat {late_mins} menit dari batas masuk {format_hhmm(ci_end)} WIB.",
            server_now=server_now,
            schedule=sched,
            is_late=True,
            late_minutes=max(1, late_mins),
        )

    if co_start <= current_hm <= co_end:
        return SessionResolution(
            session_code="check_out",
            is_open=True,
            attendance_type=AttendanceType.CHECK_OUT,
            label="Sesi Aktif: Presensi Pulang",
            short_label="Pulang",
            message=f"Sesi Presensi Pulang sedang dibuka ({format_hhmm(co_start)} - {format_hhmm(co_end)} WIB).",
            server_now=server_now,
            schedule=sched,
            is_late=False,
            late_minutes=0,
        )

    return SessionResolution(
        session_code="closed",
        is_open=False,
        attendance_type=None,
        label="Di Luar Jam Presensi",
        short_label="Tutup",
        message=(
            f"Sesi presensi sedang ditutup. "
            f"Jam Masuk: {format_hhmm(ci_start)}-{format_hhmm(ci_end)} WIB | "
            f"Jam Pulang: {format_hhmm(co_start)}-{format_hhmm(co_end)} WIB."
        ),
        server_now=server_now,
        schedule=sched,
        is_late=False,
        late_minutes=0,
    )


def compute_late_status(
    db: Session,
    checked_at: datetime,
    attendance_type: AttendanceType,
) -> tuple[bool, int]:
    """Hitung status terlambat untuk presensi Masuk (termasuk input manual admin)."""
    if attendance_type != AttendanceType.CHECK_IN:
        return False, 0

    tz = ZoneInfo(settings.timezone)
    local_dt = checked_at.astimezone(tz) if checked_at.tzinfo else checked_at
    t_hm = local_dt.time().replace(tzinfo=None, second=0, microsecond=0)
    sched = get_or_create_schedule(db)
    if sched.check_in_end < t_hm < sched.check_out_start:
        mins = (t_hm.hour * 60 + t_hm.minute) - (sched.check_in_end.hour * 60 + sched.check_in_end.minute)
        return True, max(1, mins)
    return False, 0


def find_duplicate_attendance_today(
    db: Session,
    participant_id: uuid.UUID,
    attendance_type: AttendanceType,
    server_now: datetime,
) -> Attendance | None:
    """
    Validasi anti-duplikasi: cek apakah peserta sudah melakukan presensi
    dengan status/jenis yang sama pada tanggal server hari ini.
    """
    day_start = server_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = server_now.replace(hour=23, minute=59, second=59, microsecond=999999)

    return (
        db.query(Attendance)
        .filter(
            Attendance.participant_id == participant_id,
            Attendance.attendance_type == attendance_type,
            Attendance.checked_at >= day_start,
            Attendance.checked_at <= day_end,
        )
        .order_by(Attendance.checked_at.desc())
        .first()
    )
