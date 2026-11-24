import io
import re
import uuid
from datetime import datetime, date, timedelta
from typing import Literal
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin, hash_password, serialize_admin_user
from app.core.report_generator import (
    ParticipantReportData,
    build_participant_report,
    generate_report_csv,
    generate_report_pdf,
    serialize_report_preview,
)
from app.core.schedule import compute_late_status, get_server_now
from app.db.session import get_db
from app.db.models.participant import Participant, ParticipantStatus
from app.db.models.attendance import Attendance, AttendanceType, AttendanceStatus
from app.db.models.leave_request import LeaveRequest
from app.db.models.division import Division
from app.db.models.user import User

router = APIRouter(
    prefix="/admin",
    tags=["Admin Dashboard"],
    dependencies=[Depends(get_current_admin)],
)


class AdminUserCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    username: str | None = Field(default=None, min_length=2, max_length=50)
    role: Literal["admin", "superadmin"] = "admin"


class AdminUserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=100)
    role: Literal["admin", "superadmin"] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)


class ManualAttendanceRequest(BaseModel):
    participant_id: uuid.UUID
    attendance_type: AttendanceType
    checked_at: datetime = Field(default_factory=get_server_now)
    manual_reason: str = Field(..., min_length=5, description="Alasan wajib diisi (misal: kamera tablet rusak / izin khusus)")
    admin_name: str = Field(..., description="Nama admin yang menyetujui")


def _server_day_bounds(target_d: date | None = None) -> tuple[datetime, datetime, datetime]:
    """Kembalikan waktu server WIB beserta batas awal-akhir hari kalender (timezone-aware)."""
    server_now = get_server_now()
    chosen_date = target_d or server_now.date()
    day_start = datetime.combine(chosen_date, datetime.min.time(), tzinfo=server_now.tzinfo)
    return server_now, day_start, day_start + timedelta(days=1)


@router.get("/stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Ringkasan statistik dashboard admin."""
    server_now, today_start, tomorrow_start = _server_day_bounds()

    total_active_participants = (
        db.query(Participant)
        .filter(Participant.status == ParticipantStatus.ACTIVE)
        .count()
    )

    today_attendances = (
        db.query(Attendance)
        .filter(
            Attendance.checked_at >= today_start,
            Attendance.checked_at < tomorrow_start,
        )
        .all()
    )

    check_ins = len([a for a in today_attendances if a.attendance_type == AttendanceType.CHECK_IN])
    check_outs = len([a for a in today_attendances if a.attendance_type == AttendanceType.CHECK_OUT])
    suspicious_count = len([a for a in today_attendances if a.is_suspicious])
    today_leaves = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.leave_date == today_start.date())
        .count()
    )

    return {
        "active_participants": total_active_participants,
        "today_check_ins": check_ins,
        "today_check_outs": check_outs,
        "today_flagged": suspicious_count,
        "today_leaves": today_leaves,
        "server_time": server_now.strftime("%Y-%m-%d %H:%M:%S WIB"),
        "server_date": today_start.date().isoformat(),
    }


@router.get("/attendance")
def get_attendance_logs(
    target_date: str | None = None,  # Format: YYYY-MM-DD
    division_id: uuid.UUID | None = None,
    only_flagged: bool = False,
    db: Session = Depends(get_db),
):
    """Mengambil daftar log presensi dan izin harian dengan filter tanggal, divisi, atau status flagged."""
    server_now = get_server_now()
    query = db.query(Attendance)
    leave_query = db.query(LeaveRequest)
    chosen_date: date | None = None

    if target_date:
        try:
            chosen_date = datetime.strptime(target_date, "%Y-%m-%d").date()
            _, d_start, d_next = _server_day_bounds(chosen_date)
            query = query.filter(Attendance.checked_at >= d_start, Attendance.checked_at < d_next)
            leave_query = leave_query.filter(LeaveRequest.leave_date == chosen_date)
        except ValueError:
            seven_days_ago = server_now - timedelta(days=7)
            leave_query = leave_query.filter(LeaveRequest.leave_date >= seven_days_ago.date())
    else:
        # Default 7 hari terakhir berbasis zona waktu server
        seven_days_ago = server_now - timedelta(days=7)
        query = query.filter(Attendance.checked_at >= seven_days_ago)
        leave_query = leave_query.filter(LeaveRequest.leave_date >= seven_days_ago.date())

    if only_flagged:
        query = query.filter(Attendance.is_suspicious == True)

    records = query.order_by(Attendance.checked_at.desc()).all()
    leaves = [] if only_flagged else leave_query.order_by(LeaveRequest.created_at.desc()).all()

    items_with_sort: list[tuple[datetime, dict]] = []
    for r in records:
        if division_id and r.participant and r.participant.division_id != division_id:
            continue

        local_checked = (
            r.checked_at.astimezone(server_now.tzinfo)
            if r.checked_at.tzinfo
            else r.checked_at.replace(tzinfo=server_now.tzinfo)
        )
        items_with_sort.append((
            local_checked,
            {
                "id": str(r.id),
                "record_kind": "attendance",
                "participant_id": str(r.participant_id),
                "intern_id": r.participant.intern_id if r.participant else "-",
                "full_name": r.participant.full_name if r.participant else "Peserta Dihapus",
                "division": r.participant.division.name if r.participant and r.participant.division else "-",
                "attendance_type": "Masuk" if r.attendance_type == AttendanceType.CHECK_IN else "Pulang",
                "is_late": bool(r.is_late),
                "late_minutes": int(r.late_minutes or 0),
                "status": r.status.value,
                "checked_at": local_checked.strftime("%Y-%m-%d %H:%M:%S WIB"),
                "similarity_score": round(r.similarity_score, 3) if r.similarity_score else None,
                "is_suspicious": r.is_suspicious,
                "suspicious_reason": r.suspicious_reason,
                "manual_reason": r.manual_reason,
                "location_name": r.location.name if r.location else None,
                "distance_meters": round(r.distance_meters) if r.distance_meters is not None else None,
                "evidence_photo_url": f"/evidence/{r.evidence_photo_path}" if r.evidence_photo_path else None,
            },
        ))

    for lv in leaves:
        if division_id and lv.participant and lv.participant.division_id != division_id:
            continue

        local_created = (
            lv.created_at.astimezone(server_now.tzinfo)
            if lv.created_at.tzinfo
            else lv.created_at.replace(tzinfo=server_now.tzinfo)
        )
        items_with_sort.append((
            local_created,
            {
                "id": str(lv.id),
                "record_kind": "leave",
                "participant_id": str(lv.participant_id),
                "intern_id": lv.participant.intern_id if lv.participant else "-",
                "full_name": lv.participant.full_name if lv.participant else "Peserta Dihapus",
                "division": lv.participant.division.name if lv.participant and lv.participant.division else "-",
                "attendance_type": "Izin",
                "is_late": False,
                "late_minutes": 0,
                "status": "LEAVE",
                "checked_at": f"{lv.leave_date.strftime('%Y-%m-%d')} (Dikirim {local_created.strftime('%H:%M WIB')})",
                "leave_date": lv.leave_date.isoformat(),
                "similarity_score": None,
                "is_suspicious": False,
                "suspicious_reason": None,
                "manual_reason": lv.reason,
                "location_name": "Pengajuan Mobile",
                "distance_meters": None,
                "evidence_photo_url": None,
            },
        ))

    items_with_sort.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in items_with_sort]


@router.get("/export")
def export_attendance_report(
    export_format: str = Query("csv", regex="^(csv|excel)$"),
    target_date: str | None = None,
    db: Session = Depends(get_db),
):
    """Ekspor rekap presensi ke CSV atau Excel."""
    server_now = get_server_now()
    query = db.query(Attendance)
    if target_date:
        try:
            d = datetime.strptime(target_date, "%Y-%m-%d").date()
            _, d_start, d_next = _server_day_bounds(d)
            query = query.filter(Attendance.checked_at >= d_start, Attendance.checked_at < d_next)
        except ValueError:
            pass

    records = query.order_by(Attendance.checked_at.desc()).all()

    rows = []
    for r in records:
        local_checked = (
            r.checked_at.astimezone(server_now.tzinfo)
            if r.checked_at.tzinfo
            else r.checked_at
        )
        rows.append({
            "Waktu": local_checked.strftime("%Y-%m-%d %H:%M:%S"),
            "ID Magang": r.participant.intern_id if r.participant else "",
            "Nama Lengkap": r.participant.full_name if r.participant else "",
            "Divisi": r.participant.division.name if r.participant and r.participant.division else "",
            "Jenis": "Masuk" if r.attendance_type == AttendanceType.CHECK_IN else "Pulang",
            "Ketepatan Waktu": (
                "Terlambat"
                if r.is_late
                else ("Tepat Waktu" if r.attendance_type == AttendanceType.CHECK_IN else "-")
            ),
            "Terlambat (Menit)": int(r.late_minutes or 0) if r.is_late else 0,
            "Metode/Status": r.status.value,
            "Skor Kemiripan": round(r.similarity_score, 3) if r.similarity_score else "-",
            "Lokasi": r.location.name if r.location else "-",
            "Jarak (m)": round(r.distance_meters) if r.distance_meters is not None else "-",
            "Mencurigakan": "YA" if r.is_suspicious else "TIDAK",
            "Keterangan/Alasan": r.suspicious_reason or r.manual_reason or "",
        })

    df = pd.DataFrame(rows)

    if export_format == "excel":
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Presensi DPRD")
        output.seek(0)
        filename = f"rekap_presensi_{date.today().strftime('%Y%m%d')}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    else:
        csv_data = df.to_csv(index=False)
        filename = f"rekap_presensi_{date.today().strftime('%Y%m%d')}.csv"
        return StreamingResponse(
            io.StringIO(csv_data),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )


def _resolve_report_data(
    db: Session,
    participant_id: uuid.UUID,
    start_date: date | None,
    end_date: date | None,
) -> ParticipantReportData:
    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Peserta magang tidak ditemukan.",
        )

    server_today = get_server_now().date()
    resolved_end = end_date or server_today
    resolved_start = start_date or (resolved_end - timedelta(days=29))

    if resolved_start > resolved_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tanggal mulai tidak boleh lebih besar dari tanggal selesai.",
        )

    total_days = (resolved_end - resolved_start).days + 1
    if total_days > 366:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rentang laporan maksimal 366 hari per unduhan.",
        )

    return build_participant_report(db, participant, resolved_start, resolved_end)


def _slugify_filename(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (text or "peserta").lower()).strip("_")
    return slug[:40] or "peserta"


@router.get("/reports/preview")
def preview_participant_report(
    participant_id: uuid.UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    """Pratinjau rekap presensi harian per peserta (Nama, Tanggal, Masuk, Pulang)."""
    report = _resolve_report_data(db, participant_id, start_date, end_date)
    return serialize_report_preview(report)


@router.get("/reports/export")
def export_participant_report(
    participant_id: uuid.UUID,
    export_format: Literal["csv", "pdf"] = Query("pdf"),
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    """Unduh rekap presensi per peserta dalam format CSV atau PDF A4 (30 hari per lembar)."""
    report = _resolve_report_data(db, participant_id, start_date, end_date)
    slug_name = _slugify_filename(report.full_name)
    period_tag = f"{report.start_date.strftime('%Y%m%d')}_{report.end_date.strftime('%Y%m%d')}"

    if export_format == "csv":
        payload = generate_report_csv(report)
        filename = f"rekap_presensi_{slug_name}_{period_tag}.csv"
        return StreamingResponse(
            io.BytesIO(payload),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    payload = generate_report_pdf(report)
    filename = f"rekap_presensi_{slug_name}_{period_tag}.pdf"
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/attendance/manual")
def create_manual_attendance(data: ManualAttendanceRequest, db: Session = Depends(get_db)):
    """Input presensi manual oleh admin (wajib ada alasan & nama admin)."""
    participant = db.query(Participant).filter(Participant.id == data.participant_id).first()
    if not participant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Peserta tidak ditemukan.")

    is_late, late_mins = compute_late_status(db, data.checked_at, data.attendance_type)

    record = Attendance(
        participant_id=participant.id,
        attendance_type=data.attendance_type,
        status=AttendanceStatus.MANUAL,
        checked_at=data.checked_at,
        manual_reason=f"[{data.admin_name}] {data.manual_reason}",
        is_suspicious=False,
        is_late=is_late,
        late_minutes=late_mins,
    )
    db.add(record)
    db.commit()

    late_note = f" (Terlambat {late_mins} menit)" if is_late else ""
    return {
        "success": True,
        "is_late": is_late,
        "late_minutes": late_mins,
        "message": f"Presensi manual{late_note} untuk {participant.full_name} berhasil dicatat oleh {data.admin_name}.",
    }


class UpdateAttendanceRequest(BaseModel):
    attendance_type: AttendanceType | None = None
    checked_at: datetime | None = None
    manual_reason: str | None = None


@router.put("/attendance/{attendance_id}")
def update_attendance_record(attendance_id: uuid.UUID, data: UpdateAttendanceRequest, db: Session = Depends(get_db)):
    """Admin mengedit data presensi yang salah / keliru."""
    record = db.query(Attendance).filter(Attendance.id == attendance_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data presensi tidak ditemukan.")

    if data.attendance_type is not None:
        record.attendance_type = data.attendance_type
    if data.checked_at is not None:
        record.checked_at = data.checked_at
    if data.manual_reason is not None:
        record.manual_reason = data.manual_reason
        record.status = AttendanceStatus.MANUAL

    record.is_late, record.late_minutes = compute_late_status(
        db, record.checked_at, record.attendance_type
    )

    db.commit()
    return {"success": True, "message": "Data presensi berhasil diperbarui oleh admin."}


@router.delete("/attendance/{attendance_id}")
def delete_attendance_record(attendance_id: uuid.UUID, db: Session = Depends(get_db)):
    """Admin menghapus presensi duplikat atau data uji coba agar data kehadiran valid."""
    record = db.query(Attendance).filter(Attendance.id == attendance_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data presensi tidak ditemukan.")

    db.delete(record)
    db.commit()
    return {"success": True, "message": "Data presensi berhasil dihapus."}


@router.delete("/leaves/{leave_id}")
def delete_leave_record(leave_id: uuid.UUID, db: Session = Depends(get_db)):
    """Admin menghapus catatan izin harian bila terjadi kesalahan input oleh peserta."""
    leave = db.query(LeaveRequest).filter(LeaveRequest.id == leave_id).first()
    if not leave:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data izin harian tidak ditemukan.")

    db.delete(leave)
    db.commit()
    return {"success": True, "message": "Data izin harian berhasil dihapus."}


@router.delete("/attendance/duplicates/clean-today")
def clean_duplicate_attendances_today(db: Session = Depends(get_db)):
    """
    Fitur 1-Klik: Bersihkan presensi duplikat pada hari ini.
    Hanya menyisakan 1 presensi Masuk pertama dan 1 presensi Pulang terakhir per peserta.
    """
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_records = (
        db.query(Attendance)
        .filter(Attendance.checked_at >= today_start)
        .order_by(Attendance.checked_at.asc())
        .all()
    )

    kept = set()
    deleted_count = 0

    # Kelompokkan per participant dan jenis
    # Masuk: simpan yang paling awal
    # Pulang: simpan yang paling akhir
    records_by_key = {}
    for r in today_records:
        key = (r.participant_id, r.attendance_type)
        if key not in records_by_key:
            records_by_key[key] = []
        records_by_key[key].append(r)

    for (pid, att_type), r_list in records_by_key.items():
        if len(r_list) > 1:
            if att_type == AttendanceType.CHECK_IN:
                # Pertahankan yang pertama, hapus sisanya
                for extra in r_list[1:]:
                    db.delete(extra)
                    deleted_count += 1
            else:
                # Pertahankan yang terakhir, hapus sisanya
                for extra in r_list[:-1]:
                    db.delete(extra)
                    deleted_count += 1

    db.commit()
    return {
        "success": True,
        "deleted_count": deleted_count,
        "message": f"Berhasil membersihkan {deleted_count} data presensi ganda pada hari ini.",
    }


def _generate_unique_username(db: Session, email: str, preferred: str | None) -> str:
    if preferred and preferred.strip():
        candidate = preferred.strip().lower()
        exists = db.query(User).filter(func.lower(User.username) == candidate).first()
        if exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Username '{candidate}' sudah digunakan.",
            )
        return candidate

    base = re.sub(r"[^a-z0-9._-]", "", email.split("@", 1)[0].lower())[:40] or "admin"
    candidate = base
    suffix = 2
    while db.query(User).filter(func.lower(User.username) == candidate).first():
        candidate = f"{base[:36]}{suffix}"
        suffix += 1
    return candidate


@router.get("/users")
def list_admin_users(db: Session = Depends(get_db)):
    """Daftar seluruh akun admin dashboard."""
    users = db.query(User).order_by(User.created_at.asc()).all()
    return [serialize_admin_user(u) for u in users]


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_admin_user(data: AdminUserCreate, db: Session = Depends(get_db)):
    """Buat akun admin baru dari dalam Dashboard Admin."""
    email_norm = str(data.email).strip().lower()
    if db.query(User).filter(func.lower(User.email) == email_norm).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email '{email_norm}' sudah terdaftar pada akun admin lain.",
        )

    username = _generate_unique_username(db, email_norm, data.username)
    user = User(
        username=username,
        email=email_norm,
        full_name=data.full_name.strip(),
        role=data.role,
        is_active=True,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "success": True,
        "message": f"Akun admin untuk {user.full_name} berhasil dibuat.",
        "user": serialize_admin_user(user),
    }


@router.patch("/users/{user_id}")
def update_admin_user(
    user_id: uuid.UUID,
    data: AdminUserUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """Perbarui status aktif, peran, atau kata sandi akun admin."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Akun admin tidak ditemukan.")

    if data.is_active is False:
        if user.id == current_admin.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tidak dapat menonaktifkan akun yang sedang dipakai login.",
            )
        active_count = db.query(User).filter(User.is_active == True).count()
        if user.is_active and active_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Minimal harus ada satu akun admin yang aktif.",
            )
        user.is_active = False
    elif data.is_active is True:
        user.is_active = True

    if data.full_name is not None:
        user.full_name = data.full_name.strip()
    if data.role is not None:
        user.role = data.role
    if data.password is not None:
        user.hashed_password = hash_password(data.password)

    db.commit()
    db.refresh(user)
    return {
        "success": True,
        "message": f"Akun {user.full_name} diperbarui.",
        "user": serialize_admin_user(user),
    }


@router.delete("/users/{user_id}")
def delete_admin_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """Hapus akun admin dari database."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Akun admin tidak ditemukan.")

    if user.id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tidak dapat menghapus akun yang sedang Anda gunakan.",
        )

    active_count = db.query(User).filter(User.is_active == True).count()
    if user.is_active and active_count <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Minimal harus ada satu akun admin aktif di dalam sistem.",
        )

    deleted_name = user.full_name
    db.delete(user)
    db.commit()
    return {"success": True, "message": f"Akun admin {deleted_name} telah dihapus."}
