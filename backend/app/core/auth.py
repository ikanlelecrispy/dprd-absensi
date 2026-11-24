import uuid
from datetime import datetime, timedelta, timezone
import bcrypt
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.user import User
from app.db.session import get_db

COOKIE_NAME = "dprd_admin_session"
_DEV_JWT_FALLBACK = "DPRD_Surakarta_Dev_JWT_Secret_Key_2026"


def _get_jwt_secret() -> str:
    settings = get_settings()
    if not settings.secret_key or settings.secret_key.startswith("GANTI"):
        return _DEV_JWT_FALLBACK
    return settings.secret_key


def hash_password(plain_password: str) -> str:
    """Hash kata sandi menggunakan bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifikasi kata sandi plain dengan hash bcrypt."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user: User) -> str:
    """Buat JWT session token untuk admin."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict | None:
    """Decode dan verifikasi JWT token."""
    try:
        return jwt.decode(token, _get_jwt_secret(), algorithms=[get_settings().algorithm])
    except JWTError:
        return None


def serialize_admin_user(user: User) -> dict:
    """Serialisasi aman akun admin tanpa kolom kata sandi."""
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "last_login": user.last_login.strftime("%Y-%m-%d %H:%M WIB") if user.last_login else None,
        "created_at": user.created_at.strftime("%Y-%m-%d") if user.created_at else None,
    }


def get_current_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency proteksi endpoint admin lewat cookie HttpOnly atau Bearer token."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Silakan masuk terlebih dahulu untuk mengakses Dashboard Admin.",
        )

    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesi login telah kedaluwarsa. Silakan masuk kembali.",
        )

    try:
        user_uuid = uuid.UUID(payload["sub"])
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sesi tidak valid.",
        )

    user = db.query(User).filter(User.id == user_uuid).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Akun admin tidak ditemukan atau sedang dinonaktifkan.",
        )

    return user


def ensure_default_admin(db: Session) -> User | None:
    """Buat satu akun superadmin bawaan saat database users masih kosong."""
    if db.query(User).count() > 0:
        return None

    admin = User(
        username="admin",
        email="admin@dprd-surakarta.go.id",
        full_name="Administrator DPRD",
        role="superadmin",
        is_active=True,
        hashed_password=hash_password("AdminDPRD2026"),
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    print("\n[STARTUP] Akun admin awal dibuat: admin@dprd-surakarta.go.id (username: admin)")
    return admin
