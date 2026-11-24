import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
from matplotlib import patches
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from PIL import Image
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.attendance import Attendance, AttendanceStatus, AttendanceType
from app.db.models.leave_request import LeaveRequest
from app.db.models.participant import Participant

settings = get_settings()

ROWS_PER_A4_PAGE = 30
A4_WIDTH_MM = 210.0
A4_HEIGHT_MM = 297.0
A4_WIDTH_IN = A4_WIDTH_MM / 25.4
A4_HEIGHT_IN = A4_HEIGHT_MM / 25.4

INDONESIAN_DAYS = ("Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min")
INDONESIAN_MONTHS = (
    "",
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)

LOGO_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "frontend"
    / "admin"
    / "assets"
    / "logo-emblem.png"
)


@dataclass
class DailyReportRow:
    no: int
    full_name: str
    date_iso: str
    date_display: str
    check_in_time: str
    check_out_time: str
    is_late: bool
    late_minutes: int
    status_label: str
    note: str


@dataclass
class ParticipantReportData:
    participant_id: str
    intern_id: str
    full_name: str
    division: str
    institution: str
    internship_start: str
    internship_end: str
    participant_status: str
    start_date: date
    end_date: date
    total_days: int
    present_days: int
    on_time_days: int
    late_days: int
    leave_days: int
    check_out_days: int
    absent_days: int
    rows: list[DailyReportRow]


def _format_indonesian_date(d: date) -> str:
    day_abbr = INDONESIAN_DAYS[d.weekday()]
    return f"{day_abbr}, {d.strftime('%d/%m/%Y')}"


def _format_long_indonesian_date(d: date) -> str:
    return f"{d.day} {INDONESIAN_MONTHS[d.month]} {d.year}"


def _build_day_note(check_in: Attendance | None, check_out: Attendance | None) -> tuple[str, str]:
    """Kembalikan (status_label, note) untuk 1 hari kalender."""
    if not check_in and not check_out:
        return "Belum Hadir", "-"

    parts: list[str] = []
    if check_in:
        if check_in.is_late:
            parts.append(f"Terlambat {int(check_in.late_minutes or 0)} mnt")
            status_label = "Terlambat"
        else:
            parts.append("Tepat Waktu")
            status_label = "Hadir"

        if check_in.status == AttendanceStatus.MANUAL:
            parts.append("Manual")
        elif check_in.status == AttendanceStatus.FALLBACK_PIN:
            parts.append("PIN")
    else:
        status_label = "Pulang Saja"
        parts.append("Tanpa Masuk")

    if check_in and not check_out:
        parts.append("Belum Pulang")
    elif check_out and check_out.status == AttendanceStatus.MANUAL and "Manual" not in parts:
        parts.append("Pulang Manual")

    return status_label, " | ".join(parts)


def build_participant_report(
    db: Session,
    participant: Participant,
    start_date: date,
    end_date: date,
) -> ParticipantReportData:
    """Bangun rekap harian (Masuk & Pulang dalam 1 baris per tanggal) untuk 1 peserta."""
    tz = ZoneInfo(settings.timezone)
    range_start = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
    range_end = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=tz)

    records = (
        db.query(Attendance)
        .filter(
            Attendance.participant_id == participant.id,
            Attendance.checked_at >= range_start,
            Attendance.checked_at < range_end,
        )
        .order_by(Attendance.checked_at.asc())
        .all()
    )

    leaves = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.participant_id == participant.id,
            LeaveRequest.leave_date >= start_date,
            LeaveRequest.leave_date <= end_date,
        )
        .all()
    )
    leaves_by_day: dict[date, LeaveRequest] = {lv.leave_date: lv for lv in leaves}

    by_day: dict[date, dict[str, Attendance | None]] = {}
    for rec in records:
        local_dt = rec.checked_at.astimezone(tz) if rec.checked_at.tzinfo else rec.checked_at
        rec_day = local_dt.date()
        bucket = by_day.setdefault(rec_day, {"in": None, "out": None})
        if rec.attendance_type == AttendanceType.CHECK_IN:
            # Simpan presensi masuk paling awal di hari tersebut
            if bucket["in"] is None:
                bucket["in"] = rec
        elif rec.attendance_type == AttendanceType.CHECK_OUT:
            # Simpan presensi pulang paling akhir di hari tersebut
            bucket["out"] = rec

    total_days = (end_date - start_date).days + 1
    rows: list[DailyReportRow] = []
    present_days = 0
    on_time_days = 0
    late_days = 0
    leave_days = 0
    check_out_days = 0

    for idx in range(total_days):
        cur_date = start_date + timedelta(days=idx)
        day_rec = by_day.get(cur_date, {"in": None, "out": None})
        ci = day_rec["in"]
        co = day_rec["out"]
        lv = leaves_by_day.get(cur_date)

        ci_str = "-"
        co_str = "-"
        is_late = False
        late_minutes = 0

        if ci is not None:
            ci_local = ci.checked_at.astimezone(tz) if ci.checked_at.tzinfo else ci.checked_at
            ci_str = ci_local.strftime("%H:%M:%S")
            is_late = bool(ci.is_late)
            late_minutes = int(ci.late_minutes or 0) if is_late else 0
            if is_late:
                late_days += 1
            else:
                on_time_days += 1

        if co is not None:
            co_local = co.checked_at.astimezone(tz) if co.checked_at.tzinfo else co.checked_at
            co_str = co_local.strftime("%H:%M:%S")
            check_out_days += 1

        if ci is not None or co is not None:
            present_days += 1
            status_label, note = _build_day_note(ci, co)
        elif lv is not None:
            leave_days += 1
            status_label = "Izin"
            note = f"Izin: {lv.reason}"
        else:
            status_label, note = _build_day_note(None, None)

        rows.append(
            DailyReportRow(
                no=idx + 1,
                full_name=participant.full_name,
                date_iso=cur_date.isoformat(),
                date_display=_format_indonesian_date(cur_date),
                check_in_time=ci_str,
                check_out_time=co_str,
                is_late=is_late,
                late_minutes=late_minutes,
                status_label=status_label,
                note=note,
            )
        )

    return ParticipantReportData(
        participant_id=str(participant.id),
        intern_id=participant.intern_id,
        full_name=participant.full_name,
        division=participant.division.name if participant.division else "-",
        institution=participant.institution or "-",
        internship_start=participant.internship_start.isoformat(),
        internship_end=participant.internship_end.isoformat(),
        participant_status=participant.status.value,
        start_date=start_date,
        end_date=end_date,
        total_days=total_days,
        present_days=present_days,
        on_time_days=on_time_days,
        late_days=late_days,
        leave_days=leave_days,
        check_out_days=check_out_days,
        absent_days=max(0, total_days - present_days - leave_days),
        rows=rows,
    )


def serialize_report_preview(report: ParticipantReportData) -> dict:
    pages = max(1, (report.total_days + ROWS_PER_A4_PAGE - 1) // ROWS_PER_A4_PAGE)
    return {
        "participant": {
            "id": report.participant_id,
            "intern_id": report.intern_id,
            "full_name": report.full_name,
            "division": report.division,
            "institution": report.institution,
            "internship_start": report.internship_start,
            "internship_end": report.internship_end,
            "status": report.participant_status,
        },
        "period": {
            "start_date": report.start_date.isoformat(),
            "end_date": report.end_date.isoformat(),
            "total_days": report.total_days,
            "pdf_pages": pages,
            "rows_per_page": ROWS_PER_A4_PAGE,
        },
        "summary": {
            "total_days": report.total_days,
            "present_days": report.present_days,
            "on_time_days": report.on_time_days,
            "late_days": report.late_days,
            "leave_days": report.leave_days,
            "check_out_days": report.check_out_days,
            "absent_days": report.absent_days,
        },
        "rows": [
            {
                "no": r.no,
                "full_name": r.full_name,
                "date_iso": r.date_iso,
                "date_display": r.date_display,
                "check_in_time": r.check_in_time,
                "check_out_time": r.check_out_time,
                "is_late": r.is_late,
                "late_minutes": r.late_minutes,
                "status_label": r.status_label,
                "note": r.note,
            }
            for r in report.rows
        ],
    }


def generate_report_csv(report: ParticipantReportData) -> bytes:
    """Bangun file CSV UTF-8 BOM per peserta."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "No",
        "Nama",
        "ID Magang",
        "Divisi",
        "Tanggal",
        "Waktu Masuk",
        "Waktu Pulang",
        "Keterangan",
    ])
    for r in report.rows:
        writer.writerow([
            r.no,
            r.full_name,
            report.intern_id,
            report.division,
            r.date_iso,
            r.check_in_time,
            r.check_out_time,
            r.note,
        ])
    return buf.getvalue().encode("utf-8-sig")


def _truncate_text(value: str, max_len: int) -> str:
    clean = " ".join(str(value or "").split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3].rstrip() + "..."


def _draw_letterhead_template(ax, logo_img) -> None:
    """Gambar template kepala surat (kop) di bagian atas A4."""
    # Area bingkai template kop yang jelas dan rapi
    if logo_img is not None:
        ax.imshow(logo_img, extent=[16.0, 34.0, 29.0, 11.0], zorder=3)
    else:
        ax.add_patch(
            patches.Rectangle(
                (16.0, 11.0),
                18.0,
                18.0,
                facecolor="#F1F5F9",
                edgecolor="#94A3B8",
                linewidth=0.7,
            )
        )
        ax.text(25.0, 20.0, "LOGO", ha="center", va="center", fontsize=7, color="#475569", fontweight="bold")

    ax.text(
        109.0,
        14.2,
        "PEMERINTAH KOTA SURAKARTA",
        ha="center",
        va="center",
        fontsize=9.5,
        fontweight="bold",
        color="#1E293B",
        family="sans-serif",
    )
    ax.text(
        109.0,
        19.2,
        "SEKRETARIAT DPRD KOTA SURAKARTA",
        ha="center",
        va="center",
        fontsize=12.5,
        fontweight="bold",
        color="#0F172A",
        family="sans-serif",
    )
    ax.text(
        109.0,
        24.2,
        "[TEMPLATE KEPALA SURAT - ALAMAT INSTANSI / TELEPON / LAMAN MENYUSUL]",
        ha="center",
        va="center",
        fontsize=7.3,
        style="italic",
        color="#475569",
        family="sans-serif",
    )
    ax.text(
        109.0,
        28.2,
        "[Contoh: Jl. Adi Sucipto No. 143, Surakarta | Template dapat disesuaikan]",
        ha="center",
        va="center",
        fontsize=6.8,
        color="#64748B",
        family="sans-serif",
    )

    # Garis ganda kop surat resmi
    ax.plot([14.0, 196.0], [33.2, 33.2], color="#0F172A", linewidth=1.6)
    ax.plot([14.0, 196.0], [34.4, 34.4], color="#475569", linewidth=0.6)


def _draw_participant_meta(ax, report: ParticipantReportData, page_num: int, total_pages: int) -> None:
    ax.text(
        105.0,
        39.5,
        "LAPORAN REKAP PRESENSI PESERTA MAGANG",
        ha="center",
        va="center",
        fontsize=10.5,
        fontweight="bold",
        color="#0F172A",
        family="sans-serif",
    )

    # Kotak identitas peserta
    ax.add_patch(
        patches.Rectangle(
            (14.0, 43.5),
            182.0,
            14.5,
            facecolor="#F8FAFC",
            edgecolor="#CBD5E1",
            linewidth=0.7,
        )
    )

    left_items = [
        ("Nama Peserta", _truncate_text(report.full_name, 34)),
        ("ID Magang", _truncate_text(report.intern_id, 28)),
        ("Asal Instansi", _truncate_text(report.institution, 34)),
    ]
    right_items = [
        ("Divisi", _truncate_text(report.division, 40)),
        ("Periode", f"{report.start_date.strftime('%d/%m/%Y')} s.d. {report.end_date.strftime('%d/%m/%Y')}"),
        ("Lembar A4", f"Halaman {page_num} dari {total_pages} (maks. 30 hari/lembar)"),
    ]

    for idx, (lbl, val) in enumerate(left_items):
        y_pos = 46.7 + idx * 4.1
        ax.text(16.5, y_pos, lbl, ha="left", va="center", fontsize=7.5, color="#475569", fontweight="bold")
        ax.text(39.5, y_pos, f": {val}", ha="left", va="center", fontsize=7.5, color="#0F172A")

    for idx, (lbl, val) in enumerate(right_items):
        y_pos = 46.7 + idx * 4.1
        ax.text(109.0, y_pos, lbl, ha="left", va="center", fontsize=7.5, color="#475569", fontweight="bold")
        ax.text(127.5, y_pos, f": {val}", ha="left", va="center", fontsize=7.5, color="#0F172A")


def _draw_attendance_table(ax, page_rows: list[DailyReportRow]) -> float:
    """Gambar tabel presensi hingga 30 baris di atas 1 lembar A4. Kembalikan koordinat Y akhir."""
    cols = [
        ("No", 9.0, "center"),
        ("Nama", 47.0, "left"),
        ("Tanggal", 34.0, "left"),
        ("Waktu Masuk", 26.0, "center"),
        ("Waktu Pulang", 26.0, "center"),
        ("Keterangan", 40.0, "center"),
    ]
    start_x = 14.0
    table_y = 60.5
    header_h = 6.0
    row_h = 5.8

    # Header tabel
    cur_x = start_x
    for title, width, _ in cols:
        ax.add_patch(
            patches.Rectangle(
                (cur_x, table_y),
                width,
                header_h,
                facecolor="#1E3A8A",
                edgecolor="#1E3A8A",
                linewidth=0.5,
            )
        )
        ax.text(
            cur_x + width / 2.0,
            table_y + header_h / 2.0,
            title,
            ha="center",
            va="center",
            fontsize=7.8,
            fontweight="bold",
            color="#FFFFFF",
            family="sans-serif",
        )
        cur_x += width

    # Baris data (maksimal 30 baris per A4)
    y_cursor = table_y + header_h
    for row_idx, r in enumerate(page_rows):
        bg_color = "#FFFFFF" if row_idx % 2 == 0 else "#F8FAFC"
        values = [
            str(r.no),
            _truncate_text(r.full_name, 26),
            r.date_display,
            r.check_in_time,
            r.check_out_time,
            _truncate_text(r.note, 28),
        ]

        cur_x = start_x
        for (_, width, align), val in zip(cols, values):
            ax.add_patch(
                patches.Rectangle(
                    (cur_x, y_cursor),
                    width,
                    row_h,
                    facecolor=bg_color,
                    edgecolor="#CBD5E1",
                    linewidth=0.45,
                )
            )
            if align == "center":
                text_x = cur_x + width / 2.0
                ha = "center"
            else:
                text_x = cur_x + 2.2
                ha = "left"

            text_color = "#0F172A"
            if val == "-" or r.status_label == "Belum Hadir":
                if align == "center" and val == "-":
                    text_color = "#64748B"

            ax.text(
                text_x,
                y_cursor + row_h / 2.0,
                val,
                ha=ha,
                va="center",
                fontsize=7.3,
                color=text_color,
                family="sans-serif",
            )
            cur_x += width

        y_cursor += row_h

    return y_cursor


def _draw_footer_and_signature(
    ax,
    report: ParticipantReportData,
    table_end_y: float,
    page_num: int,
    total_pages: int,
    printed_on: date,
) -> None:
    is_last_page = page_num == total_pages
    if is_last_page:
        sum_y = max(table_end_y + 3.0, 243.0)
        ax.add_patch(
            patches.Rectangle(
                (14.0, sum_y),
                182.0,
                7.2,
                facecolor="#F1F5F9",
                edgecolor="#CBD5E1",
                linewidth=0.6,
            )
        )
        summary_text = (
            f"Ringkasan:  Total {report.total_days} Hari   |   "
            f"Hadir {report.present_days}   |   "
            f"Tepat Waktu {report.on_time_days}   |   "
            f"Terlambat {report.late_days}   |   "
            f"Izin {report.leave_days}   |   "
            f"Pulang {report.check_out_days}"
        )
        ax.text(
            105.0,
            sum_y + 3.6,
            summary_text,
            ha="center",
            va="center",
            fontsize=7.5,
            fontweight="bold",
            color="#1E293B",
        )

        sig_y = sum_y + 11.0
        sig_x = 165.0
        ax.text(sig_x, sig_y, f"Surakarta, {_format_long_indonesian_date(printed_on)}", ha="center", va="center", fontsize=7.8, color="#0F172A")
        ax.text(sig_x, sig_y + 4.0, "Mengetahui,", ha="center", va="center", fontsize=7.8, color="#0F172A")
        ax.text(sig_x, sig_y + 8.0, "[Jabatan Pembimbing - Template]", ha="center", va="center", fontsize=7.5, style="italic", color="#475569")
        ax.text(sig_x, sig_y + 24.5, "( ________________________________ )", ha="center", va="center", fontsize=7.8, color="#0F172A")

    ax.plot([14.0, 196.0], [286.5, 286.5], color="#E2E8F0", linewidth=0.5)
    ax.text(
        14.0,
        290.0,
        "Sistem Presensi Magang - DPRD Kota Surakarta (Template PDF A4)",
        ha="left",
        va="center",
        fontsize=6.8,
        color="#64748B",
    )
    ax.text(
        196.0,
        290.0,
        f"Halaman {page_num} dari {total_pages}",
        ha="right",
        va="center",
        fontsize=6.8,
        color="#64748B",
    )


def generate_report_pdf(report: ParticipantReportData) -> bytes:
    """Bangun PDF A4 portrait dengan template kop surat dan maksimal 30 hari per lembar A4."""
    logo_img = None
    if LOGO_PATH.exists():
        try:
            logo_img = Image.open(LOGO_PATH).convert("RGBA")
        except Exception:
            logo_img = None

    chunks = [
        report.rows[i : i + ROWS_PER_A4_PAGE]
        for i in range(0, len(report.rows), ROWS_PER_A4_PAGE)
    ] or [[]]
    total_pages = len(chunks)
    printed_on = datetime.now(ZoneInfo(settings.timezone)).date()

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        for page_idx, page_rows in enumerate(chunks, start=1):
            fig = Figure(figsize=(A4_WIDTH_IN, A4_HEIGHT_IN), dpi=300)
            ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
            ax.set_xlim(0.0, A4_WIDTH_MM)
            ax.set_ylim(A4_HEIGHT_MM, 0.0)
            ax.axis("off")

            _draw_letterhead_template(ax, logo_img)
            _draw_participant_meta(ax, report, page_idx, total_pages)
            table_end_y = _draw_attendance_table(ax, page_rows)
            _draw_footer_and_signature(ax, report, table_end_y, page_idx, total_pages, printed_on)

            pdf.savefig(fig)
            fig.clear()

    buf.seek(0)
    return buf.getvalue()
