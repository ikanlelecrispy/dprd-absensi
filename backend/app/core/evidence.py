from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import uuid
import cv2
import numpy as np


@dataclass(slots=True)
class EvidenceResult:
    """Hasil foto bukti terkompresi beserta path relatif dan tipe MIME."""

    relative_path: str
    data: bytes
    media_type: str


def detect_image_media_type(data: bytes, file_path: str = "") -> str:
    """Deteksi MIME type gambar dari magic header bytes atau ekstensi file."""
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"

    lower = file_path.lower()
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".png"):
        return "image/png"
    return "image/jpeg"


def crop_face_for_evidence(
    frame_bgr: np.ndarray,
    bbox: list[float] | tuple[float, float, float, float] | None = None,
) -> np.ndarray:
    """Potong area wajah secara proporsional agar wajah jelas dengan latar minimal."""
    if bbox is None or len(bbox) != 4:
        return frame_bgr

    h, w = frame_bgr.shape[:2]
    x1, y1, x2, y2 = (float(v) for v in bbox)
    bw = x2 - x1
    bh = y2 - y1
    if bw <= 1 or bh <= 1:
        return frame_bgr

    # Perluas kotak wajah menjadi potret persegi mencakup rambut, wajah penuh, dan kerah bahu
    side = max(bw, bh) * 1.9
    crop_w = min(int(round(side)), w)
    crop_h = min(int(round(side)), h)

    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0 + 0.04 * bh

    left = int(round(cx - crop_w / 2.0))
    top = int(round(cy - crop_h / 2.0))
    left = max(0, min(left, w - crop_w))
    top = max(0, min(top, h - crop_h))

    return frame_bgr[top : top + crop_h, left : left + crop_w]


def _resize_to_max_dim(img_bgr: np.ndarray, max_dim: int) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    longest = max(h, w)
    if longest <= max_dim:
        return img_bgr

    scale = max_dim / float(longest)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    return cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)


def compress_evidence_image(
    frame_bgr: np.ndarray,
    bbox: list[float] | tuple[float, float, float, float] | None = None,
    target_max_bytes: int = 8192,
) -> tuple[bytes, str, str]:
    """
    Kompres foto bukti menjadi WebP berukuran sangat kecil (<~8 KB) dengan wajah tetap jelas.
    Jika bbox tersedia, frame di-crop ke potret wajah (maks 224 px) agar bit terfokus pada wajah.
    """
    cropped = crop_face_for_evidence(frame_bgr, bbox)
    max_dim = 224 if (bbox is not None and len(bbox) == 4) else 280
    resized = _resize_to_max_dim(cropped, max_dim=max_dim)

    webp_qualities = (58, 50, 42)
    last_webp: bytes | None = None
    for q in webp_qualities:
        ok, buf = cv2.imencode(".webp", resized, [cv2.IMWRITE_WEBP_QUALITY, q])
        if not ok:
            break
        encoded = buf.tobytes()
        last_webp = encoded
        if len(encoded) <= target_max_bytes:
            return encoded, "webp", "image/webp"

    if last_webp is not None:
        return last_webp, "webp", "image/webp"

    jpeg_qualities = (58, 48, 38)
    last_jpg: bytes | None = None
    for q in jpeg_qualities:
        ok, buf = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, q])
        if ok:
            encoded = buf.tobytes()
            last_jpg = encoded
            if len(encoded) <= target_max_bytes:
                return encoded, "jpg", "image/jpeg"

    if last_jpg is None:
        raise ValueError("Gagal mengenkode foto bukti presensi.")
    return last_jpg, "jpg", "image/jpeg"


def save_attendance_evidence(
    frame_bgr: np.ndarray | None,
    checked_at: datetime,
    bbox: list[float] | tuple[float, float, float, float] | None = None,
    base_dir: Path | None = None,
) -> EvidenceResult | None:
    """Kompres foto bukti dan tulis salinan lokal (best-effort) untuk dikirim & disimpan ke DB."""
    if frame_bgr is None or frame_bgr.size == 0:
        return None

    encoded, ext, media_type = compress_evidence_image(frame_bgr, bbox=bbox)
    today_str = checked_at.strftime("%Y/%m/%d")
    filename = f"{uuid.uuid4()}.{ext}"
    rel_path = f"{today_str}/{filename}"

    if base_dir is not None:
        try:
            target_dir = base_dir / today_str
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / filename).write_bytes(encoded)
        except OSError:
            pass

    return EvidenceResult(relative_path=rel_path, data=encoded, media_type=media_type)
