import base64
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import bcrypt

from app.config import get_settings
from app.db.session import get_db
from app.db.models.attendance import Attendance, AttendanceType, AttendanceStatus
from app.db.models.participant import Participant, ParticipantStatus
from app.db.models.participant_pin import ParticipantPin
from app.core.geofence import validate_geofence
from app.core.schedule import (
    resolve_current_session,
    find_duplicate_attendance_today,
    get_server_now,
)
from app.core.matcher import matcher
from app.core.face_processor import face_processor
from app.core.evidence import save_attendance_evidence

router = APIRouter(prefix="/attendance", tags=["Attendance"])
settings = get_settings()


class FaceVerifyRequest(BaseModel):
    photo_b64: str = Field(..., description="Frame kamera JPEG/PNG dalam format base64/data URI")
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)


class FallbackPinRequest(BaseModel):
    intern_id: str = Field(..., description="Nomor Induk Magang")
    pin: str = Field(..., description="PIN 4-8 digit pribadi peserta")
    attendance_type: AttendanceType | None = Field(
        default=None,
        description="Diabaikan — jenis presensi ditentukan otomatis berdasarkan waktu server & jadwal admin",
    )
    photo_b64: str | None = Field(default=None, description="Foto bukti dari kamera tablet saat input PIN")
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)


@router.post("/verify")
def verify_face_attendance(data: FaceVerifyRequest, db: Session = Depends(get_db)):
    """
    Alur satu pintu 'Mulai Presensi' berbasis kamera:
    1. Cocokkan WAKTU SERVER saat ini dengan jadwal di DB (Masuk / Pulang / Tutup).
    2. Deteksi & kenali wajah menggunakan InsightFace + FaceMatcher.
    3. Validasi anti-duplikasi (maksimal 1x Masuk & 1x Pulang per tanggal server).
    4. Validasi lingkup lokasi (Geofence) jika ada lokasi aktif.
    5. Simpan bukti foto & catatan kehadiran ke tabel attendance.
    """
    session = resolve_current_session(db)
    now = session.server_now

    if not session.is_open or session.attendance_type is None:
        return {
            "status": "outside_schedule",
            "session_code": session.session_code,
            "session_label": session.label,
            "server_time": now.strftime("%H:%M:%S WIB"),
            "message": session.message,
        }

    # Decode base64 frame
    raw_b64 = data.photo_b64 or ""
    if "," in raw_b64:
        raw_b64 = raw_b64.split(",", 1)[1]

    try:
        img_bytes = base64.b64decode(raw_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format gambar kamera tidak valid.",
        )

    if frame_bgr is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gambar kamera kosong atau gagal dibaca.",
        )

    res = face_processor.process_frame(frame_bgr, enforce_quality=False)
    if not res.bbox:
        return {
            "status": "no_face",
            "message": "Wajah tidak terdeteksi. Posisikan wajah di dalam lingkaran panduan.",
        }

    x1, y1, x2, y2 = res.bbox
    h, w, _ = frame_bgr.shape
    bbox_norm = {
        "x": float(x1 / w),
        "y": float(y1 / h),
        "width": float((x2 - x1) / w),
        "height": float((y2 - y1) / h),
    }

    if res.embedding is None:
        return {
            "status": "analyzing",
            "bbox": bbox_norm,
            "message": "Kualitas wajah kurang tajam. Tahan posisi sebentar dan coba lagi.",
        }

    match_res = matcher.match(res.embedding)
    if not match_res.is_matched or match_res.participant_id is None:
        return {
            "status": "unrecognized",
            "bbox": bbox_norm,
            "similarity_score": round(match_res.similarity_score, 3),
            "message": "Wajah tidak dikenali. Pastikan pencahayaan cukup atau gunakan PIN Cadangan.",
        }

    pid = match_res.participant_id
    att_type = session.attendance_type
    jenis_str = session.short_label
    dup_label = "Masuk" if att_type == AttendanceType.CHECK_IN else "Pulang"
    dup_label = "Masuk" if att_type == AttendanceType.CHECK_IN else "Pulang"

    # Anti-duplikasi berdasarkan tanggal server
    existing_today = find_duplicate_attendance_today(db, pid, att_type, now)
    if existing_today:
        waktu_str = existing_today.checked_at.strftime("%H:%M WIB")
        return {
            "status": "already_checked",
            "bbox": bbox_norm,
            "participant_id": str(pid),
            "intern_id": match_res.intern_id,
            "full_name": match_res.full_name,
            "attendance_type": dup_label,
            "time": waktu_str,
            "message": f"Anda SUDAH melakukan presensi {dup_label} hari ini pukul {waktu_str}.",
        }

    # Validasi Geofence
    geo = validate_geofence(db, data.latitude, data.longitude)
    if not geo.allowed:
        return {
            "status": "out_of_range",
            "bbox": bbox_norm,
            "participant_id": str(pid),
            "intern_id": match_res.intern_id,
            "full_name": match_res.full_name,
            "distance_meters": geo.distance_meters,
            "max_radius": geo.location.radius_meters if geo.location else None,
            "message": geo.reason or "Lokasi berada di luar jangkauan area presensi.",
        }

    # Simpan foto bukti terkompresi (crop area wajah + WebP ringkas)
    evidence = save_attendance_evidence(
        frame_bgr,
        checked_at=now,
        bbox=res.bbox,
        base_dir=Path(settings.resolved_evidence_photo_path),
    )

    # Simpan log presensi ke DB
    att_record = Attendance(
        participant_id=pid,
        location_id=geo.location.id if geo.location else None,
        attendance_type=att_type,
        status=AttendanceStatus.FLAGGED if match_res.is_suspicious else AttendanceStatus.VERIFIED,
        checked_at=now,
        similarity_score=match_res.similarity_score,
        latitude=data.latitude,
        longitude=data.longitude,
        distance_meters=geo.distance_meters,
        evidence_photo_path=evidence.relative_path if evidence else None,
        evidence_photo_data=evidence.data if evidence else None,
        is_suspicious=match_res.is_suspicious,
        suspicious_reason=match_res.suspicious_reason,
        is_late=session.is_late,
        late_minutes=session.late_minutes,
    )
    db.add(att_record)
    db.commit()

    success_msg = (
        f"Presensi Masuk (Terlambat {session.late_minutes} menit) tercatat untuk {match_res.full_name}."
        if session.is_late
        else f"Presensi {jenis_str} Berhasil! Selamat beraktivitas, {match_res.full_name}."
    )

    return {
        "status": "success",
        "bbox": bbox_norm,
        "participant_id": str(pid),
        "intern_id": match_res.intern_id,
        "full_name": match_res.full_name,
        "similarity_score": round(match_res.similarity_score, 3),
        "time": now.strftime("%H:%M:%S WIB"),
        "attendance_type": jenis_str,
        "session_code": session.session_code,
        "is_late": session.is_late,
        "late_minutes": session.late_minutes,
        "location_name": geo.location.name if geo.location else None,
        "distance_meters": geo.distance_meters,
        "message": success_msg,
    }


@router.post("/fallback-pin")
def submit_fallback_pin_attendance(data: FallbackPinRequest, db: Session = Depends(get_db)):
    """
    JALUR PRESENSI CADANGAN MANDIRI (SELF-SERVICE PIN):
    Otomatis menentukan Masuk/Pulang berdasarkan waktu server dan jadwal dari Dashboard Admin.
    """
    session = resolve_current_session(db)
    now = session.server_now

    if not session.is_open or session.attendance_type is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=session.message,
        )

    att_type = session.attendance_type
    jenis_str = session.short_label
    dup_label = "Masuk" if att_type == AttendanceType.CHECK_IN else "Pulang"

    # 1. Cari Peserta
    participant = db.query(Participant).filter(
        Participant.intern_id == data.intern_id,
        Participant.status == ParticipantStatus.ACTIVE,
    ).first()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Peserta dengan ID '{data.intern_id}' tidak ditemukan atau sudah tidak aktif.",
        )

    # 2. Verifikasi PIN
    pin_record = db.query(ParticipantPin).filter(
        ParticipantPin.participant_id == participant.id,
        ParticipantPin.is_active == True,
    ).first()

    if not pin_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Peserta belum memiliki PIN cadangan. Silakan hubungi admin.",
        )

    # Cek Lockout (jika salah >= 3 kali)
    if pin_record.locked_until:
        locked_cmp = pin_record.locked_until
        now_cmp = now if locked_cmp.tzinfo else now.replace(tzinfo=None)
        if now_cmp < locked_cmp:
            sisa = int((locked_cmp - now_cmp).total_seconds())
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"PIN terkunci karena salah 3x. Silakan tunggu {sisa} detik lagi.",
            )

    # Cek kebenaran PIN
    if not bcrypt.checkpw(data.pin.encode("utf-8"), pin_record.hashed_pin.encode("utf-8")):
        pin_record.failed_attempts += 1
        if pin_record.failed_attempts >= 3:
            pin_record.locked_until = now + timedelta(minutes=10)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="PIN salah 3 kali berturut-turut. Akses PIN terkunci selama 10 menit demi keamanan.",
            )
        db.commit()
        sisa_percobaan = 3 - pin_record.failed_attempts
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"PIN salah! Sisa percobaan: {sisa_percobaan}x.",
        )

    # Reset counter jika benar
    pin_record.failed_attempts = 0
    pin_record.locked_until = None

    # Validasi Lingkup Lokasi (Geofence)
    geo = validate_geofence(db, data.latitude, data.longitude)
    if not geo.allowed:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=geo.reason or "Lokasi berada di luar jangkauan presensi.",
        )

    # ATURAN: SEHARI CUMA BISA 1x MASUK & 1x PULANG (berdasarkan tanggal server)
    existing_today = find_duplicate_attendance_today(db, participant.id, att_type, now)
    if existing_today:
        waktu_str = existing_today.checked_at.strftime("%H:%M WIB")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Peserta '{participant.full_name}' SUDAH melakukan presensi {dup_label} hari ini pukul {waktu_str}.",
        )

    # 3. Simpan foto bukti snapshot kamera secara ringkas & persisten
    ev_rel_path: str | None = None
    ev_photo_data: bytes | None = None
    if data.photo_b64:
        try:
            raw_b64 = data.photo_b64
            if "," in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]
            img_bytes = base64.b64decode(raw_b64)
            nparr = np.frombuffer(img_bytes, np.uint8)
            frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame_bgr is not None:
                evidence = save_attendance_evidence(
                    frame_bgr,
                    checked_at=now,
                    bbox=None,
                    base_dir=Path(settings.resolved_evidence_photo_path),
                )
                if evidence is not None:
                    ev_rel_path = evidence.relative_path
                    ev_photo_data = evidence.data
        except Exception:
            pass

    # 4. Simpan presensi ke database
    att_record = Attendance(
        participant_id=participant.id,
        location_id=geo.location.id if geo.location else None,
        attendance_type=att_type,
        status=AttendanceStatus.FALLBACK_PIN,
        checked_at=now,
        similarity_score=None,
        latitude=data.latitude,
        longitude=data.longitude,
        distance_meters=geo.distance_meters,
        evidence_photo_path=ev_rel_path,
        evidence_photo_data=ev_photo_data,
        is_suspicious=False,
        is_late=session.is_late,
        late_minutes=session.late_minutes,
        manual_reason="Presensi mandiri menggunakan PIN cadangan",
    )
    db.add(att_record)
    db.commit()

    pin_msg = (
        f"Presensi Masuk (Terlambat {session.late_minutes} menit) via PIN Berhasil untuk {participant.full_name}."
        if session.is_late
        else f"Presensi {jenis_str} via PIN Berhasil! Selamat beraktivitas, {participant.full_name}."
    )

    return {
        "success": True,
        "full_name": participant.full_name,
        "intern_id": participant.intern_id,
        "time": now.strftime("%H:%M:%S WIB"),
        "attendance_type": jenis_str,
        "is_late": session.is_late,
        "late_minutes": session.late_minutes,
        "message": pin_msg,
    }



@router.get("/today")
def get_today_attendance(response: Response, db: Session = Depends(get_db)):
    """Mendapatkan daftar presensi khusus tanggal server WIB hari ini."""
    server_now = get_server_now()
    today_start = server_now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    server_date_iso = today_start.date().isoformat()

    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["X-Server-Date"] = server_date_iso

    records = (
        db.query(Attendance)
        .filter(
            Attendance.checked_at >= today_start,
            Attendance.checked_at < tomorrow_start,
        )
        .order_by(Attendance.checked_at.desc())
        .all()
    )

    result = []
    for r in records:
        local_checked = (
            r.checked_at.astimezone(server_now.tzinfo)
            if r.checked_at.tzinfo
            else r.checked_at
        )
        result.append({
            "id": str(r.id),
            "participant_id": str(r.participant_id),
            "intern_id": r.participant.intern_id if r.participant else None,
            "full_name": r.participant.full_name if r.participant else None,
            "division": r.participant.division.name if r.participant and r.participant.division else None,
            "attendance_type": r.attendance_type.value,
            "status": r.status.value,
            "is_late": bool(r.is_late),
            "late_minutes": int(r.late_minutes or 0),
            "checked_at": local_checked.isoformat(),
            "checked_date": local_checked.date().isoformat(),
            "time_str": local_checked.strftime("%H:%M:%S WIB"),
            "similarity_score": round(r.similarity_score, 3) if r.similarity_score else None,
            "is_suspicious": r.is_suspicious,
            "suspicious_reason": r.suspicious_reason,
            "evidence_photo_url": f"/evidence/{r.evidence_photo_path}" if r.evidence_photo_path else None,
        })
    return result
