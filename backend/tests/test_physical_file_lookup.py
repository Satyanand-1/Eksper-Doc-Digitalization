"""
Tests for Task 6.4: Barcode/QR Identification, Physical File Search, and Label Generation.
Covers:
- Exact physical file reference lookup.
- External reference lookup.
- URL / deep-link scanned QR payload extraction and lookup.
- UUID identifier lookup.
- Inaccessible file lookup (non-disclosing 404).
- Malformed and non-existent reference lookup (404).
- Department isolation enforcement.
- Registry search with classification and custody_state filters.
- Label printing audit logging endpoint.
"""
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.physical_file import PhysicalFile, PhysicalRecordType, PhysicalFileStatus
from app.models.storage_location import StorageLocation, LocationType
from app.models.custody import FileCustodyRecord, CustodyStatus
from app.models.audit import AuditLog
from app.jwt import create_access_token


@pytest.fixture
def test_users(db_session: Session) -> dict[str, User]:
    """Provision test users across roles and departments."""
    configs = [
        ("admin", UserRole.ADMIN, "Executive", True),
        ("records_officer", UserRole.RECORDS_OFFICER, "Records Management", True),
        ("dept_user_fin", UserRole.DEPARTMENT_USER, "Finance", True),
        ("dept_user_hr", UserRole.DEPARTMENT_USER, "Human Resources", True),
        ("approver_fin", UserRole.APPROVER, "Finance", True),
        ("auditor_fin", UserRole.AUDITOR, "Finance", True),
        ("read_only_fin", UserRole.READ_ONLY, "Finance", True),
        ("inactive_user", UserRole.DEPARTMENT_USER, "Finance", False),
    ]
    users = {}
    for key, role, dept, is_active in configs:
        u = User(
            email=f"{key}_{uuid.uuid4().hex[:6]}@example.com",
            full_name=f"User {key}",
            hashed_password="pw_hash",
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


@pytest.fixture
def setup_lookup_environment(db_session: Session, test_users: dict[str, User]):
    """Set up storage locations and test physical files across departments."""
    u_suffix = uuid.uuid4().hex[:6].upper()
    fin_loc = StorageLocation(
        name="Finance Archive 1",
        location_code=f"FIN-ARCH-{u_suffix}",
        location_type=LocationType.CABINET,
        department="Finance",
        is_active=True,
        created_by_id=test_users["admin"].id,
    )
    hr_loc = StorageLocation(
        name="HR Room 101",
        location_code=f"HR-RM-{u_suffix}",
        location_type=LocationType.ROOM,
        department="Human Resources",
        is_active=True,
        created_by_id=test_users["admin"].id,
    )
    db_session.add_all([fin_loc, hr_loc])
    db_session.commit()

    file_fin = PhysicalFile(
        file_reference=f"PHY-2026-FIN{u_suffix}",
        title="Fiscal Tax Audit 2025",
        record_type=PhysicalRecordType.FINANCIAL_RECORD,
        department="Finance",
        classification="Confidential",
        status=PhysicalFileStatus.ACTIVE,
        storage_location_id=fin_loc.id,
        external_reference=f"BARCODE-FIN-{u_suffix}",
        created_by_id=test_users["dept_user_fin"].id,
    )

    file_hr = PhysicalFile(
        file_reference=f"PHY-2026-HR{u_suffix}",
        title="Senior Director Personnel File",
        record_type=PhysicalRecordType.PERSONNEL_FILE,
        department="Human Resources",
        classification="Restricted",
        status=PhysicalFileStatus.ACTIVE,
        storage_location_id=hr_loc.id,
        external_reference=f"QR-HR-DIR-{u_suffix}",
        created_by_id=test_users["admin"].id,
    )

    db_session.add_all([file_fin, file_hr])
    db_session.commit()

    return {
        "fin_loc": fin_loc,
        "hr_loc": hr_loc,
        "file_fin": file_fin,
        "file_hr": file_hr,
    }


def test_lookup_by_exact_reference(
    client: TestClient, test_users: dict[str, User], setup_lookup_environment: dict
):
    """1. Test successful lookup by exact physical file reference."""
    file_fin = setup_lookup_environment["file_fin"]
    headers = get_auth_headers(test_users["dept_user_fin"])

    res = client.get(f"/api/v1/physical-files/lookup?code={file_fin.file_reference}", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["id"] == str(file_fin.id)
    assert data["file_reference"] == file_fin.file_reference
    assert data["title"] == file_fin.title
    assert data["department"] == "Finance"


def test_lookup_by_external_reference(
    client: TestClient, test_users: dict[str, User], setup_lookup_environment: dict
):
    """2. Test lookup by external reference (barcode / QR string)."""
    file_fin = setup_lookup_environment["file_fin"]
    headers = get_auth_headers(test_users["dept_user_fin"])

    res = client.get(f"/api/v1/physical-files/lookup?code={file_fin.external_reference}", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["id"] == str(file_fin.id)
    assert data["external_reference"] == file_fin.external_reference


def test_lookup_from_qr_url_payload(
    client: TestClient, test_users: dict[str, User], setup_lookup_environment: dict
):
    """3. Test lookup when QR scan payload contains full application URL or deep-link query."""
    file_fin = setup_lookup_environment["file_fin"]
    headers = get_auth_headers(test_users["dept_user_fin"])

    # Scan returning query parameter format
    url_payload = f"https://edrms.example.gov/physical-files?ref={file_fin.file_reference}"
    res = client.get(f"/api/v1/physical-files/lookup?code={url_payload}", headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["id"] == str(file_fin.id)

    # Scan returning path format
    path_payload = f"https://edrms.example.gov/physical-files/{file_fin.file_reference}"
    res2 = client.get(f"/api/v1/physical-files/lookup?code={path_payload}", headers=headers)
    assert res2.status_code == 200, res2.text
    assert res2.json()["id"] == str(file_fin.id)


def test_lookup_by_uuid(
    client: TestClient, test_users: dict[str, User], setup_lookup_environment: dict
):
    """4. Test lookup by direct UUID string."""
    file_fin = setup_lookup_environment["file_fin"]
    headers = get_auth_headers(test_users["dept_user_fin"])

    res = client.get(f"/api/v1/physical-files/lookup?code={file_fin.id}", headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["file_reference"] == file_fin.file_reference


def test_lookup_department_isolation_and_non_disclosing_404(
    client: TestClient, test_users: dict[str, User], setup_lookup_environment: dict, db_session: Session
):
    """5. Test that department user looking up file in another department receives non-disclosing 404."""
    file_hr = setup_lookup_environment["file_hr"]
    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    res = client.get(f"/api/v1/physical-files/lookup?code={file_hr.file_reference}", headers=fin_headers)
    assert res.status_code == 404
    assert res.json()["detail"] == "Physical file not found."

    # Verify audit log captures denied lookup
    audit_entry = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == "physical_file.lookup",
            AuditLog.resource_id == file_hr.id,
            AuditLog.actor_id == test_users["dept_user_fin"].id,
        )
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.outcome.value == "denied"


def test_lookup_nonexistent_and_malformed_code(
    client: TestClient, test_users: dict[str, User]
):
    """6. Test lookup returns 404 for unknown or malformed code."""
    admin_headers = get_auth_headers(test_users["admin"])

    res = client.get("/api/v1/physical-files/lookup?code=DOES-NOT-EXIST-9999", headers=admin_headers)
    assert res.status_code == 404
    assert res.json()["detail"] == "Physical file not found."

    # Blank/empty code fails validation
    res_empty = client.get("/api/v1/physical-files/lookup?code=", headers=admin_headers)
    assert res_empty.status_code == 422


def test_search_filters_and_custody_state(
    client: TestClient, db_session: Session, test_users: dict[str, User], setup_lookup_environment: dict
):
    """7. Test extended registry search: classification and custody state filtering."""
    file_fin = setup_lookup_environment["file_fin"]
    admin_headers = get_auth_headers(test_users["admin"])

    # Set file_fin as checked out and overdue
    file_fin.is_checked_out = True
    custody_rec = FileCustodyRecord(
        physical_file_id=file_fin.id,
        custodian_name="External Investigator",
        custodian_department="Finance",
        status=CustodyStatus.ACTIVE,
        checked_out_at=datetime.now(timezone.utc) - timedelta(days=5),
        expected_return_at=datetime.now(timezone.utc) - timedelta(days=1),
        purpose="Investigation",
        issued_by_id=test_users["admin"].id,
    )
    db_session.add(custody_rec)
    db_session.commit()

    # Search filter by classification
    res_cls = client.get("/api/v1/physical-files?classification=Confidential", headers=admin_headers)
    assert res_cls.status_code == 200
    items = res_cls.json()["items"]
    assert any(i["id"] == str(file_fin.id) for i in items)

    # Search filter by custody_state=checked_out
    res_co = client.get("/api/v1/physical-files?custody_state=checked_out", headers=admin_headers)
    assert res_co.status_code == 200
    assert any(i["id"] == str(file_fin.id) for i in res_co.json()["items"])

    # Search filter by custody_state=overdue
    res_od = client.get("/api/v1/physical-files?custody_state=overdue", headers=admin_headers)
    assert res_od.status_code == 200
    assert any(i["id"] == str(file_fin.id) for i in res_od.json()["items"])

    # Search filter by custody_state=stored (file_fin should not appear)
    res_st = client.get("/api/v1/physical-files?custody_state=stored", headers=admin_headers)
    assert res_st.status_code == 200
    assert all(i["id"] != str(file_fin.id) for i in res_st.json()["items"])


def test_label_print_audit_endpoint(
    client: TestClient, db_session: Session, test_users: dict[str, User], setup_lookup_environment: dict
):
    """8. Test audit logging for label printing."""
    file_fin = setup_lookup_environment["file_fin"]
    headers = get_auth_headers(test_users["dept_user_fin"])

    payload = {
        "file_ids": [str(file_fin.id)],
        "label_format": "standard_qr_barcode_3x2",
    }

    res = client.post("/api/v1/physical-files/print-label", json=payload, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert res.json()["printed_count"] == 1

    # Verify audit log was recorded
    audit_entry = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == "physical_file.print_label",
            AuditLog.resource_id == file_fin.id,
        )
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.details.get("label_format") == "standard_qr_barcode_3x2"
