from dataclasses import dataclass
import numpy as np


@dataclass
class QualityCheckResult:
    is_valid: bool
    face_count: int
    blur_score: float        # Laplacian variance: makin tinggi makin tajam
    brightness_score: float  # Rata-rata luminansi grayscale: 0 - 255
    message: str


class QualityChecker:
    """
    Validasi kualitas foto enrollment & presensi sebelum masuk inference embedding:
    1. Jumlah wajah: harus tepat 1 wajah
    2. Tingkat ketajaman (blur): menggunakan Laplacian variance
    3. Pencahayaan (brightness): memeriksa under-exposure dan over-exposure
    4. Ukuran bounding box wajah: memastikan wajah tidak terlalu jauh
    """
    def __init__(
        self,
        min_blur_score: float = 18.0,
        min_brightness: float = 35.0,
        max_brightness: float = 240.0,
        min_face_size_px: int = 60,
    ):
        self.min_blur_score = min_blur_score
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness
        self.min_face_size_px = min_face_size_px

    def check(self, image_bgr: np.ndarray, detected_faces: list) -> QualityCheckResult:
        """
        image_bgr: citra OpenCV format BGR (H, W, 3)
        detected_faces: list object face dari InsightFace
        """
        import cv2

        face_count = len(detected_faces)
        if face_count == 0:
            return QualityCheckResult(
                is_valid=False,
                face_count=0,
                blur_score=0.0,
                brightness_score=0.0,
                message="Wajah tidak terdeteksi. Posisikan wajah tepat di depan kamera.",
            )

        if face_count > 1:
            return QualityCheckResult(
                is_valid=False,
                face_count=face_count,
                blur_score=0.0,
                brightness_score=0.0,
                message=f"Terdeteksi {face_count} wajah. Pastikan hanya ada 1 orang di depan kamera.",
            )

        face = detected_faces[0]
        bbox = face.bbox.astype(int)  # [x1, y1, x2, y2]
        x1, y1, x2, y2 = max(0, bbox[0]), max(0, bbox[1]), min(image_bgr.shape[1], bbox[2]), min(image_bgr.shape[0], bbox[3])
        
        face_w = x2 - x1
        face_h = y2 - y1

        if face_w < self.min_face_size_px or face_h < self.min_face_size_px:
            return QualityCheckResult(
                is_valid=False,
                face_count=1,
                blur_score=0.0,
                brightness_score=0.0,
                message="Wajah terlalu jauh dari kamera. Silakan mendekat.",
            )

        # Crop area wajah untuk penilaian blur & brightness lokal
        face_roi = image_bgr[y1:y2, x1:x2]
        gray_roi = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)

        # Hitung blur (variansi Laplacian)
        laplacian_var = float(cv2.Laplacian(gray_roi, cv2.CV_64F).var())

        # Hitung brightness (mean intensity)
        mean_brightness = float(np.mean(gray_roi))

        if laplacian_var < self.min_blur_score:
            return QualityCheckResult(
                is_valid=False,
                face_count=1,
                blur_score=laplacian_var,
                brightness_score=mean_brightness,
                message=f"Foto buram / tidak fokus (skor {laplacian_var:.1f} < {self.min_blur_score}). Diam sejenak saat pengambilan.",
            )

        if mean_brightness < self.min_brightness:
            return QualityCheckResult(
                is_valid=False,
                face_count=1,
                blur_score=laplacian_var,
                brightness_score=mean_brightness,
                message=f"Pencahayaan terlalu gelap (skor {mean_brightness:.1f} < {self.min_brightness}). Tambahkan cahaya dari depan.",
            )

        if mean_brightness > self.max_brightness:
            return QualityCheckResult(
                is_valid=False,
                face_count=1,
                blur_score=laplacian_var,
                brightness_score=mean_brightness,
                message=f"Pencahayaan terlalu silau/terang (skor {mean_brightness:.1f} > {self.max_brightness}).",
            )

        return QualityCheckResult(
            is_valid=True,
            face_count=1,
            blur_score=laplacian_var,
            brightness_score=mean_brightness,
            message="Kualitas foto memenuhi standar.",
        )


quality_checker = QualityChecker()
