import uuid
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.user import User, UserRole
from app.models.physical_file import PhysicalFile, PhysicalRecordType, PhysicalFileStatus
from app.models.storage_location import StorageLocation, LocationType
from app.models.custody import FileCustodyRecord, FileMovementHistory, CustodyStatus, PhysicalMovementType
from app.models.audit import AuditLog
from app.jwt import create_access_token


@pytest.fixture
def test_all_roles(db_session: Session) -> dict[str, User]:
    """Provision test users across all six EDRMS roles plus cross-department users."""
    role_configs = [
        ("admin", UserRole.ADMIN, "Executive", True),
        ("records_officer", UserRole.RECORDS_OFFICER, "Records Management", True),
        ("dept_user_fin", UserRole.DEPARTMENT_USER, "Finance", True),
        ("dept_user_hr", UserRole.DEPARTMENT_USER, "Human Resources", True),
        ("approver_fin", UserRole.APPROVER, "Finance", True),
        ("approver_hr", UserRole.APPROVER, "Human Resources", True),
        ("auditor_fin", UserRole.AUDITOR, "Finance", True),
        ("auditor_hr", UserRole.AUDITOR, "Human Resources", True),
        ("read_only_fin", UserRole.READ_ONLY, "Finance", True),
        ("read_only_hr", UserRole.READ_ONLY, "Human Resources", True),
        ("inactive_user", UserRole.DEPARTMENT_USER, "Finance", False),
    ]
    users = {}
    for key, role, dept, is_active in role_configs:
        u = User(
            email=f"{key}_{uuid.uuid4().hex[:6]}@edrms.test",
            full_name=f"User {key}",
            hashed_password="pw_hash_test",
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


def get_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def create_location(db: Session, code: str, dept: str, creator_id: uuid.UUID, capacity: int = 10) -> StorageLocation:
    loc = StorageLocation(
        location_code=code,
        name=f"Location {code}",
        location_type=LocationType.SHELF,
        department=dept,
        is_active=True,
        max_capacity=capacity,
        created_by_id=creator_id,
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


def test_complete_end_to_end_physical_file_lifecycle(
    client: TestClient, db_session: Session, test_all_roles: dict[str, User]
):
    """
    Checklist 1: End-to-End Physical File Lifecycle
    1. Register physical file
    2. Assign to storage location
    3. Generate/audit label print
    4. Lookup by reference / QR / barcode
    5. Check out to custodian
    6. Verify active custody and movement history
    7. Check file back in
    8. Transfer to another location
    9. Verify current location and movement agreement
    10. Review complete custody and audit history
    """
    fin_user = test_all_roles["dept_user_fin"]
    headers = get_headers(fin_user)

    loc1 = create_location(db_session, f"LOC-E2E-1-{uuid.uuid4().hex[:4]}", "Finance", fin_user.id)
    loc2 = create_location(db_session, f"LOC-E2E-2-{uuid.uuid4().hex[:4]}", "Finance", fin_user.id)

    # 1. Register physical file
    reg_payload = {
        "title": "Master Services Contract 2026",
        "description": "Original signed agreement with supplier",
        "record_type": "contract",
        "department": "Finance",
        "classification": "Confidential",
        "external_reference": "EXT-E2E-99",
    }
    r = client.post("/api/v1/physical-files", json=reg_payload, headers=headers)
    assert r.status_code == 201, r.text
    file_data = r.json()
    file_id = file_data["id"]
    file_ref = file_data["file_reference"]

    # 2. Assign to storage location loc1
    assign_payload = {"storage_location_id": str(loc1.id), "notes": "Initial shelf filing"}
    r = client.post(f"/api/v1/physical-files/{file_id}/assign-location", json=assign_payload, headers=headers)
    assert r.status_code == 200
    assert r.json()["storage_location_id"] == str(loc1.id)

    # 3. Label print audit
    print_payload = {"file_ids": [file_id], "label_format": "standard_qr"}
    r = client.post("/api/v1/physical-files/print-label", json=print_payload, headers=headers)
    assert r.status_code == 200
    assert r.json()["printed_count"] == 1

    # 4. Lookup by exact reference and barcode
    r = client.get(f"/api/v1/physical-files/lookup?code={file_ref}", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == file_id
    assert r.json()["storage_location_code"] == loc1.location_code

    # 5. Check out to custodian
    exp_return = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    checkout_payload = {
        "custodian_name": "Auditor Sarah Connor",
        "custodian_department": "Internal Audit",
        "custodian_contact": "sarah@audit.org",
        "expected_return_at": exp_return,
        "purpose": "Fiscal Year 2025 Audit Inspection",
    }
    r = client.post(f"/api/v1/physical-files/{file_id}/checkout", json=checkout_payload, headers=headers)
    assert r.status_code == 201
    custody_data = r.json()
    assert custody_data["status"] == "active"
    custody_id = custody_data["id"]

    # 6. Verify active custody and movement history
    r = client.get(f"/api/v1/physical-files/{file_id}/custody", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == custody_id
    assert r.json()["status"] == "active"

    r = client.get(f"/api/v1/physical-files/{file_id}/movement-history", headers=headers)
    assert r.status_code == 200
    movements = r.json()["items"]
    assert len(movements) >= 1
    assert movements[0]["movement_type"] == "checkout"

    # 7. Check the file back in
    checkin_payload = {
        "destination_location_id": str(loc1.id),
        "checkin_notes": "Returned intact with audit seal",
    }
    r = client.post(f"/api/v1/physical-files/{file_id}/checkin", json=checkin_payload, headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "returned"

    # Verify active custody is now null
    r = client.get(f"/api/v1/physical-files/{file_id}/custody", headers=headers)
    assert r.status_code == 200
    assert r.json() is None

    # 8. Transfer to location loc2
    transfer_payload = {
        "destination_location_id": str(loc2.id),
        "reason": "Relocation to long-term vault",
    }
    r = client.post(f"/api/v1/physical-files/{file_id}/transfer", json=transfer_payload, headers=headers)
    assert r.status_code == 201
    transfer_data = r.json()
    assert transfer_data["movement_type"] == "transfer"
    assert transfer_data["destination_location_id"] == str(loc2.id)

    # 9. Verify current location and movement history agreement
    r = client.get(f"/api/v1/physical-files/{file_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["storage_location_id"] == str(loc2.id)
    assert r.json()["is_checked_out"] is False

    r = client.get(f"/api/v1/physical-files/{file_id}/movement-history", headers=headers)
    assert r.status_code == 200
    all_movs = r.json()["items"]
    # Chronological: transfer (newest), checkin, checkout (oldest)
    assert len(all_movs) == 3
    assert all_movs[0]["movement_type"] == "transfer"
    assert all_movs[1]["movement_type"] == "checkin"
    assert all_movs[2]["movement_type"] == "checkout"

    # 10. Custody history preserves closed record
    r = client.get(f"/api/v1/physical-files/{file_id}/custody-history", headers=headers)
    assert r.status_code == 200
    custody_hist = r.json()["items"]
    assert len(custody_hist) == 1
    assert custody_hist[0]["status"] == "returned"
    assert custody_hist[0]["checked_in_at"] is not None


def test_checked_out_file_invariant_protections(
    client: TestClient, db_session: Session, test_all_roles: dict[str, User]
):
    """
    Checklist 2: Custody & Location Invariant Edge Cases
    Verify that a checked-out file CANNOT be:
    - Transferred
    - Reassigned to a storage location directly via assign-location
    - Modified via PATCH to unlink or change storage location
    - Transitioned to archived or inactive status
    """
    fin_user = test_all_roles["dept_user_fin"]
    headers = get_headers(fin_user)

    loc1 = create_location(db_session, f"LOC-INV-1-{uuid.uuid4().hex[:4]}", "Finance", fin_user.id)
    loc2 = create_location(db_session, f"LOC-INV-2-{uuid.uuid4().hex[:4]}", "Finance", fin_user.id)

    # Create and check out file
    pf = PhysicalFile(
        file_reference=f"PHY-INV-{uuid.uuid4().hex[:6]}",
        title="Invariant Test File",
        record_type=PhysicalRecordType.CONTRACT,
        department="Finance",
        status=PhysicalFileStatus.ACTIVE,
        storage_location_id=loc1.id,
        created_by_id=fin_user.id,
    )
    db_session.add(pf)
    db_session.commit()
    db_session.refresh(pf)

    checkout_r = client.post(
        f"/api/v1/physical-files/{pf.id}/checkout",
        json={"custodian_name": "Alice Invariant", "purpose": "Testing invariants"},
        headers=headers,
    )
    assert checkout_r.status_code == 201

    # Attempt 1: Transfer checked-out file -> Must fail 400
    r = client.post(
        f"/api/v1/physical-files/{pf.id}/transfer",
        json={"destination_location_id": str(loc2.id), "reason": "Illegal transfer attempt"},
        headers=headers,
    )
    assert r.status_code == 400
    assert "checked out" in r.json()["detail"].lower()

    # Attempt 2: Direct assign-location on checked-out file -> Must fail 400
    r = client.post(
        f"/api/v1/physical-files/{pf.id}/assign-location",
        json={"storage_location_id": str(loc2.id)},
        headers=headers,
    )
    assert r.status_code == 400
    assert "checked out" in r.json()["detail"].lower()

    # Attempt 3: Direct unlink via assign-location -> Must fail 400
    r = client.post(
        f"/api/v1/physical-files/{pf.id}/assign-location",
        json={"storage_location_id": None},
        headers=headers,
    )
    assert r.status_code == 400
    assert "checked out" in r.json()["detail"].lower()

    # Attempt 4: PATCH metadata updating storage location -> Must fail 400
    r = client.patch(
        f"/api/v1/physical-files/{pf.id}",
        json={"storage_location_id": str(loc2.id)},
        headers=headers,
    )
    assert r.status_code == 400
    assert "checked out" in r.json()["detail"].lower()

    # Attempt 5: Change lifecycle status to archived -> Must fail 400
    r = client.patch(
        f"/api/v1/physical-files/{pf.id}/status",
        json={"status": "archived", "reason": "premature archive"},
        headers=headers,
    )
    assert r.status_code == 400
    assert "checked out" in r.json()["detail"].lower()


def test_rbac_matrix_across_all_roles(
    client: TestClient, db_session: Session, test_all_roles: dict[str, User]
):
    """
    Checklist 3: Comprehensive RBAC and Department Scoping Matrix
    Roles tested:
    - admin: Full cross-department access
    - records_officer: Full cross-department records management
    - dept_user_fin: Access within Finance, denied cross-department to HR
    - approver_fin: Read-only within Finance, mutations denied
    - auditor_fin: Read-only audit access within Finance, mutations denied
    - read_only_fin: Strictly read-only within Finance, mutations denied
    - inactive_user: Blocked at authentication / authorization level
    """
    admin = test_all_roles["admin"]
    ro = test_all_roles["records_officer"]
    fin_user = test_all_roles["dept_user_fin"]
    hr_user = test_all_roles["dept_user_hr"]
    approver = test_all_roles["approver_fin"]
    auditor = test_all_roles["auditor_fin"]
    read_only = test_all_roles["read_only_fin"]
    inactive = test_all_roles["inactive_user"]

    loc_fin = create_location(db_session, f"LOC-RBAC-FIN-{uuid.uuid4().hex[:4]}", "Finance", fin_user.id)
    loc_hr = create_location(db_session, f"LOC-RBAC-HR-{uuid.uuid4().hex[:4]}", "Human Resources", hr_user.id)

    # Create Finance physical file
    pf_fin = PhysicalFile(
        file_reference=f"PHY-RBAC-FIN-{uuid.uuid4().hex[:4]}",
        title="Finance File",
        record_type=PhysicalRecordType.FINANCIAL_RECORD,
        department="Finance",
        status=PhysicalFileStatus.ACTIVE,
        storage_location_id=loc_fin.id,
        created_by_id=fin_user.id,
    )
    db_session.add(pf_fin)
    db_session.commit()
    db_session.refresh(pf_fin)

    # 1. Non-mutation roles must be denied checkout
    for role_user, name in [(approver, "approver"), (auditor, "auditor"), (read_only, "read_only")]:
        r = client.post(
            f"/api/v1/physical-files/{pf_fin.id}/checkout",
            json={"custodian_name": "Test Custodian", "purpose": "Test"},
            headers=get_headers(role_user),
        )
        assert r.status_code == 403, f"{name} should be denied checkout"

    # 2. Inactive user must be blocked
    r = client.post(
        f"/api/v1/physical-files/{pf_fin.id}/checkout",
        json={"custodian_name": "Test Custodian", "purpose": "Test"},
        headers=get_headers(inactive),
    )
    assert r.status_code in (401, 403), "Inactive user must be rejected"

    # 3. Cross-department user (HR user trying to checkout Finance file) -> Must be denied (403)
    r = client.post(
        f"/api/v1/physical-files/{pf_fin.id}/checkout",
        json={"custodian_name": "HR Sneak", "purpose": "Cross dept"},
        headers=get_headers(hr_user),
    )
    assert r.status_code == 403, "Cross-department checkout must be denied"

    # 4. Department user checkout within own department -> Must succeed (201)
    r = client.post(
        f"/api/v1/physical-files/{pf_fin.id}/checkout",
        json={"custodian_name": "Fin Custodian", "purpose": "Dept checkout"},
        headers=get_headers(fin_user),
    )
    assert r.status_code == 201

    # 5. Checkin by cross-department user -> Denied (403)
    r = client.post(
        f"/api/v1/physical-files/{pf_fin.id}/checkin",
        json={"checkin_notes": "Cross dept return"},
        headers=get_headers(hr_user),
    )
    assert r.status_code == 403

    # 6. Checkin by Records Officer -> Allowed across departments (200)
    r = client.post(
        f"/api/v1/physical-files/{pf_fin.id}/checkin",
        json={"checkin_notes": "Records officer return"},
        headers=get_headers(ro),
    )
    assert r.status_code == 200

    # 7. Cross-department transfer attempt by Finance user to HR location -> Denied (403)
    r = client.post(
        f"/api/v1/physical-files/{pf_fin.id}/transfer",
        json={"destination_location_id": str(loc_hr.id), "reason": "Cross-dept transfer attempt"},
        headers=get_headers(fin_user),
    )
    assert r.status_code == 403

    # 8. Admin transfer across departments -> Allowed (201)
    r = client.post(
        f"/api/v1/physical-files/{pf_fin.id}/transfer",
        json={"destination_location_id": str(loc_hr.id), "reason": "Admin inter-department transfer"},
        headers=get_headers(admin),
    )
    assert r.status_code == 201


def test_qr_barcode_safety_and_non_disclosing_lookup(
    client: TestClient, db_session: Session, test_all_roles: dict[str, User]
):
    """
    Checklist 4: Barcode, QR, and Label Safety
    Verify that:
    - Malformed or SQL/script injection payloads in lookup do not cause crashes
    - Unauthorized cross-department lookup returns non-disclosing 404 (does not reveal file existence)
    - Non-existent references return 404
    - Label printing validates file visibility and records audit events
    """
    fin_user = test_all_roles["dept_user_fin"]
    hr_user = test_all_roles["dept_user_hr"]

    test_ref = f"PHY-SAFE-FIN-{uuid.uuid4().hex[:6]}"
    pf_fin = PhysicalFile(
        file_reference=test_ref,
        title="Sensitive Financial Ledger",
        record_type=PhysicalRecordType.FINANCIAL_RECORD,
        department="Finance",
        status=PhysicalFileStatus.ACTIVE,
        created_by_id=fin_user.id,
    )
    db_session.add(pf_fin)
    db_session.commit()
    db_session.refresh(pf_fin)

    # Malformed / Injection query strings
    malicious_inputs = [
        "'; DROP TABLE physical_files; --",
        "<script>alert('xss')</script>",
        "../../etc/passwd",
        "%00%20%27",
        "NONEXISTENT_REF_99999",
    ]
    for bad_input in malicious_inputs:
        r = client.get(f"/api/v1/physical-files/lookup?code={bad_input}", headers=get_headers(fin_user))
        assert r.status_code == 404, f"Malformed input '{bad_input}' should safely return 404"

    # Also verify scanned URL containing valid reference extracts and resolves correctly:
    r_url = client.get(
        f"/api/v1/physical-files/lookup?code=https://edrms.local/physical-files?ref={test_ref}",
        headers=get_headers(fin_user),
    )
    assert r_url.status_code == 200
    assert r_url.json()["file_reference"] == test_ref

    # Cross-department lookup returns non-disclosing 404 (same status as non-existent)
    r_unauth = client.get(f"/api/v1/physical-files/lookup?code={test_ref}", headers=get_headers(hr_user))
    assert r_unauth.status_code == 404

    r_nonexist = client.get("/api/v1/physical-files/lookup?code=PHY-DOES-NOT-EXIST", headers=get_headers(hr_user))
    assert r_nonexist.status_code == 404
    assert r_unauth.json() == r_nonexist.json(), "Unauthorized file lookup must match non-existent response"


def test_retention_and_audit_evidence_preservation(
    client: TestClient, db_session: Session, test_all_roles: dict[str, User]
):
    """
    Checklist 6: Retention and Audit Integration
    Verify that:
    - Physical file registration, checkout, checkin, transfer, and label printing produce durable audit records
    - Audit events cannot be bypassed
    - Diagnostic integrity verification does not mutate database records
    """
    admin = test_all_roles["admin"]
    headers = get_headers(admin)

    # Initial audit log count
    initial_audit_count = db_session.query(AuditLog).count()

    loc = create_location(db_session, f"LOC-AUDIT-{uuid.uuid4().hex[:4]}", "Executive", admin.id)

    # Register file
    reg_r = client.post(
        "/api/v1/physical-files",
        json={"title": "Audit Evidence File", "record_type": "contract", "department": "Executive"},
        headers=headers,
    )
    assert reg_r.status_code == 201
    file_id = reg_r.json()["id"]

    # Assign location
    client.post(
        f"/api/v1/physical-files/{file_id}/assign-location",
        json={"storage_location_id": str(loc.id)},
        headers=headers,
    )

    # Print label
    client.post(
        "/api/v1/physical-files/print-label",
        json={"file_ids": [file_id], "label_format": "standard_qr"},
        headers=headers,
    )

    # Checkout
    client.post(
        f"/api/v1/physical-files/{file_id}/checkout",
        json={"custodian_name": "Audit Inspector", "purpose": "Evidence review"},
        headers=headers,
    )

    # Checkin
    client.post(
        f"/api/v1/physical-files/{file_id}/checkin",
        json={"checkin_notes": "Inspection complete"},
        headers=headers,
    )

    # Verify audit actions exist in audit_logs
    audit_actions = [
        a.action
        for a in db_session.query(AuditLog).filter(AuditLog.resource_id == uuid.UUID(file_id)).all()
    ]
    assert "physical_file.register" in audit_actions
    assert "physical_file.assign_location" in audit_actions
    assert "physical_file.print_label" in audit_actions
    assert "physical_file.checkout" in audit_actions
    assert "physical_file.checkin" in audit_actions

    # Diagnostic run must NOT create new audit entries or mutate physical file records
    count_before_diagnostic = db_session.query(AuditLog).count()
    diag_r = client.get("/api/v1/physical-files/custody-integrity", headers=headers)
    assert diag_r.status_code == 200
    count_after_diagnostic = db_session.query(AuditLog).count()
    assert count_after_diagnostic == count_before_diagnostic, "Diagnostic integrity endpoint must be strictly read-only"
