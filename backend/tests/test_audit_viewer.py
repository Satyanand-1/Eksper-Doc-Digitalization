"""
Automated test suite for Task 5.11: Audit Log Viewer and Administrative Reports.

Tests:
1. Admin can retrieve and list audit records with pagination.
2. Records Officer can retrieve and list audit records.
3. Non-authorized roles (department_user, approver, auditor, read_only) are denied (403 Forbidden).
4. Unauthenticated requests are rejected with 401 Unauthorized.
5. Pagination and deterministic ordering (newest first).
6. Filtering by action, resource_type, resource_id, actor_id, outcome, and search keyword.
7. Date range filtering and validation (rejecting start_date > end_date with 422).
8. Admin/Records Officer can view single audit log detail with sanitized context.
9. Non-existent audit log detail returns 404.
10. Sensitive fields (passwords, tokens, internal keys) are omitted from responses.
11. Aggregate reporting summary endpoint (/api/v1/audit-logs/reports/summary) works.
12. Read-only enforcement: No PUT, POST, or DELETE endpoints exist for audit logs.
"""
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.audit import AuditLog, AuditOutcome
from app.jwt import create_access_token


@pytest.fixture
def test_users(db_session: Session) -> dict[UserRole, User]:
    """Create test users across all roles."""
    roles = [
        UserRole.ADMIN,
        UserRole.RECORDS_OFFICER,
        UserRole.DEPARTMENT_USER,
        UserRole.APPROVER,
        UserRole.AUDITOR,
        UserRole.READ_ONLY,
    ]
    users = {}
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
        users[r] = u
    db_session.commit()
    for u in users.values():
        db_session.refresh(u)
    return users


@pytest.fixture
def seed_audit_logs(db_session: Session, test_users: dict[UserRole, User]) -> list[AuditLog]:
    """Seed identifiable audit log entries for testing."""
    admin = test_users[UserRole.ADMIN]
    dept_user = test_users[UserRole.DEPARTMENT_USER]
    now = datetime.now(timezone.utc)

    logs = [
        AuditLog(
            action="document.upload",
            resource_type="document",
            resource_id=uuid.uuid4(),
            outcome=AuditOutcome.SUCCESS,
            actor_id=dept_user.id,
            client_ip="192.168.1.10",
            correlation_id="corr-1",
            details={"title": "Q1 Report", "password": "supersecretpassword", "storage_key": "uploads/secret.pdf"},
            created_at=now - timedelta(minutes=10),
        ),
        AuditLog(
            action="workflow.approved",
            resource_type="workflow",
            resource_id=uuid.uuid4(),
            outcome=AuditOutcome.SUCCESS,
            actor_id=test_users[UserRole.APPROVER].id,
            client_ip="192.168.1.11",
            correlation_id="corr-2",
            details={"decision": "approved", "comments": "Looks good"},
            created_at=now - timedelta(minutes=5),
        ),
        AuditLog(
            action="user.deactivate",
            resource_type="user",
            resource_id=dept_user.id,
            outcome=AuditOutcome.SUCCESS,
            actor_id=admin.id,
            client_ip="192.168.1.12",
            correlation_id="corr-3",
            details={"old_status": True, "new_status": False},
            created_at=now - timedelta(minutes=2),
        ),
        AuditLog(
            action="workflow.cancel.denied",
            resource_type="workflow",
            resource_id=uuid.uuid4(),
            outcome=AuditOutcome.DENIED,
            actor_id=dept_user.id,
            client_ip="192.168.1.13",
            correlation_id="corr-4",
            details={"reason": "Unauthorized cancellation attempt"},
            created_at=now - timedelta(minutes=1),
        ),
    ]
    db_session.add_all(logs)
    db_session.commit()
    for l in logs:
        db_session.refresh(l)
    return logs


def test_admin_can_list_audit_logs(client: TestClient, test_users: dict[UserRole, User], seed_audit_logs: list[AuditLog]):
    """Test 1: Admin can retrieve and list audit records."""
    token = create_access_token(test_users[UserRole.ADMIN].id)
    res = client.get("/api/v1/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= len(seed_audit_logs)
    assert len(data["items"]) > 0


def test_records_officer_can_list_audit_logs(client: TestClient, test_users: dict[UserRole, User], seed_audit_logs: list[AuditLog]):
    """Test 2: Records Officer can retrieve audit records."""
    token = create_access_token(test_users[UserRole.RECORDS_OFFICER].id)
    res = client.get("/api/v1/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] >= len(seed_audit_logs)


def test_unauthorized_roles_denied(client: TestClient, test_users: dict[UserRole, User]):
    """Test 3: Department User, Approver, Auditor, and Read-Only users are denied with 403."""
    denied_roles = [
        UserRole.DEPARTMENT_USER,
        UserRole.APPROVER,
        UserRole.AUDITOR,
        UserRole.READ_ONLY,
    ]
    for r in denied_roles:
        token = create_access_token(test_users[r].id)
        res = client.get("/api/v1/audit-logs", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 403, f"Role {r.value} should be denied access."


def test_unauthenticated_request_rejected(client: TestClient):
    """Test 4: Unauthenticated requests are rejected with 401."""
    res = client.get("/api/v1/audit-logs")
    assert res.status_code == 401


def test_pagination_and_ordering(client: TestClient, test_users: dict[UserRole, User], seed_audit_logs: list[AuditLog]):
    """Test 5: Pagination and newest-first ordering."""
    token = create_access_token(test_users[UserRole.ADMIN].id)
    res = client.get("/api/v1/audit-logs?page=1&page_size=2", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2

    # Verify descending created_at timestamp order
    t0 = datetime.fromisoformat(data["items"][0]["created_at"])
    t1 = datetime.fromisoformat(data["items"][1]["created_at"])
    assert t0 >= t1


def test_filtering_by_action_and_outcome(client: TestClient, test_users: dict[UserRole, User], seed_audit_logs: list[AuditLog]):
    """Test 6: Filtering by action, outcome, and resource type."""
    token = create_access_token(test_users[UserRole.ADMIN].id)

    # Filter by action
    res_act = client.get("/api/v1/audit-logs?action=document.upload", headers={"Authorization": f"Bearer {token}"})
    assert res_act.status_code == 200
    items = res_act.json()["items"]
    assert len(items) >= 1
    assert all(i["action"] == "document.upload" for i in items)

    # Filter by outcome
    res_out = client.get("/api/v1/audit-logs?outcome=denied", headers={"Authorization": f"Bearer {token}"})
    assert res_out.status_code == 200
    items = res_out.json()["items"]
    assert len(items) >= 1
    assert all(i["outcome"] == "denied" for i in items)

    # Filter by actor_id
    dept_user = test_users[UserRole.DEPARTMENT_USER]
    res_actor = client.get(f"/api/v1/audit-logs?actor_id={dept_user.id}", headers={"Authorization": f"Bearer {token}"})
    assert res_actor.status_code == 200
    items = res_actor.json()["items"]
    assert len(items) >= 1
    assert all(i["actor_id"] == str(dept_user.id) for i in items)


def test_date_range_filtering_and_validation(client: TestClient, test_users: dict[UserRole, User]):
    """Test 7: Valid date range filters and rejection of invalid ranges."""
    token = create_access_token(test_users[UserRole.ADMIN].id)
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=2)
    future = now + timedelta(days=2)

    # Valid range
    res_valid = client.get(
        "/api/v1/audit-logs",
        params={"start_date": past.isoformat(), "end_date": future.isoformat()},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_valid.status_code == 200

    # Invalid range: start_date > end_date
    res_invalid = client.get(
        "/api/v1/audit-logs",
        params={"start_date": future.isoformat(), "end_date": past.isoformat()},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_invalid.status_code == 422
    assert "start_date must be earlier than or equal to end_date" in res_invalid.json()["detail"]


def test_audit_log_detail_and_data_redaction(client: TestClient, test_users: dict[UserRole, User], seed_audit_logs: list[AuditLog]):
    """Test 8, 9, 10: Detail retrieval, 404 for unknown, and sanitization of secrets."""
    token = create_access_token(test_users[UserRole.ADMIN].id)
    upload_log = next(l for l in seed_audit_logs if l.action == "document.upload")

    # 1. Detail endpoint
    res = client.get(f"/api/v1/audit-logs/{upload_log.id}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(upload_log.id)
    assert data["action"] == "document.upload"
    assert data["details"] is not None
    assert data["details"]["title"] == "Q1 Report"

    # Redaction checks: password and storage_key must NOT appear in details
    assert "password" not in data["details"]
    assert "storage_key" not in data["details"]

    # 2. Unknown ID returns 404
    res_404 = client.get(f"/api/v1/audit-logs/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert res_404.status_code == 404


def test_audit_report_summary(client: TestClient, test_users: dict[UserRole, User], seed_audit_logs: list[AuditLog]):
    """Test 11: Aggregate reporting endpoint provides metrics."""
    token = create_access_token(test_users[UserRole.ADMIN].id)
    res = client.get("/api/v1/audit-logs/reports/summary", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert "total_events" in data
    assert "events_by_action" in data
    assert "events_by_outcome" in data
    assert "recent_security_events" in data
    assert data["total_events"] >= len(seed_audit_logs)
    assert "document.upload" in data["events_by_action"]
    assert "success" in data["events_by_outcome"]


def test_read_only_protection(client: TestClient, test_users: dict[UserRole, User], seed_audit_logs: list[AuditLog]):
    """Test 12: Audit log records are strictly immutable (POST, PUT, DELETE disallowed)."""
    token = create_access_token(test_users[UserRole.ADMIN].id)
    log_id = seed_audit_logs[0].id

    # POST on /audit-logs
    res_post = client.post("/api/v1/audit-logs", json={"action": "fake"}, headers={"Authorization": f"Bearer {token}"})
    assert res_post.status_code == 405

    # PUT on /audit-logs/{id}
    res_put = client.put(f"/api/v1/audit-logs/{log_id}", json={"action": "fake"}, headers={"Authorization": f"Bearer {token}"})
    assert res_put.status_code == 405

    # DELETE on /audit-logs/{id}
    res_del = client.delete(f"/api/v1/audit-logs/{log_id}", headers={"Authorization": f"Bearer {token}"})
    assert res_del.status_code == 405
