import uuid
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.document import DigitalDocument, DocumentStatus
from app.models.retention import (
    RetentionRule,
    LegalHold,
    RetentionPeriodUnit,
    RetentionTriggerEvent,
    LegalHoldStatus,
    DisposalEligibilityStatus,
)
from app.models.notification import Notification, NotificationType
from app.models.audit import AuditLog
from app.jwt import create_access_token


@pytest.fixture
def test_users(db_session: Session) -> dict[str, User]:
    """Create test users covering various roles and departments."""
    user_configs = [
        ("admin", UserRole.ADMIN, "Executive", True),
        ("records_officer", UserRole.RECORDS_OFFICER, "Records Management", True),
        ("dept_user_fin", UserRole.DEPARTMENT_USER, "Finance", True),
        ("dept_user_hr", UserRole.DEPARTMENT_USER, "Human Resources", True),
        ("approver", UserRole.APPROVER, "Finance", True),
        ("auditor_fin", UserRole.AUDITOR, "Finance", True),
        ("auditor_hr", UserRole.AUDITOR, "Human Resources", True),
        ("read_only_fin", UserRole.READ_ONLY, "Finance", True),
        ("inactive_admin", UserRole.ADMIN, "Executive", False),
        ("inactive_user", UserRole.DEPARTMENT_USER, "Finance", False),
    ]
    users = {}
    for key, role, dept, is_active in user_configs:
        u = User(
            email=f"{key}_{uuid.uuid4().hex[:6]}@example.com",
            full_name=f"User {key}",
            hashed_password="hashed_pw",
            department=dept,
            role=role,
            is_active=is_active,
        )
        db_session.add(u)
        users[key] = u
    db_session.commit()
    for u in users.values():
        db_session.refresh(u)
    return users


def get_auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def test_inactive_user_token_rejection(client: TestClient, test_users: dict[str, User]):
    """Ensure inactive users cannot access protected endpoints even with valid unexpired JWT."""
    inactive_headers = get_auth_headers(test_users["inactive_user"])
    
    # Check document listing
    res = client.get("/api/v1/documents", headers=inactive_headers)
    assert res.status_code == 401
    assert "User account is inactive" in res.json().get("detail", "")

    # Check retention rules listing
    res = client.get("/api/v1/retention/rules", headers=inactive_headers)
    assert res.status_code == 401
    assert "User account is inactive" in res.json().get("detail", "")

    # Inactive admin also rejected
    inactive_admin_headers = get_auth_headers(test_users["inactive_admin"])
    res = client.get("/api/v1/users", headers=inactive_admin_headers)
    assert res.status_code == 401
    assert "User account is inactive" in res.json().get("detail", "")


def test_invalid_and_expired_jwt_handling(client: TestClient):
    """Ensure malformed or expired JWT tokens are cleanly rejected with 401."""
    # Malformed token
    res = client.get("/api/v1/documents", headers={"Authorization": "Bearer not-a-valid-token"})
    assert res.status_code == 401
    assert "Could not validate credentials" in res.json().get("detail", "")

    # Expired token
    expired_token = create_access_token(uuid.uuid4(), expires_delta=timedelta(seconds=-60))
    res = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401
    assert "Could not validate credentials" in res.json().get("detail", "")


def test_cross_department_document_access_isolation(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """Ensure strict department isolation: Finance user cannot access HR document metadata, download, or preview."""
    # Create HR document
    hr_doc = DigitalDocument(
        title="HR Confidential Payroll 2026",
        document_reference=f"HR-DOC-{uuid.uuid4().hex[:6]}",
        department="Human Resources",
        classification="Confidential",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=test_users["dept_user_hr"].id,
    )
    db_session.add(hr_doc)
    db_session.commit()
    db_session.refresh(hr_doc)

    fin_user_headers = get_auth_headers(test_users["dept_user_fin"])

    # 1. Access HR doc metadata -> Non-disclosing 404
    res = client.get(f"/api/v1/documents/{hr_doc.id}", headers=fin_user_headers)
    assert res.status_code == 404

    # 2. Access HR doc download -> 403 Forbidden
    res = client.get(f"/api/v1/documents/{hr_doc.id}/versions/1/download", headers=fin_user_headers)
    assert res.status_code == 403

    # 3. Access HR doc preview -> Non-disclosing 404
    res = client.get(f"/api/v1/documents/{hr_doc.id}/versions/1/preview", headers=fin_user_headers)
    assert res.status_code == 404


def test_retention_classification_mismatch_prevention(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """Ensure retention rule targeted to Confidential cannot be assigned to Restricted document."""
    ro_headers = get_auth_headers(test_users["records_officer"])

    # 1. Create a Confidential retention rule
    rule_res = client.post(
        "/api/v1/retention/rules",
        headers=ro_headers,
        json={
            "name": f"Confidential Policy {uuid.uuid4().hex[:6]}",
            "retention_period_value": 5,
            "retention_period_unit": RetentionPeriodUnit.YEARS.value,
            "trigger_event": RetentionTriggerEvent.CREATION.value,
            "classification": "Confidential",
        },
    )
    assert rule_res.status_code == 201
    rule_id = rule_res.json()["id"]

    # 2. Create a Restricted document
    doc = DigitalDocument(
        title="Restricted Blueprint",
        document_reference=f"REST-DOC-{uuid.uuid4().hex[:6]}",
        department="Finance",
        classification="Restricted",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=test_users["dept_user_fin"].id,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    # 3. Attempt to assign Confidential rule to Restricted doc -> 400 Bad Request
    assign_res = client.post(
        f"/api/v1/retention/documents/{doc.id}/assign-rule",
        headers=ro_headers,
        json={"retention_rule_id": str(rule_id)},
    )
    assert assign_res.status_code == 400
    assert "does not match document classification" in assign_res.json()["detail"]


def test_disposal_eligibility_date_range_validation_and_filter(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """Ensure start_date > end_date returns 422, and valid range filters properly."""
    ro_headers = get_auth_headers(test_users["records_officer"])

    # Inverted date range -> 422
    res = client.get(
        "/api/v1/retention/disposal-eligibility?start_date=2026-12-31T00:00:00Z&end_date=2026-01-01T00:00:00Z",
        headers=ro_headers,
    )
    assert res.status_code == 422
    assert "start_date must be before or equal to end_date" in res.json()["detail"]

    # Valid date range -> 200
    res_valid = client.get(
        "/api/v1/retention/disposal-eligibility?start_date=2026-01-01T00:00:00Z&end_date=2026-12-31T00:00:00Z",
        headers=ro_headers,
    )
    assert res_valid.status_code == 200
    assert "items" in res_valid.json()


def test_notification_ownership_verification(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """Ensure a user cannot mark or mutate another user's notifications."""
    # Create notification for User A
    notif = Notification(
        recipient_id=test_users["dept_user_fin"].id,
        title="Finance Notification",
        message="Your report has been uploaded.",
        notification_type=NotificationType.WORKFLOW_SUBMITTED,
    )
    db_session.add(notif)
    db_session.commit()
    db_session.refresh(notif)

    # User B attempts to mark User A's notification as read -> 404 Not Found (object not found for this user)
    hr_headers = get_auth_headers(test_users["dept_user_hr"])
    res = client.post(f"/api/v1/notifications/{notif.id}/read", headers=hr_headers)
    assert res.status_code == 404

    # User A successfully marks it as read
    fin_headers = get_auth_headers(test_users["dept_user_fin"])
    res_ok = client.post(f"/api/v1/notifications/{notif.id}/read", headers=fin_headers)
    assert res_ok.status_code == 200
    assert res_ok.json()["is_read"] is True


def test_user_admin_and_ocr_role_enforcement(
    client: TestClient, test_users: dict[str, User]
):
    """Verify non-admin users are strictly forbidden from user admin and OCR operational endpoints."""
    ro_headers = get_auth_headers(test_users["records_officer"])
    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    # 1. Records Officer attempts to list users -> 403 Forbidden
    res = client.get("/api/v1/users", headers=ro_headers)
    assert res.status_code == 403

    # 2. Dept User attempts to create a user -> 403 Forbidden
    res = client.post(
        "/api/v1/users",
        headers=fin_headers,
        json={
            "email": "hacker@example.com",
            "full_name": "Hacker",
            "password": "Password123!",
            "role": "admin",
            "department": "Finance",
        },
    )
    assert res.status_code == 403

    # 3. Dept User attempts OCR retry -> 403 Forbidden
    dummy_job_id = uuid.uuid4()
    res = client.post(f"/api/v1/ocr/jobs/{dummy_job_id}/retry", headers=fin_headers)
    assert res.status_code == 403


def test_global_security_headers_enforcement(client: TestClient):
    """Verify standard security headers are present on API responses."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert res.headers.get("X-XSS-Protection") == "1; mode=block"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_production_settings_validation_safeguards():
    """Verify production security validation fails fast on insecure defaults."""
    from app.config import Settings
    import pytest

    # Fails if default weak secret key is used in production
    with pytest.raises(ValueError, match="JWT_SECRET_KEY must be a strong secret"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="dev_insecure_jwt_secret_key_change_in_production_min_32_bytes_len",
            ALLOWED_ORIGINS="https://edrms.example.com",
        )

    # Fails if CORS wildcard is used in production
    with pytest.raises(ValueError, match="ALLOWED_ORIGINS must not be '\\*'"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="super_strong_production_secret_key_min_32_chars!",
            ALLOWED_ORIGINS="*",
        )

