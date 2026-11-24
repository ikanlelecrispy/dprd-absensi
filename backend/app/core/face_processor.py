from dataclasses import dataclass
import importlib
import os
import pkgutil
import shutil
import sys
import tempfile
from pathlib import Path
import numpy as np

from app.config import get_settings
from app.core.quality_checker import quality_checker, QualityCheckResult


def _ensure_skimage_lazy_fallback():
    """
    Vercel Python bundler menghapus file type stub (.pyi) dari _vendor,
    sehingga lazy_loader.attach_stub pada scikit-image gagal menemukan .pyi.
    Fallback ini memuat submodul/atribut langsung dari file .py/.so yang tersedia.
    """
    try:
        import lazy_loader
    except ImportError:
        return

    if getattr(lazy_loader.attach_stub, "_dprd_patched", False):
        return

    orig_attach_stub = lazy_loader.attach_stub

    def _safe_attach_stub(package_name: str, filename: str):
        try:
            return orig_attach_stub(package_name, filename)
        except ValueError:
            pkg_dir = Path(filename).parent
            submods = [m.name for m in pkgutil.iter_modules([str(pkg_dir)])]
            ordered = [s for s in submods if not s.startswith("_")] + [
                s for s in submods if s.startswith("_")
            ]

            def _getattr(name: str):
                pkg_mod = sys.modules.get(package_name)
                if name in submods:
                    val = importlib.import_module(f"{package_name}.{name}")
                    if pkg_mod is not None:
                        setattr(pkg_mod, name, val)
                    return val
                for sub in ordered:
                    try:
                        mod = importlib.import_module(f"{package_name}.{sub}")
                        if hasattr(mod, name):
                            val = getattr(mod, name)
                            if pkg_mod is not None:
                                setattr(pkg_mod, name, val)
                            return val
                    except Exception:
                        continue
                raise AttributeError(f"module {package_name!r} has no attribute {name!r}")

            return _getattr, (lambda: list(submods)), list(submods)

    _safe_attach_stub._dprd_patched = True
    lazy_loader.attach_stub = _safe_attach_stub


@dataclass
class ProcessedFaceResult:
    success: bool
    embedding: np.ndarray | None
    bbox: list[int] | None          # [x1, y1, x2, y2]
    landmarks: list | None
    quality: QualityCheckResult | None
    error_message: str | None


class FaceProcessor:
    """
    Wrapper untuk InsightFace (ArcFace).
    Menggunakan CPUExecutionProvider dengan onnxruntime dan model buffalo_sc.
    
    Tugas:
    1. Deteksi wajah & landmark alignment (RetinaFace/SCRFD di buffalo_sc)
    2. Ekstraksi 512-dim embedding (ArcFace)
    3. Integrasi QualityChecker sebelum menghasilkan embedding
    """
    def __init__(self):
        self.settings = get_settings()
        self._app = None
        self._is_initialized = False

    def initialize(self):
        """
        Lazy initialization model agar startup cepat dan hemat memori saat testing non-CV.
        """
        if self._is_initialized:
            return

        os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
        _ensure_skimage_lazy_fallback()

        import insightface
        from insightface.app import FaceAnalysis

        # Folder simpan model lokal (di Vercel serverless hanya tempdir /tmp yang writable)
        if os.getenv("VERCEL"):
            models_root = Path(tempfile.gettempdir()) / "models"
        else:
            models_root = Path(__file__).resolve().parent.parent.parent / "models"
        models_root.mkdir(parents=True, exist_ok=True)

        expected_dir = models_root / "models" / self.settings.insightface_model
        if expected_dir.exists() and not any(expected_dir.glob("*.onnx")):
            shutil.rmtree(expected_dir, ignore_errors=True)

        # Gunakan CPUExecutionProvider secara eksplisit
        app = FaceAnalysis(
            name=self.settings.insightface_model,
            root=str(models_root),
            providers=["CPUExecutionProvider"],
        )
        det_sz = self.settings.face_det_size
        app.prepare(ctx_id=-1, det_size=(det_sz, det_sz))
        
        self._app = app
        self._is_initialized = True

    def process_frame(self, image_bgr: np.ndarray, enforce_quality: bool = True) -> ProcessedFaceResult:
        """
        Proses satu frame gambar:
        1. Jalankan deteksi wajah InsightFace
        2. Periksa kualitas (blur, pencahayaan, jumlah wajah)
        3. Kembalikan 512-dim embedding jika lolos
        """
        self.initialize()
        faces = self._app.get(image_bgr)

        # Cek kualitas
        quality_res = quality_checker.check(image_bgr, faces)
        if enforce_quality and not quality_res.is_valid:
            bbox = faces[0].bbox.astype(int).tolist() if len(faces) == 1 else None
            return ProcessedFaceResult(
                success=False,
                embedding=None,
                bbox=bbox,
                landmarks=None,
                quality=quality_res,
                error_message=quality_res.message,
            )

        if len(faces) == 0:
            return ProcessedFaceResult(
                success=False,
                embedding=None,
                bbox=None,
                landmarks=None,
                quality=quality_res,
                error_message="Wajah tidak terdeteksi",
            )

        target_face = faces[0]
        bbox = target_face.bbox.astype(int).tolist()
        landmarks = target_face.kps.astype(int).tolist() if hasattr(target_face, "kps") else None

        return ProcessedFaceResult(
            success=True,
            embedding=target_face.embedding,
            bbox=bbox,
            landmarks=landmarks,
            quality=quality_res,
            error_message=None,
        )


face_processor = FaceProcessor()
