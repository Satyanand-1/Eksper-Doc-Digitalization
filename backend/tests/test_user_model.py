import pytest
import uuid
from sqlalchemy.exc import IntegrityError
from app.models.user import User, UserRole
from app.security import hash_password
from app.database import SessionLocal

@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()

def test_user_model_instantiation():
    """Verify User model constructs with correct attributes and defaults."""
    pwd_hash = hash_password("Password123!")
    user = User(
        email="User.Test@Example.COM ",
        full_name="Test User",
        hashed_password=pwd_hash,
        department="Records",
        role=UserRole.RECORDS_OFFICER,
    )

    # Email normalization check
    assert user.email == "user.test@example.com"
    assert user.full_name == "Test User"
    assert user.hashed_password == pwd_hash
    assert user.department == "Records"
    assert user.role == UserRole.RECORDS_OFFICER
    assert user.is_active is True
    assert user.created_at is not None
    assert user.updated_at is not None

def test_user_email_validation_error():
    """Verify invalid email formats raise ValueError during model instantiation."""
    pwd_hash = hash_password("Password123!")
    with pytest.raises(ValueError, match="Invalid email address format"):
        User(
            email="invalid_email_without_at",
            full_name="Invalid Email User",
            hashed_password=pwd_hash,
        )

def test_user_role_enum_values():
    """Verify all 6 required roles are represented accurately."""
    expected_roles = {
        UserRole.ADMIN: "admin",
        UserRole.RECORDS_OFFICER: "records_officer",
        UserRole.DEPARTMENT_USER: "department_user",
        UserRole.APPROVER: "approver",
        UserRole.AUDITOR: "auditor",
        UserRole.READ_ONLY: "read_only",
    }
    for role_enum, role_str in expected_roles.items():
        assert role_enum.value == role_str

def test_user_database_persistence_and_email_uniqueness(db):
    """Verify persistence in PostgreSQL and enforcement of email uniqueness constraint."""
    unique_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    pwd_hash = hash_password("ValidPassword123!")

    user1 = User(
        email=unique_email,
        full_name="Primary User",
        hashed_password=pwd_hash,
        role=UserRole.ADMIN,
    )
    db.add(user1)
    db.commit()
    db.refresh(user1)

    assert user1.id is not None
    assert user1.email == unique_email

    # Attempt inserting duplicate user with identical email
    user2 = User(
        email=unique_email,
        full_name="Duplicate Email User",
        hashed_password=pwd_hash,
        role=UserRole.DEPARTMENT_USER,
    )
    db.add(user2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # Clean up test user
    db.delete(user1)
    db.commit()

def test_user_repr_excludes_password_hash():
    """Verify __repr__ does not expose password hash."""
    user = User(
        email="auditor@example.com",
        full_name="Audit Specialist",
        hashed_password=hash_password("AuditPassword123!"),
        role=UserRole.AUDITOR,
    )
    repr_str = repr(user)
    assert "auditor@example.com" in repr_str
    assert "argon2" not in repr_str
    assert "hashed_password" not in repr_str
