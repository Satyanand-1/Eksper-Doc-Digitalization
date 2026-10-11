from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings

def normalize_database_url(url: str) -> str:
    """Normalize legacy postgres:// URLs to SQLAlchemy compatible format."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url

# Engine configured with pool pre-ping to verify active connections
engine = create_engine(
    normalize_database_url(settings.DATABASE_URL),
    pool_pre_ping=settings.DB_POOL_PRE_PING,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    echo=(settings.ENVIRONMENT == "development" and settings.LOG_LEVEL.lower() == "debug"),
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding a SQLAlchemy session.
    Guarantees the session is properly closed after request processing.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
