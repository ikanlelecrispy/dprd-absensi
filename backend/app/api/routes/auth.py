from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.auth import (
    COOKIE_NAME,
    create_access_token,
    get_current_admin,
    serialize_admin_user,
    verify_password,
)
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["Admin Auth"])


class AdminLoginRequest(BaseModel):
    identifier: str = Field(..., min_length=2, description="Email atau username admin")
    password: str = Field(..., min_length=1, description="Kata sandi akun admin")


@router.post("/login")
def login_admin(data: AdminLoginRequest, response: Response, db: Session = Depends(get_db)):
    """Autentikasi admin via email/username dan kata sandi bcrypt."""
    ident = data.identifier.strip().lower()
    user = (
        db.query(User)
        .filter(
            (func.lower(User.email) == ident) | (func.lower(User.username) == ident)
        )
        .first()
    )

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email/username atau kata sandi salah.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun admin ini sedang dinonaktifkan.",
        )

    user.last_login = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    token = create_access_token(user)
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=settings.access_token_expire_minutes * 60,
    )

    return {
        "success": True,
        "message": f"Selamat datang, {user.full_name}.",
        "user": serialize_admin_user(user),
    }


@router.post("/logout")
def logout_admin(response: Response):
    """Hapus cookie sesi admin."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"success": True, "message": "Berhasil keluar dari sesi admin."}


@router.get("/me")
def get_me(current_admin: User = Depends(get_current_admin)):
    """Periksa status sesi login admin yang sedang aktif."""
    return {"user": serialize_admin_user(current_admin)}
