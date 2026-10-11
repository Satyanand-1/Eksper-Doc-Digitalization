"""
Automated test suite for Task 5.10: User Administration and Role Management.

Tests:
1. Admin can list users with pagination and filtering.
2. Non-admin roles (department_user, approver, auditor, read_only, records_officer) are denied access (403).
3. User listing search across name and email, role filter, department filter, active filter.
4. Admin can create a valid user with Argon2id hash.
5. Duplicate email registration is rejected with 409 Conflict.
6. Passwords are never returned in user creation or listing responses.
7. Role and department validation (e.g. required department for departmental roles).
8. Admin can update permitted user profile fields (name, department, role).
9. Unauthorized / arbitrary field changes (passwords, tokens, id) are rejected.
10. Admin can deactivate and reactivate a user.
11. Deactivated users cannot authenticate or access protected endpoints (401).
12. Self-deactivation prevention for administrators.
13. Last active administrator cannot be deactivated or demoted.
14. Mandatory audit log creation on user create, update, and status change.
15. Audit failure triggers transaction rollback.
16. Existing documents, workflow history, and notifications remain intact after deactivation.
"""
import uuid
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus
from app.models.workflow import ReviewWorkflow, ReviewAssignment, WorkflowState
from app.models.notification import Notification, NotificationType
from app.models.audit import AuditLog
from app.jwt import create_access_token
from app.services.audit import AuditWriteError
from app.security import verify_password


@pytest.fixture
def admin_user(db_session: Session) -> User:
    """Fixture providing a primary active admin user."""
    u = User(
        email=f"admin_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Primary Admin",
        hashed_password="hash",
        department="IT",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def non_admin_users(db_session: Session) -> dict[UserRole, User]:
    """Fixture providing users with each non-admin role."""
    roles = [
        UserRole.RECORDS_OFFICER,
        UserRole.DEPARTMENT_USER,
        UserRole.APPROVER,
        UserRole.AUDITOR,
        UserRole.READ_ONLY,
    ]
    users_by_role = {}
    for r in roles:
        u = User(
            email=f"{r.value}_{uuid.uuid4().hex[:6]}@example.com",
            full_name=f"User {r.value}",
            hashed_password="hash",
            department="Operations",
            role=r,
            is_active=True,
        )
        db_session.add(u)
        users_by_role[r] = u
    db_session.commit()
    for u in users_by_role.values():
        db_session.refresh(u)
    return users_by_role


def test_admin_can_list_users_paginated(client: TestClient, admin_user: User, db_session: Session):
    """Test 1: Admin can list users with pagination."""
    token = create_access_token(admin_user.id)
    response = client.get(
        "/api/v1/users?page=1&page_size=5",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "page" in data
    assert "total" in data
    assert data["page"] == 1
    assert data["page_size"] == 5
    assert len(data["items"]) <= 5
    # Verify no hashed_password in any returned item
    for item in data["items"]:
        assert "hashed_password" not in item
        assert "password" not in item


def test_non_admin_roles_denied_access(client: TestClient, non_admin_users: dict[UserRole, User]):
    """Test 2: Non-admin roles cannot access user administration endpoints."""
    for role, user in non_admin_users.items():
        token = create_access_token(user.id)
        # List users
        resp_list = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
        assert resp_list.status_code == 403, f"Role {role} should be denied on GET /api/v1/users"

        # Create user
        resp_create = client.post(
            "/api/v1/users",
            json={
                "email": f"test_{uuid.uuid4().hex[:6]}@example.com",
                "full_name": "Test User",
                "role": "department_user",
                "department": "Finance",
                "password": "ValidPassword123!",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp_create.status_code == 403, f"Role {role} should be denied on POST /api/v1/users"

        # Update user
        resp_update = client.patch(
            f"/api/v1/users/{user.id}",
            json={"full_name": "Hacked Name"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp_update.status_code == 403, f"Role {role} should be denied on PATCH /api/v1/users"

        # Status update
        resp_status = client.patch(
            f"/api/v1/users/{user.id}/status",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp_status.status_code == 403, f"Role {role} should be denied on PATCH /api/v1/users/status"


def test_user_listing_filtering_and_search(client: TestClient, admin_user: User, db_session: Session):
    """Test 3: User listing supports search, role, department, and active filters."""
    tag = uuid.uuid4().hex[:6]
    unique_name = f"SearchableName_{tag}"
    unique_dept = f"SpecificDept_{tag}"

    u1 = User(
        email=f"search_{tag}_1@example.com",
        full_name=unique_name,
        hashed_password="hash",
        department=unique_dept,
        role=UserRole.APPROVER,
        is_active=True,
    )
    u2 = User(
        email=f"search_{tag}_2@example.com",
        full_name="Another User",
        hashed_password="hash",
        department=unique_dept,
        role=UserRole.AUDITOR,
        is_active=False,
    )
    db_session.add_all([u1, u2])
    db_session.commit()

    token = create_access_token(admin_user.id)

    # 1. Search filter by name
    res_search = client.get(
        f"/api/v1/users?search={unique_name}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_search.status_code == 200
    items = res_search.json()["items"]
    assert any(item["full_name"] == unique_name for item in items)

    # 2. Filter by role
    res_role = client.get(
        f"/api/v1/users?role=approver&department={unique_dept}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_role.status_code == 200
    items = res_role.json()["items"]
    assert len(items) == 1
    assert items[0]["email"] == u1.email

    # 3. Filter by is_active
    res_inactive = client.get(
        f"/api/v1/users?is_active=false&department={unique_dept}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_inactive.status_code == 200
    items = res_inactive.json()["items"]
    assert len(items) == 1
    assert items[0]["email"] == u2.email


def test_admin_can_create_user(client: TestClient, admin_user: User, db_session: Session):
    """Test 4 & 6: Admin creates a user with Argon2id hashing; passwords never returned."""
    token = create_access_token(admin_user.id)
    email = f"newuser_{uuid.uuid4().hex[:6]}@example.com"
    raw_pass = "SecureInitPassword2026!"

    res = client.post(
        "/api/v1/users",
        json={
            "email": email,
            "full_name": "New Valid User",
            "role": "department_user",
            "department": "Finance",
            "password": raw_pass,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == email.lower()
    assert data["full_name"] == "New Valid User"
    assert data["role"] == "department_user"
    assert data["department"] == "Finance"
    assert data["is_active"] is True
    assert "password" not in data
    assert "hashed_password" not in data

    # Verify user in database has Argon2id hash that verifies
    db_user = db_session.query(User).filter(User.email == email.lower()).first()
    assert db_user is not None
    assert verify_password(raw_pass, db_user.hashed_password) is True


def test_duplicate_email_rejected(client: TestClient, admin_user: User):
    """Test 5: Duplicate email is rejected with 409 Conflict."""
    token = create_access_token(admin_user.id)
    email = f"dup_{uuid.uuid4().hex[:6]}@example.com"

    payload = {
        "email": email,
        "full_name": "First Instance",
        "role": "records_officer",
        "password": "ValidPassword123!",
    }
    res1 = client.post("/api/v1/users", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res1.status_code == 201

    # Attempt to create again with same email (even with case difference)
    payload["email"] = email.upper()
    res2 = client.post("/api/v1/users", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"]


def test_department_required_for_departmental_roles(client: TestClient, admin_user: User):
    """Test 7: Missing department for departmental roles rejected with 422."""
    token = create_access_token(admin_user.id)

    # Department user without department
    res = client.post(
        "/api/v1/users",
        json={
            "email": f"nodept_{uuid.uuid4().hex[:6]}@example.com",
            "full_name": "No Dept User",
            "role": "department_user",
            "department": None,
            "password": "ValidPassword123!",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422
    assert "Department is required" in res.json()["detail"]

    # Approver without department
    res_appr = client.post(
        "/api/v1/users",
        json={
            "email": f"noapprdept_{uuid.uuid4().hex[:6]}@example.com",
            "full_name": "No Dept Approver",
            "role": "approver",
            "department": "",
            "password": "ValidPassword123!",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_appr.status_code == 422


def test_admin_can_update_user_fields(client: TestClient, admin_user: User, db_session: Session):
    """Test 8: Admin can update permitted user profile fields (name, department, role)."""
    token = create_access_token(admin_user.id)

    u = User(
        email=f"target_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Original Name",
        hashed_password="hash",
        department="Sales",
        role=UserRole.DEPARTMENT_USER,
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)

    res = client.patch(
        f"/api/v1/users/{u.id}",
        json={
            "full_name": "Updated Name",
            "department": "Marketing",
            "role": "records_officer",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["full_name"] == "Updated Name"
    assert data["department"] == "Marketing"
    assert data["role"] == "records_officer"


def test_unauthorized_field_changes_rejected(client: TestClient, admin_user: User, db_session: Session):
    """Test 9: Changing passwords or immutable fields via PATCH /users/{id} is disallowed."""
    token = create_access_token(admin_user.id)
    u = User(
        email=f"immutable_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Immutable Test",
        hashed_password="orig_hash",
        department="IT",
        role=UserRole.DEPARTMENT_USER,
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    orig_id = u.id

    res = client.patch(
        f"/api/v1/users/{u.id}",
        json={
            "id": str(uuid.uuid4()),
            "password": "HackedPassword123!",
            "hashed_password": "fake_hash",
            "email": "hacked@example.com",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    db_session.refresh(u)
    assert u.id == orig_id
    assert u.hashed_password == "orig_hash"


def test_activate_and_deactivate_user(client: TestClient, admin_user: User, db_session: Session):
    """Test 10 & 11: Admin can deactivate a user; deactivated user cannot authenticate."""
    token = create_access_token(admin_user.id)
    raw_pass = "LoginSecret123!"

    # Create active user
    create_res = client.post(
        "/api/v1/users",
        json={
            "email": f"auth_test_{uuid.uuid4().hex[:6]}@example.com",
            "full_name": "Auth Test User",
            "role": "records_officer",
            "password": raw_pass,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    user_id = create_res.json()["id"]
    user_email = create_res.json()["email"]

    # Verify user can log in
    login_res = client.post("/api/v1/auth/login", json={"email": user_email, "password": raw_pass})
    assert login_res.status_code == 200
    user_token = login_res.json()["access_token"]

    # Verify user can access /api/v1/auth/me
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {user_token}"})
    assert me_res.status_code == 200

    # Deactivate the user
    deact_res = client.patch(
        f"/api/v1/users/{user_id}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deact_res.status_code == 200
    assert deact_res.json()["is_active"] is False

    # Verify deactivated user cannot log in
    login_fail = client.post("/api/v1/auth/login", json={"email": user_email, "password": raw_pass})
    assert login_fail.status_code == 401

    # Verify already-issued token is now rejected with 401
    me_fail = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {user_token}"})
    assert me_fail.status_code == 401
    assert "inactive" in me_fail.json()["detail"].lower()

    # Reactivate the user
    react_res = client.patch(
        f"/api/v1/users/{user_id}/status",
        json={"is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert react_res.status_code == 200
    assert react_res.json()["is_active"] is True

    # User can log in again
    login_ok = client.post("/api/v1/auth/login", json={"email": user_email, "password": raw_pass})
    assert login_ok.status_code == 200


def test_self_deactivation_prevention(client: TestClient, admin_user: User):
    """Test 12: Admin cannot deactivate their own account."""
    token = create_access_token(admin_user.id)
    res = client.patch(
        f"/api/v1/users/{admin_user.id}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert "cannot deactivate their own account" in res.json()["detail"]


def test_last_active_administrator_safeguard(client: TestClient, db_session: Session):
    """Test 12 & 13: Last active administrator cannot be deactivated or demoted."""
    # Ensure only ONE active admin exists
    tag = uuid.uuid4().hex[:6]
    only_admin = User(
        email=f"sole_admin_{tag}@example.com",
        full_name="Sole Admin",
        hashed_password="hash",
        department="IT",
        role=UserRole.ADMIN,
        is_active=True,
    )
    # Deactivate or delete other admins in this test scope
    other_admins = db_session.query(User).filter(User.role == UserRole.ADMIN, User.is_active == True).all()
    for oa in other_admins:
        oa.is_active = False
    db_session.add(only_admin)
    db_session.commit()
    db_session.refresh(only_admin)

    # Create a secondary admin that we'll deactivate
    token_only_admin = create_access_token(only_admin.id)

    # 1. Attempt to demote sole admin to department_user
    demote_res = client.patch(
        f"/api/v1/users/{only_admin.id}",
        json={"role": "department_user", "department": "IT"},
        headers={"Authorization": f"Bearer {token_only_admin}"},
    )
    assert demote_res.status_code == 400
    assert "last active administrator" in demote_res.json()["detail"]

    # 2. Add second admin
    second_admin = User(
        email=f"second_admin_{tag}@example.com",
        full_name="Second Admin",
        hashed_password="hash",
        department="IT",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(second_admin)
    db_session.commit()

    # Now deactivating only_admin by second_admin should succeed
    token_second_admin = create_access_token(second_admin.id)
    deact_res = client.patch(
        f"/api/v1/users/{only_admin.id}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token_second_admin}"},
    )
    assert deact_res.status_code == 200

    # Now second_admin is the ONLY active admin. Attempting to deactivate second_admin via self fails with 400
    res_self = client.patch(
        f"/api/v1/users/{second_admin.id}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token_second_admin}"},
    )
    assert res_self.status_code == 400


def test_mandatory_audit_logging_and_rollback(client: TestClient, admin_user: User, db_session: Session):
    """Test 14 & 15: Admin actions create audit entries; audit failure triggers rollback."""
    token = create_access_token(admin_user.id)
    tag = uuid.uuid4().hex[:6]

    # 1. Normal user creation produces audit entry
    res = client.post(
        "/api/v1/users",
        json={
            "email": f"audited_{tag}@example.com",
            "full_name": "Audited User",
            "role": "records_officer",
            "password": "ValidPassword123!",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    created_id = uuid.UUID(res.json()["id"])

    audit_entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.resource_id == created_id, AuditLog.action == "user.create")
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.actor_id == admin_user.id
    assert audit_entry.outcome.value == "success"

    # 2. Mock audit failure and verify user creation rolls back
    fail_email = f"audit_fail_{tag}@example.com"
    with patch("app.api.v1.users.AuditService.log_from_request", side_effect=AuditWriteError("Simulated DB error")):
        fail_res = client.post(
            "/api/v1/users",
            json={
                "email": fail_email,
                "full_name": "Should Rollback",
                "role": "records_officer",
                "password": "ValidPassword123!",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert fail_res.status_code == 500

    # Verify user was NOT saved
    assert db_session.query(User).filter(User.email == fail_email).first() is None


def test_data_integrity_after_user_deactivation(client: TestClient, admin_user: User, db_session: Session):
    """Test 16: Documents, workflow history, and notifications remain intact after deactivation."""
    token = create_access_token(admin_user.id)
    tag = uuid.uuid4().hex[:6]

    # Create a user who creates a document, submits workflow, and receives notification
    author = User(
        email=f"author_{tag}@example.com",
        full_name="Author User",
        hashed_password="hash",
        department="Finance",
        role=UserRole.DEPARTMENT_USER,
        is_active=True,
    )
    approver = User(
        email=f"appr_{tag}@example.com",
        full_name="Approver User",
        hashed_password="hash",
        department="Finance",
        role=UserRole.APPROVER,
        is_active=True,
    )
    db_session.add_all([author, approver])
    db_session.commit()

    doc = DigitalDocument(
        document_reference=f"DOC-TEST-{tag}",
        title="Important Financial Audit",
        department="Finance",
        classification="OFFICIAL",
        mime_type="application/pdf",
        status=DocumentStatus.UNDER_REVIEW,
        created_by_id=author.id,
    )
    db_session.add(doc)
    db_session.flush()

    wf = ReviewWorkflow(
        document_id=doc.id,
        submitter_id=author.id,
        state=WorkflowState.PENDING,
        submission_comments="Initial test submission",
    )
    db_session.add(wf)
    db_session.flush()

    assignment = ReviewAssignment(
        workflow_id=wf.id,
        assigned_approver_id=approver.id,
    )
    db_session.add(assignment)

    notif = Notification(
        recipient_id=approver.id,
        notification_type=NotificationType.WORKFLOW_SUBMITTED,
        title="Review Needed",
        message="Please review financial audit.",
        document_id=doc.id,
        workflow_id=wf.id,
    )
    db_session.add(notif)
    db_session.commit()

    # Now admin deactivates the author
    deact_res = client.patch(
        f"/api/v1/users/{author.id}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deact_res.status_code == 200

    # Verify document, workflow, and notification records remain intact
    doc_check = db_session.query(DigitalDocument).filter(DigitalDocument.id == doc.id).first()
    assert doc_check is not None
    assert doc_check.created_by_id == author.id

    wf_check = db_session.query(ReviewWorkflow).filter(ReviewWorkflow.id == wf.id).first()
    assert wf_check is not None
    assert wf_check.submitter_id == author.id

    notif_check = db_session.query(Notification).filter(Notification.id == notif.id).first()
    assert notif_check is not None
    assert notif_check.recipient_id == approver.id
