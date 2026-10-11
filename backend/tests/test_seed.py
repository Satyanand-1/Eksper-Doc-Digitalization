import pytest
import os
from unittest.mock import patch
from app.config import settings
from app.database import SessionLocal
from app.models.user import User, UserRole
from app.security import verify_password
from app.seed import (
    seed_test_users,
    remove_test_users,
    assert_development_environment,
    SEED_USER_SPECS,
    SeedAccountSpec,
)

@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()

def test_assert_development_environment_blocks_production():
    """Verify assert_development_environment raises RuntimeError if environment is production."""
    with patch.object(settings, "ENVIRONMENT", "production"):
        with pytest.raises(RuntimeError, match="strictly prohibited in production"):
            assert_development_environment()

def test_assert_development_environment_blocks_unknown_environment():
    """Verify assert_development_environment fails closed on unrecognized environment."""
    with patch.object(settings, "ENVIRONMENT", "staging"):
        with pytest.raises(RuntimeError, match="unrecognized environment"):
            assert_development_environment()

    with patch.object(settings, "ENVIRONMENT", ""):
        with pytest.raises(RuntimeError, match="strictly prohibited in production"):
            assert_development_environment()

def test_assert_development_environment_allows_dev_and_test():
    """Verify assert_development_environment passes in development or test."""
    with patch.object(settings, "ENVIRONMENT", "development"):
        assert_development_environment()

    with patch.object(settings, "ENVIRONMENT", "test"):
        assert_development_environment()

def test_seed_test_users_creates_all_six_roles(db):
    """Verify seed_test_users creates accounts representing all 6 EDRMS roles."""
    # Ensure starting clean
    remove_test_users(db)

    results = seed_test_users(db)
    assert len(results) == 6
    assert all(status == "created" for status in results.values())

    # Verify all 6 roles exist in PostgreSQL
    expected_roles = {
        UserRole.ADMIN,
        UserRole.RECORDS_OFFICER,
        UserRole.DEPARTMENT_USER,
        UserRole.APPROVER,
        UserRole.AUDITOR,
        UserRole.READ_ONLY,
    }
    seed_emails = [spec["default_email"] for spec in SEED_USER_SPECS]
    seeded_users = db.query(User).filter(User.email.in_(seed_emails)).all()
    found_roles = {u.role for u in seeded_users}
    assert found_roles == expected_roles

    # Verify passwords are properly hashed with Argon2id and match
    for spec in SEED_USER_SPECS:
        user = db.query(User).filter(User.email == spec["default_email"]).first()
        assert user is not None
        assert user.hashed_password.startswith("$argon2id$")
        assert verify_password(spec["default_password"], user.hashed_password) is True
        assert user.role == spec["role"]
        assert user.is_active is True

    # Cleanup
    remove_test_users(db)

def test_seed_test_users_idempotence(db):
    """Verify running seed_test_users twice does not duplicate accounts or raise error."""
    remove_test_users(db)

    # First run: created
    res1 = seed_test_users(db)
    assert all(status == "created" for status in res1.values())

    # Second run: skipped_existing
    res2 = seed_test_users(db)
    assert all(status == "skipped_existing" for status in res2.values())

    # Verify no duplicate user records exist
    for spec in SEED_USER_SPECS:
        count = db.query(User).filter(User.email == spec["default_email"]).count()
        assert count == 1

    # Cleanup
    remove_test_users(db)

def test_seed_test_users_does_not_overwrite_existing_account(db):
    """Verify seed_test_users preserves modified attributes of existing accounts."""
    remove_test_users(db)

    # Run seed to create accounts
    seed_test_users(db)

    # Modify an account's full_name
    admin_spec = SEED_USER_SPECS[0]
    admin = db.query(User).filter(User.email == admin_spec["default_email"]).first()
    admin.full_name = "Modified Admin Name"
    db.commit()

    # Rerun seed
    seed_test_users(db)

    # Verify full_name was NOT overwritten
    admin_refreshed = db.query(User).filter(User.email == admin_spec["default_email"]).first()
    assert admin_refreshed.full_name == "Modified Admin Name"

    # Cleanup
    remove_test_users(db)

def test_seeded_users_can_authenticate_and_return_roles(client, db):
    """Verify each seeded account can log in and retrieve its profile with the correct role."""
    remove_test_users(db)
    seed_test_users(db)

    for spec in SEED_USER_SPECS:
        # 1. Login
        login_resp = client.post(
            "/api/v1/auth/login",
            json={
                "email": spec["default_email"],
                "password": spec["default_password"],
            },
        )
        assert login_resp.status_code == 200, f"Login failed for {spec['default_email']}: {login_resp.text}"
        token = login_resp.json()["access_token"]

        # 2. Get profile /me
        me_resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["email"] == spec["default_email"]
        assert me_data["role"] == spec["role"].value

    # Cleanup
    remove_test_users(db)

def test_dynamic_role_user_factory(client, role_user_factory):
    """Verify dynamic role_user_factory creates and cleans up users across all 6 roles."""
    for role in UserRole:
        user_info = role_user_factory(role=role)
        login_resp = client.post(
            "/api/v1/auth/login",
            json={
                "email": user_info["email"],
                "password": user_info["password"],
            },
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json()["access_token"]

        me_resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["role"] == role.value
