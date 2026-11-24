from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,         # Reconnect jika koneksi DB putus
    pool_size=5,
    max_overflow=10,
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
