import uuid
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.document import DigitalDocument, DocumentStatus
from app.models.physical_file import (
    PhysicalFile,
    PhysicalRecordType,
    PhysicalFileStatus,
)
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


def test_physical_file_registration_and_validation(client: TestClient, test_users: dict[str, User]):
    """1. Registration and field-level validation."""
    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    # Successful registration by department user in own department
    payload = {
        "title": "2026 Fiscal Audit Binder",
        "description": "Physical binder containing paper audit reports.",
        "record_type": PhysicalRecordType.FINANCIAL_RECORD.value,
        "department": "Finance",
        "classification": "Confidential",
        "external_reference": "EXT-FIN-9901",
    }
    res = client.post("/api/v1/physical-files", headers=fin_headers, json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == payload["title"]
    assert data["record_type"] == PhysicalRecordType.FINANCIAL_RECORD.value
    assert data["department"] == "Finance"
    assert data["status"] == PhysicalFileStatus.ACTIVE.value
    assert data["file_reference"].startswith("PHY-")
    assert data["external_reference"] == "EXT-FIN-9901"
    assert data["created_by"]["id"] == str(test_users["dept_user_fin"].id)

    # Missing title validation
    invalid_payload = {**payload, "title": ""}
    res_err = client.post("/api/v1/physical-files", headers=fin_headers, json=invalid_payload)
    assert res_err.status_code == 422


def test_unique_reference_generation(client: TestClient, test_users: dict[str, User]):
    """2. Verify generated PHY references are unique and well-formatted."""
    ro_headers = get_auth_headers(test_users["records_officer"])
    refs = set()
    for i in range(5):
        payload = {
            "title": f"Unique File {i} {uuid.uuid4().hex[:4]}",
            "record_type": PhysicalRecordType.CONTRACT.value,
            "department": "Legal",
        }
        res = client.post("/api/v1/physical-files", headers=ro_headers, json=payload)
        assert res.status_code == 201
        ref = res.json()["file_reference"]
        assert ref.startswith("PHY-")
        assert ref not in refs
        refs.add(ref)


def test_listing_searching_filtering_pagination(client: TestClient, test_users: dict[str, User]):
    """3. List, search, department filter, and pagination."""
    admin_headers = get_auth_headers(test_users["admin"])

    # Create distinct records
    client.post(
        "/api/v1/physical-files",
        headers=admin_headers,
        json={
            "title": "Alpha Physical Agreement",
            "record_type": PhysicalRecordType.CONTRACT.value,
            "department": "Operations",
            "external_reference": "EXT-ALPHA",
        },
    )
    client.post(
        "/api/v1/physical-files",
        headers=admin_headers,
        json={
            "title": "Beta Employment Folder",
            "record_type": PhysicalRecordType.PERSONNEL_FILE.value,
            "department": "Human Resources",
            "external_reference": "EXT-BETA",
        },
    )

    # Search by keyword
    res = client.get("/api/v1/physical-files?search=Alpha", headers=admin_headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert any("Alpha" in item["title"] for item in items)
    assert not any("Beta" in item["title"] for item in items)

    # Filter by record_type
    res_type = client.get(
        f"/api/v1/physical-files?record_type={PhysicalRecordType.PERSONNEL_FILE.value}",
        headers=admin_headers,
    )
    assert res_type.status_code == 200
    for item in res_type.json()["items"]:
        assert item["record_type"] == PhysicalRecordType.PERSONNEL_FILE.value

    # Pagination
    res_page = client.get("/api/v1/physical-files?page=1&page_size=1", headers=admin_headers)
    assert res_page.status_code == 200
    assert len(res_page.json()["items"]) == 1
    assert res_page.json()["page"] == 1
    assert res_page.json()["total"] >= 2


def test_department_level_isolation_and_scoping(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """4. Department-level access control: Finance cannot see or access HR physical files."""
    # HR file
    hr_file = PhysicalFile(
        file_reference=f"PHY-HR-{uuid.uuid4().hex[:6].upper()}",
        title="Confidential HR Grievance Dossier",
        record_type=PhysicalRecordType.CASE_FILE,
        department="Human Resources",
        status=PhysicalFileStatus.ACTIVE,
        created_by_id=test_users["dept_user_hr"].id,
    )
    db_session.add(hr_file)
    db_session.commit()
    db_session.refresh(hr_file)

    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    # 1. Direct GET HR file by Finance user -> non-disclosing 404
    res_get = client.get(f"/api/v1/physical-files/{hr_file.id}", headers=fin_headers)
    assert res_get.status_code == 404

    # 2. List physical files by Finance user -> does not include HR file
    res_list = client.get("/api/v1/physical-files", headers=fin_headers)
    assert res_list.status_code == 200
    file_ids = [item["id"] for item in res_list.json()["items"]]
    assert str(hr_file.id) not in file_ids

    # 3. Department user attempting to register file in different department -> 403 Forbidden
    cross_reg = {
        "title": "Illicit Cross-Dept Registration",
        "record_type": PhysicalRecordType.CONTRACT.value,
        "department": "Human Resources",
    }
    res_cross = client.post("/api/v1/physical-files", headers=fin_headers, json=cross_reg)
    assert res_cross.status_code == 403
    assert "Department users may only register physical files in their own department" in res_cross.json()["detail"]


def test_unauthorized_department_reassignment(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """5. Prevent department users from reassigning department ownership; allow admin."""
    fin_file = PhysicalFile(
        file_reference=f"PHY-FIN-{uuid.uuid4().hex[:6].upper()}",
        title="Finance Ledger 2026",
        record_type=PhysicalRecordType.FINANCIAL_RECORD,
        department="Finance",
        status=PhysicalFileStatus.ACTIVE,
        created_by_id=test_users["dept_user_fin"].id,
    )
    db_session.add(fin_file)
    db_session.commit()
    db_session.refresh(fin_file)

    fin_headers = get_auth_headers(test_users["dept_user_fin"])
    admin_headers = get_auth_headers(test_users["admin"])

    # Dept User attempts to change department -> 403 Forbidden
    res_denied = client.patch(
        f"/api/v1/physical-files/{fin_file.id}",
        headers=fin_headers,
        json={"department": "Operations"},
    )
    assert res_denied.status_code == 403
    assert "reassign department ownership" in res_denied.json()["detail"]

    # Admin successfully reassigns department -> 200 OK
    res_ok = client.patch(
        f"/api/v1/physical-files/{fin_file.id}",
        headers=admin_headers,
        json={"department": "Operations"},
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["department"] == "Operations"


def test_digital_document_relationship_validation_and_access(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """6. Optional digital document link validation and non-leaking behavior."""
    # HR digital document
    hr_doc = DigitalDocument(
        title="HR Confidential Payroll 2026",
        document_reference=f"DOC-HR-{uuid.uuid4().hex[:6]}",
        department="Human Resources",
        classification="Confidential",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=test_users["dept_user_hr"].id,
    )
    db_session.add(hr_doc)
    db_session.commit()
    db_session.refresh(hr_doc)

    fin_headers = get_auth_headers(test_users["dept_user_fin"])
    hr_headers = get_auth_headers(test_users["dept_user_hr"])

    # 1. Finance user attempts to register physical file linking to HR digital document -> 403 Forbidden
    res_bad_link = client.post(
        "/api/v1/physical-files",
        headers=fin_headers,
        json={
            "title": "Finance Physical Summary",
            "record_type": PhysicalRecordType.FINANCIAL_RECORD.value,
            "department": "Finance",
            "digital_document_id": str(hr_doc.id),
        },
    )
    assert res_bad_link.status_code == 403
    assert "permission to link to this digital document" in res_bad_link.json()["detail"]

    # 2. HR user successfully links to HR digital document
    res_good_link = client.post(
        "/api/v1/physical-files",
        headers=hr_headers,
        json={
            "title": "HR Physical Payroll Backup",
            "record_type": PhysicalRecordType.PERSONNEL_FILE.value,
            "department": "Human Resources",
            "digital_document_id": str(hr_doc.id),
        },
    )
    assert res_good_link.status_code == 201
    file_data = res_good_link.json()
    assert file_data["digital_document_id"] == str(hr_doc.id)
    assert file_data["digital_document"]["title"] == hr_doc.title


def test_status_transitions_and_validation(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """7. Validated lifecycle transitions: ACTIVE -> ARCHIVED -> INACTIVE -> ACTIVE."""
    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    # Create active file
    file_record = PhysicalFile(
        file_reference=f"PHY-STATUS-{uuid.uuid4().hex[:6].upper()}",
        title="Status Transition Test File",
        record_type=PhysicalRecordType.CONTRACT,
        department="Finance",
        status=PhysicalFileStatus.ACTIVE,
        created_by_id=test_users["dept_user_fin"].id,
    )
    db_session.add(file_record)
    db_session.commit()
    db_session.refresh(file_record)

    # 1. ACTIVE -> ARCHIVED: Valid
    res_arch = client.patch(
        f"/api/v1/physical-files/{file_record.id}/status",
        headers=fin_headers,
        json={"status": PhysicalFileStatus.ARCHIVED.value, "reason": "Moved to archive room"},
    )
    assert res_arch.status_code == 200
    assert res_arch.json()["status"] == PhysicalFileStatus.ARCHIVED.value

    # 2. ARCHIVED -> INACTIVE: Valid
    res_inact = client.patch(
        f"/api/v1/physical-files/{file_record.id}/status",
        headers=fin_headers,
        json={"status": PhysicalFileStatus.INACTIVE.value, "reason": "Decommissioned"},
    )
    assert res_inact.status_code == 200
    assert res_inact.json()["status"] == PhysicalFileStatus.INACTIVE.value

    # 3. INACTIVE -> ARCHIVED: Invalid (only INACTIVE -> ACTIVE allowed)
    res_invalid = client.patch(
        f"/api/v1/physical-files/{file_record.id}/status",
        headers=fin_headers,
        json={"status": PhysicalFileStatus.ARCHIVED.value},
    )
    assert res_invalid.status_code == 400
    assert "Invalid status transition" in res_invalid.json()["detail"]


def test_mandatory_audit_logging_for_physical_registry(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """8. Audit logging for physical file operations."""
    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    # Register file
    reg_res = client.post(
        "/api/v1/physical-files",
        headers=fin_headers,
        json={
            "title": "Audited Physical Record",
            "record_type": PhysicalRecordType.CASE_FILE.value,
            "department": "Finance",
        },
    )
    assert reg_res.status_code == 201
    file_id = reg_res.json()["id"]

    # Verify audit log was recorded
    audit_entry = db_session.query(AuditLog).filter(
        AuditLog.action == "physical_file.register",
        AuditLog.resource_id == uuid.UUID(file_id),
    ).first()
    assert audit_entry is not None
    assert audit_entry.actor_id == test_users["dept_user_fin"].id


def test_inactive_user_and_read_only_role_restrictions(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """9. Inactive user token rejection & read_only/approver mutations denied."""
    inactive_headers = get_auth_headers(test_users["inactive_user"])
    ro_headers = get_auth_headers(test_users["read_only_fin"])
    approver_headers = get_auth_headers(test_users["approver_fin"])

    # Inactive user rejected with 401
    res_inact = client.get("/api/v1/physical-files", headers=inactive_headers)
    assert res_inact.status_code == 401

    # Read-only user cannot register -> 403 Forbidden
    res_ro_reg = client.post(
        "/api/v1/physical-files",
        headers=ro_headers,
        json={
            "title": "Forbidden File",
            "record_type": PhysicalRecordType.CONTRACT.value,
            "department": "Finance",
        },
    )
    assert res_ro_reg.status_code == 403

    # Approver cannot register physical files -> 403 Forbidden
    res_app_reg = client.post(
        "/api/v1/physical-files",
        headers=approver_headers,
        json={
            "title": "Forbidden Approver File",
            "record_type": PhysicalRecordType.CONTRACT.value,
            "department": "Finance",
        },
    )
    assert res_app_reg.status_code == 403
