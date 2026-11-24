from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models.division import Division
from app.db.models.location import Location
from app.core.schedule import get_or_create_schedule
from app.core.auth import ensure_default_admin
from app.core.matcher import matcher
from app.db.models.leave_request import LeaveRequest
from app.api.routes import participants, enrollment, attendance, divisions, admin, locations, schedule, auth, leaves
from app.api.websocket import ws_router

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
EVIDENCE_DIR = BASE_DIR / "data" / "evidence_photos"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle Startup & Shutdown:
    1. Memastikan divisi default tersedia di DB.
    2. Memuat seluruh embedding aktif ke in-memory cache matcher.
    """
    db = SessionLocal()
    try:
        # 1. Pastikan ada divisi default
        div = db.query(Division).first()
        if not div:
            default_div = Division(
                name="Bagian Persidangan & Perundang-undangan",
                code="SIDANG",
                description="Divisi peserta magang DPRD",
                supervisor_name="Admin Resepsionis",
                is_active=True,
            )
            db.add(default_div)
            db.commit()

        # 2. Pastikan ada lokasi default (nonaktif hingga admin mengaktifkan/menyesuaikan pin)
        loc = db.query(Location).first()
        if not loc:
            default_loc = Location(
                name="Gedung DPRD Kota Surakarta",
                address="Jl. Adi Sucipto No. 143, Surakarta",
                latitude=-7.5515,
                longitude=110.7858,
                radius_meters=100,
                is_active=False,
            )
            db.add(default_loc)
            db.commit()

        # 3. Pastikan ada jadwal presensi default (06:00-09:00 & 14:00-16:00)
        get_or_create_schedule(db)

        # 3b. Pastikan kolom keterlambatan & tabel izin harian tersedia
        db.execute(text("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS is_late BOOLEAN NOT NULL DEFAULT FALSE"))
        db.execute(text("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS late_minutes INTEGER NOT NULL DEFAULT 0"))
        db.commit()
        LeaveRequest.__table__.create(bind=db.get_bind(), checkfirst=True)

        # 3c. Pastikan minimal ada satu akun admin bawaan saat database masih kosong
        ensure_default_admin(db)

        # 4. Muat embedding ke RAM
        count = matcher.load_from_db(db)
        print(f"\n[STARTUP] In-memory FaceMatcher siap dengan {count} peserta aktif.")
    finally:
        db.close()

    yield
    print("[SHUTDOWN] Menutup aplikasi presensi.")


app = FastAPI(
    title="Sistem Presensi Wajah DPRD Surakarta",
    version="1.0.0",
    description="Backend Presensi Wajah Real-Time Berbasis Tablet Kiosk",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Saat produksi atur ke allowed_origins di .env
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(divisions.router, prefix="/api")
app.include_router(participants.router, prefix="/api")
app.include_router(enrollment.router, prefix="/api")
app.include_router(attendance.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(locations.router, prefix="/api")
app.include_router(schedule.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(leaves.router, prefix="/api")
app.include_router(ws_router)

# Mount Static Files (Frontend Kiosk & Admin Dashboard & Foto Bukti)
kiosk_dir = FRONTEND_DIR / "kiosk"
if kiosk_dir.exists():
    app.mount("/kiosk", StaticFiles(directory=str(kiosk_dir), html=True), name="kiosk")

admin_dir = FRONTEND_DIR / "admin"
if admin_dir.exists():
    app.mount("/admin", StaticFiles(directory=str(admin_dir), html=True), name="admin")

EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/evidence", StaticFiles(directory=str(EVIDENCE_DIR)), name="evidence")


@app.get("/")
def root():
    """Redirect root ke halaman kiosk tablet."""
    return RedirectResponse(url="/kiosk/index.html")


@app.get("/izin")
def leave_page_shortcut():
    """Shortcut URL ramah untuk halaman izin harian mobile."""
    return RedirectResponse(url="/kiosk/izin.html")


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "active_participants_cached": len(matcher._index),
    }
