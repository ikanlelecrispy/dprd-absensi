import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import get_settings

settings = get_settings()

is_vercel = bool(os.getenv("VERCEL"))
engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,         # Reconnect jika koneksi DB putus
    pool_size=2 if is_vercel else 5,
    max_overflow=3 if is_vercel else 10,
    echo=settings.debug,        # Log SQL di development
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency untuk database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
