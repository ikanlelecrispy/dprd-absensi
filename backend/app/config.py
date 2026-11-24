from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database ---
    database_url: str = "postgresql+psycopg2://dprd_user:password@localhost:5432/absensi_dprd"

    # --- Security ---
    # Generate: python -c "import secrets; print(secrets.token_hex(32))"
    secret_key: str = "GANTI-INI-WAJIB"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 jam (satu hari kerja)

    # Fernet key untuk enkripsi embedding
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    embedding_encryption_key: str = "GANTI-INI-WAJIB"

    # --- Face Recognition ---
    similarity_threshold: float = 0.50
    # Tolak enrollment jika wajah baru mirip > ini dengan yang sudah terdaftar
    duplicate_enrollment_threshold: float = 0.70
    liveness_threshold: float = 0.80
    attendance_cooldown_minutes: int = 5
    max_face_fail_before_fallback: int = 5

    # InsightFace config
    insightface_model: str = "buffalo_sc"
    face_det_size: int = 320  # Input size deteksi — 320 cukup untuk CPU

    # Zona waktu server
    timezone: str = "Asia/Jakarta"

    # --- Storage ---
    evidence_photo_path: str = "./data/evidence_photos"
    enrollment_temp_path: str = "./data/enrollment_temp"
    evidence_retention_days: int = 90

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Origins yang diizinkan CORS (comma-separated)
    # Contoh: "https://192.168.1.20,http://localhost:3000"
    allowed_origins: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    # --- Kiosk Security ---
    # Set False hanya saat development, selalu True di produksi
    device_auth_enabled: bool = True

    # Jam kerja normal (untuk flagging presensi di luar jam kerja)
    work_start_hour: int = 7   # 07:00 WIB
    work_end_hour: int = 17    # 17:00 WIB

    # Zona threshold suspicious (nilai antara threshold dan threshold+margin di-flag)
    suspicious_similarity_margin: float = 0.05
    suspicious_liveness_margin: float = 0.10


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings — instance tunggal sepanjang lifetime aplikasi.
    Cache di-invalidate jika diperlukan dengan: get_settings.cache_clear()
    """
    return Settings()
