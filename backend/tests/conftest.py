import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.database import SessionLocal
from app.models.user import User, UserRole
from app.security import hash_password

@pytest.fixture(scope="session")
def client():
    """Global TestClient instance for backend tests."""
    with TestClient(app) as test_client:
        yield test_client

@pytest.fixture
def db_session():
    """Transactional database session fixture that rolls back on completion."""
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()

def create_dynamic_test_user(
    db: Session,
    role: UserRole,
    is_active: bool = True,
    department: str | None = None,
    raw_password: str = "TestPassword123!",
) -> dict:
    """Helper creating an isolated test user and returning user record and credentials."""
    unique_email = f"test_{role.value}_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=unique_email,
        full_name=f"Dynamic {role.value.replace('_', ' ').title()} User",
        hashed_password=hash_password(raw_password),
        department=department or f"{role.value.title()} Dept",
        role=role,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "user": user,
        "email": unique_email,
        "password": raw_password,
        "role": role,
    }

@pytest.fixture
def role_user_factory(db_session):
    """
    Factory fixture to dynamically create test users for any of the 6 roles.
    Automatically deletes created users during fixture teardown.
    """
    created_users = []

    def _factory(role: UserRole, is_active: bool = True, raw_password: str = "TestPassword123!"):
        user_info = create_dynamic_test_user(
            db=db_session,
            role=role,
            is_active=is_active,
            raw_password=raw_password,
        )
        created_users.append(user_info["user"])
        return user_info

    yield _factory

    # Teardown
    for user in created_users:
        try:
            db_session.delete(user)
            db_session.commit()
        except Exception:
            db_session.rollback()
