import pytest
from sqlalchemy import text
from app.config import settings
from app.database import engine, SessionLocal, Base, get_db

@pytest.fixture(scope="session")
def db_session():
    """Provides a database session for testing."""
    session = SessionLocal()
    yield session
    session.close()

def test_database_settings_loaded():
    """Verify database settings load correctly from environment."""
    assert settings.DATABASE_URL is not None
    assert "postgresql" in settings.DATABASE_URL
    assert settings.DB_POOL_SIZE >= 1
    assert settings.DB_MAX_OVERFLOW >= 0
    assert settings.DB_POOL_PRE_PING is True

def test_sqlalchemy_engine_connection():
    """Verify SQLAlchemy 2.x engine can connect to PostgreSQL."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1

def test_session_executes_query(db_session):
    """Verify SessionLocal executes a query and returns expected result."""
    result = db_session.execute(text("SELECT 'edrms_db_ok' AS check_val"))
    row = result.fetchone()
    assert row is not None
    assert row[0] == "edrms_db_ok"

def test_get_db_dependency_lifecycle():
    """Verify get_db dependency yields an active session and closes it."""
    gen = get_db()
    session = next(gen)
    assert session is not None
    assert session.is_active is True
    # Verify session can execute
    val = session.execute(text("SELECT 42")).scalar()
    assert val == 42
    
    # Complete generator and verify close
    with pytest.raises(StopIteration):
        next(gen)

def test_declarative_base_metadata():
    """Verify Base has a valid MetaData object configured."""
    assert Base.metadata is not None
