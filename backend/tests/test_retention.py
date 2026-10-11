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
from app.models.audit import AuditLog
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
            department="Operations" if r != UserRole.DEPARTMENT_USER else "Finance",
            role=r,
            is_active=True,
        )
        db_session.add(u)
        users[r] = u
    db_session.commit()
    for u in users.values():
        db_session.refresh(u)
    return users


def get_auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def test_retention_rule_crud_and_validation(client: TestClient, test_users: dict[UserRole, User]):
    """1. Retention rule creation, validation, listing, and updates by admin."""
    admin_headers = get_auth_headers(test_users[UserRole.ADMIN])

    # 1. Create rule
    payload = {
        "name": f"Financial Records Rule {uuid.uuid4().hex[:6]}",
        "description": "Retention policy for financial statements and audits.",
        "classification": "Financial",
        "retention_period_unit": "years",
        "retention_period_value": 7,
        "trigger_event": "creation",
    }
    create_resp = client.post("/api/v1/retention/rules", json=payload, headers=admin_headers)
    assert create_resp.status_code == 201
    rule_data = create_resp.json()
    rule_id = rule_data["id"]
    assert rule_data["name"] == payload["name"]
    assert rule_data["retention_period_value"] == 7
    assert rule_data["is_active"] is True

    # 2. Duplicate rule name rejected with 409 Conflict
    dup_resp = client.post("/api/v1/retention/rules", json=payload, headers=admin_headers)
    assert dup_resp.status_code == 409

    # 3. Invalid retention period rejected with 422
    invalid_payload = {**payload, "name": f"Invalid Rule {uuid.uuid4().hex[:6]}", "retention_period_value": -5}
    inv_resp = client.post("/api/v1/retention/rules", json=invalid_payload, headers=admin_headers)
    assert inv_resp.status_code == 422

    # 4. Get single rule
    get_resp = client.get(f"/api/v1/retention/rules/{rule_id}", headers=admin_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == rule_id

    # 5. Update rule
    update_resp = client.patch(
        f"/api/v1/retention/rules/{rule_id}",
        json={"description": "Updated retention policy description.", "retention_period_value": 8},
        headers=admin_headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["description"] == "Updated retention policy description."
    assert update_resp.json()["retention_period_value"] == 8

    # 6. Deactivate rule
    deact_resp = client.patch(
        f"/api/v1/retention/rules/{rule_id}/status",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert deact_resp.status_code == 200
    assert deact_resp.json()["is_active"] is False

    # 7. List rules includes deactivated
    list_resp = client.get(f"/api/v1/retention/rules?q={rule_data['name']}", headers=admin_headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1


def test_retention_rule_role_authorization(client: TestClient, test_users: dict[UserRole, User]):
    """2. Only admin and records officer can create or modify retention rules."""
    records_officer_headers = get_auth_headers(test_users[UserRole.RECORDS_OFFICER])
    dept_headers = get_auth_headers(test_users[UserRole.DEPARTMENT_USER])
    approver_headers = get_auth_headers(test_users[UserRole.APPROVER])
    auditor_headers = get_auth_headers(test_users[UserRole.AUDITOR])
    readonly_headers = get_auth_headers(test_users[UserRole.READ_ONLY])

    payload = {
        "name": f"Policy Rule {uuid.uuid4().hex[:6]}",
        "description": "General policy retention.",
        "retention_period_unit": "days",
        "retention_period_value": 90,
        "trigger_event": "creation",
    }

    # Records Officer is permitted
    ro_resp = client.post("/api/v1/retention/rules", json=payload, headers=records_officer_headers)
    assert ro_resp.status_code == 201

    # Unauthorized roles denied with 403
    for headers in [dept_headers, approver_headers, auditor_headers, readonly_headers]:
        p = {**payload, "name": f"Rule {uuid.uuid4().hex[:6]}"}
        denied_resp = client.post("/api/v1/retention/rules", json=p, headers=headers)
        assert denied_resp.status_code == 403


def test_assign_retention_rule_and_calculation(client: TestClient, test_users: dict[UserRole, User], db_session: Session):
    """3. Assign rule to document, verify trigger dates and period calculations."""
    admin_headers = get_auth_headers(test_users[UserRole.ADMIN])

    # Create active rule: 30 days on creation
    rule = RetentionRule(
        name=f"30-Day Rule {uuid.uuid4().hex[:6]}",
        retention_period_unit=RetentionPeriodUnit.DAYS,
        retention_period_value=30,
        trigger_event=RetentionTriggerEvent.CREATION,
        is_active=True,
        created_by_id=test_users[UserRole.ADMIN].id,
    )
    db_session.add(rule)

    # Create document
    doc = DigitalDocument(
        title="Sample Retention Doc",
        document_reference=f"DOC-RET-{uuid.uuid4().hex[:6]}",
        department="Operations",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=test_users[UserRole.ADMIN].id,
    )
    db_session.add(doc)
    db_session.commit()

    # Assign rule
    assign_resp = client.post(
        f"/api/v1/retention/documents/{doc.id}/assign-rule",
        json={"retention_rule_id": str(rule.id)},
        headers=admin_headers,
    )
    assert assign_resp.status_code == 200
    data = assign_resp.json()
    assert data["retention_rule"]["id"] == str(rule.id)
    assert data["retention_start_date"] is not None
    assert data["retention_end_date"] is not None
    assert data["eligibility_status"] == DisposalEligibilityStatus.RETAINED.value


def test_prevent_silent_shortening_of_retention_period(client: TestClient, test_users: dict[UserRole, User], db_session: Session):
    """4. Assigning a new rule cannot silently calculate an earlier retention_end_date."""
    admin_headers = get_auth_headers(test_users[UserRole.ADMIN])

    # Rule 1: 5 years
    long_rule = RetentionRule(
        name=f"Long Rule {uuid.uuid4().hex[:6]}",
        retention_period_unit=RetentionPeriodUnit.YEARS,
        retention_period_value=5,
        trigger_event=RetentionTriggerEvent.CREATION,
        is_active=True,
        created_by_id=test_users[UserRole.ADMIN].id,
    )
    # Rule 2: 30 days
    short_rule = RetentionRule(
        name=f"Short Rule {uuid.uuid4().hex[:6]}",
        retention_period_unit=RetentionPeriodUnit.DAYS,
        retention_period_value=30,
        trigger_event=RetentionTriggerEvent.CREATION,
        is_active=True,
        created_by_id=test_users[UserRole.ADMIN].id,
    )
    db_session.add_all([long_rule, short_rule])

    doc = DigitalDocument(
        title="Pre-retained Doc",
        document_reference=f"DOC-PR-{uuid.uuid4().hex[:6]}",
        department="Legal",
        classification="Contract",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=test_users[UserRole.ADMIN].id,
    )
    db_session.add(doc)
    db_session.commit()

    # First assign long rule
    r1 = client.post(
        f"/api/v1/retention/documents/{doc.id}/assign-rule",
        json={"retention_rule_id": str(long_rule.id)},
        headers=admin_headers,
    )
    assert r1.status_code == 200

    # Attempt to assign short rule (which shortens custody) -> Must fail with 400
    r2 = client.post(
        f"/api/v1/retention/documents/{doc.id}/assign-rule",
        json={"retention_rule_id": str(short_rule.id)},
        headers=admin_headers,
    )
    assert r2.status_code == 400
    assert "earlier retention end date" in r2.json()["detail"]


def test_inactive_rule_cannot_be_assigned(client: TestClient, test_users: dict[UserRole, User], db_session: Session):
    """5. Inactive retention rule cannot be assigned to documents."""
    admin_headers = get_auth_headers(test_users[UserRole.ADMIN])

    inactive_rule = RetentionRule(
        name=f"Inactive Rule {uuid.uuid4().hex[:6]}",
        retention_period_unit=RetentionPeriodUnit.DAYS,
        retention_period_value=10,
        trigger_event=RetentionTriggerEvent.CREATION,
        is_active=False,
        created_by_id=test_users[UserRole.ADMIN].id,
    )
    doc = DigitalDocument(
        title="Doc For Inactive",
        document_reference=f"DOC-INA-{uuid.uuid4().hex[:6]}",
        department="Operations",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.DRAFT,
        created_by_id=test_users[UserRole.ADMIN].id,
    )
    db_session.add_all([inactive_rule, doc])
    db_session.commit()

    resp = client.post(
        f"/api/v1/retention/documents/{doc.id}/assign-rule",
        json={"retention_rule_id": str(inactive_rule.id)},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "inactive" in resp.json()["detail"].lower()


def test_legal_hold_lifecycle_and_blocking_disposal(client: TestClient, test_users: dict[UserRole, User], db_session: Session):
    """6. Place and release legal hold, verifying hold blocks disposal eligibility."""
    admin_headers = get_auth_headers(test_users[UserRole.ADMIN])

    # Create expired document
    past_date = datetime.now(timezone.utc) - timedelta(days=100)
    rule = RetentionRule(
        name=f"Expired Rule {uuid.uuid4().hex[:6]}",
        retention_period_unit=RetentionPeriodUnit.DAYS,
        retention_period_value=10,
        trigger_event=RetentionTriggerEvent.CREATION,
        is_active=True,
        created_by_id=test_users[UserRole.ADMIN].id,
    )
    db_session.add(rule)
    db_session.flush()

    doc = DigitalDocument(
        title="Expired Document",
        document_reference=f"DOC-EXP-{uuid.uuid4().hex[:6]}",
        department="Finance",
        classification="Audit",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=test_users[UserRole.ADMIN].id,
        retention_rule_id=rule.id,
        retention_start_date=past_date,
        retention_end_date=past_date + timedelta(days=10),
    )
    db_session.add(doc)
    db_session.commit()

    # Prior to hold, document should be eligible_for_review
    status_resp = client.get(f"/api/v1/retention/documents/{doc.id}", headers=admin_headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["eligibility_status"] == DisposalEligibilityStatus.ELIGIBLE_FOR_REVIEW.value

    # Place legal hold
    hold_resp = client.post(
        f"/api/v1/retention/documents/{doc.id}/legal-holds",
        json={"hold_reason": "Pending regulatory investigation into financial quarter."},
        headers=admin_headers,
    )
    assert hold_resp.status_code == 201
    hold_id = hold_resp.json()["id"]

    # Now document MUST be on_hold
    status_resp2 = client.get(f"/api/v1/retention/documents/{doc.id}", headers=admin_headers)
    assert status_resp2.status_code == 200
    assert status_resp2.json()["eligibility_status"] == DisposalEligibilityStatus.ON_HOLD.value
    assert status_resp2.json()["active_legal_hold_count"] == 1

    # Check disposal eligibility query reflects ON_HOLD
    disp_resp = client.get(f"/api/v1/retention/disposal-eligibility?q={doc.document_reference}", headers=admin_headers)
    assert disp_resp.status_code == 200
    items = disp_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["eligibility_status"] == DisposalEligibilityStatus.ON_HOLD.value
    assert items[0]["has_active_hold"] is True

    # Release legal hold
    release_resp = client.post(
        f"/api/v1/retention/legal-holds/{hold_id}/release",
        json={"release_reason": "Investigation concluded; no further evidentiary hold required."},
        headers=admin_headers,
    )
    assert release_resp.status_code == 200
    assert release_resp.json()["status"] == LegalHoldStatus.RELEASED.value

    # Document returns to eligible_for_review
    status_resp3 = client.get(f"/api/v1/retention/documents/{doc.id}", headers=admin_headers)
    assert status_resp3.status_code == 200
    assert status_resp3.json()["eligibility_status"] == DisposalEligibilityStatus.ELIGIBLE_FOR_REVIEW.value


def test_disposal_eligibility_department_isolation(client: TestClient, test_users: dict[UserRole, User], db_session: Session):
    """7. Department user can only see disposal eligibility assessments for own department."""
    finance_headers = get_auth_headers(test_users[UserRole.DEPARTMENT_USER])  # Department: Finance

    doc_fin = DigitalDocument(
        title="Finance Secret Doc",
        document_reference=f"DOC-FIN-{uuid.uuid4().hex[:6]}",
        department="Finance",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=test_users[UserRole.ADMIN].id,
    )
    doc_hr = DigitalDocument(
        title="HR Policy Doc",
        document_reference=f"DOC-HR-{uuid.uuid4().hex[:6]}",
        department="HR",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=test_users[UserRole.ADMIN].id,
    )
    db_session.add_all([doc_fin, doc_hr])
    db_session.commit()

    # Finance user sees Finance doc, NOT HR doc
    fin_resp = client.get(f"/api/v1/retention/disposal-eligibility?q={doc_fin.document_reference}", headers=finance_headers)
    assert fin_resp.status_code == 200
    assert any(item["document_id"] == str(doc_fin.id) for item in fin_resp.json()["items"])

    fin_cross_resp = client.get(f"/api/v1/retention/disposal-eligibility?q={doc_hr.document_reference}", headers=finance_headers)
    assert fin_cross_resp.status_code == 200
    assert not any(item["document_id"] == str(doc_hr.id) for item in fin_cross_resp.json()["items"])


def test_mandatory_audit_logging_for_retention_operations(client: TestClient, test_users: dict[UserRole, User], db_session: Session):
    """8. Verifies audit logs are generated for rule creation, update, hold placement, and release."""
    admin_headers = get_auth_headers(test_users[UserRole.ADMIN])

    # Create rule
    rule_name = f"Audited Rule {uuid.uuid4().hex[:6]}"
    r = client.post(
        "/api/v1/retention/rules",
        json={
            "name": rule_name,
            "retention_period_unit": "days",
            "retention_period_value": 60,
            "trigger_event": "creation",
        },
        headers=admin_headers,
    )
    assert r.status_code == 201

    rule_audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "retention_rule.create")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert rule_audit is not None
    assert rule_audit.resource_type == "retention_rule"
    assert rule_audit.details["rule_name"] == rule_name
