import pytest
import uuid
from datetime import timedelta
import jwt
from fastapi.testclient import TestClient
from app.main import app
from app.models.user import User, UserRole
from app.security import hash_password
from app.database import SessionLocal
from app.jwt import create_access_token
from app.config import settings

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client

@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()

@pytest.fixture
def active_user(db):
    """Fixture providing an active registered test user."""
    unique_email = f"active_{uuid.uuid4().hex[:8]}@example.com"
    raw_password = "SecurePassword123!"
    user = User(
        email=unique_email,
        full_name="Active Test User",
        hashed_password=hash_password(raw_password),
        department="Finance",
        role=UserRole.DEPARTMENT_USER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    user_data = {
        "user": user,
        "email": unique_email,
        "password": raw_password,
    }
    yield user_data

    # Cleanup
    db.delete(user)
    db.commit()

@pytest.fixture
def inactive_user(db):
    """Fixture providing an inactive registered test user."""
    unique_email = f"inactive_{uuid.uuid4().hex[:8]}@example.com"
    raw_password = "InactivePassword123!"
    user = User(
        email=unique_email,
        full_name="Inactive User",
        hashed_password=hash_password(raw_password),
        department="Operations",
        role=UserRole.READ_ONLY,
        is_active=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    user_data = {
        "user": user,
        "email": unique_email,
        "password": raw_password,
    }
    yield user_data

    # Cleanup
    db.delete(user)
    db.commit()

# --- Login Endpoint Tests ---

def test_login_success(client, active_user):
    """Verify valid credentials return 200 with Bearer JWT token."""
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": active_user["email"],
            "password": active_user["password"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 15 * 60
    # Ensure sensitive fields are never in response
    assert "argon2" not in response.text
    assert "hashed_password" not in response.text

def test_login_incorrect_password(client, active_user):
    """Verify incorrect password returns 401 with generic error."""
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": active_user["email"],
            "password": "WrongPassword456!",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"

def test_login_nonexistent_user(client):
    """Verify nonexistent user returns 401 with identical generic error (no user enumeration)."""
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent_random_user@example.com",
            "password": "SomePassword123!",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"

def test_login_inactive_user(client, inactive_user):
    """Verify inactive user cannot log in and receives 401."""
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": inactive_user["email"],
            "password": inactive_user["password"],
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "User account is inactive"

def test_login_email_case_insensitivity(client, active_user):
    """Verify email login is normalized and case-insensitive."""
    upper_email = active_user["email"].upper()
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": upper_email,
            "password": active_user["password"],
        },
    )
    assert response.status_code == 200
    assert "access_token" in response.json()

# --- Current User Profile (/api/v1/auth/me) Tests ---

def test_get_current_user_profile_success(client, active_user):
    """Verify authenticated user can retrieve their profile with bearer token."""
    login_resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": active_user["email"],
            "password": active_user["password"],
        },
    )
    token = login_resp.json()["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == active_user["email"]
    assert data["full_name"] == "Active Test User"
    assert data["department"] == "Finance"
    assert data["role"] == "department_user"
    assert data["is_active"] is True
    assert "id" in data
    # Ensure sensitive hashes are not exposed
    assert "hashed_password" not in data
    assert "argon2" not in response.text

def test_get_current_user_missing_token(client):
    """Verify request without Authorization header returns 401."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401

def test_get_current_user_malformed_token(client):
    """Verify malformed bearer token returns 401."""
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not_a_valid_jwt_token_string"},
    )
    assert response.status_code == 401

def test_get_current_user_invalid_signature(client, active_user):
    """Verify token signed with wrong secret key is rejected with 401."""
    forged_token = jwt.encode(
        {"sub": str(active_user["user"].id), "exp": 9999999999, "type": "access", "iat": 1000},
        "wrong_fraudulent_secret_key_1234567890",
        algorithm="HS256",
    )
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {forged_token}"},
    )
    assert response.status_code == 401

def test_get_current_user_expired_token(client, active_user):
    """Verify expired token returns 401."""
    # Issue token that expired 1 hour ago
    expired_token = create_access_token(
        user_id=active_user["user"].id,
        expires_delta=timedelta(hours=-1),
    )
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401

def test_get_current_user_missing_required_claims(client, active_user):
    """Verify token missing 'sub' or 'type' claim is rejected."""
    # Token missing 'sub'
    bad_payload_token = jwt.encode(
        {"exp": 9999999999, "iat": 1000, "type": "access"},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {bad_payload_token}"},
    )
    assert response.status_code == 401

def test_get_current_user_deleted_or_nonexistent_user(client):
    """Verify valid token for a deleted/nonexistent user ID returns 401."""
    nonexistent_user_id = uuid.uuid4()
    token = create_access_token(user_id=nonexistent_user_id)

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401

def test_get_current_user_deactivated_after_token_issued(client, db, active_user):
    """Verify token is rejected if user is deactivated after token was issued."""
    # 1. Login to get token
    login_resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": active_user["email"],
            "password": active_user["password"],
        },
    )
    token = login_resp.json()["access_token"]

    # 2. Deactivate user in DB
    user = active_user["user"]
    user.is_active = False
    db.commit()

    # 3. Access endpoint with previously valid token
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "User account is inactive"

    # Restore user active status for fixture cleanup
    user.is_active = True
    db.commit()
