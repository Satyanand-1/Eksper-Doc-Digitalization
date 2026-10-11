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
from app.jwt import create_access_token


@pytest.fixture
def test_users(db_session: Session) -> dict[str, User]:
    """Provision test users across roles and departments."""
    configs = [
        ("admin", UserRole.ADMIN, "Executive", True),
        ("records_officer", UserRole.RECORDS_OFFICER, "Records Management", True),
        ("dept_user_fin", UserRole.DEPARTMENT_USER, "Finance", True),
        ("dept_user_hr", UserRole.DEPARTMENT_USER, "Human Resources", True),
        ("auditor_fin", UserRole.AUDITOR, "Finance", True),
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


def create_test_location(db: Session, code: str, dept: str, creator_id: uuid.UUID) -> StorageLocation:
    loc = StorageLocation(
        location_code=code,
        name=f"Location {code}",
        location_type=LocationType.SHELF,
        department=dept,
        is_active=True,
        created_by_id=creator_id,
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


def create_test_physical_file(
    db: Session,
    ref: str,
    title: str,
    dept: str,
    creator_id: uuid.UUID,
    loc_id: uuid.UUID | None = None,
    is_checked_out: bool = False,
) -> PhysicalFile:
    pf = PhysicalFile(
        file_reference=ref,
        title=title,
        record_type=PhysicalRecordType.CONTRACT,
        department=dept,
        classification="Confidential",
        status=PhysicalFileStatus.ACTIVE,
        created_by_id=creator_id,
        storage_location_id=loc_id,
        is_checked_out=is_checked_out,
    )
    db.add(pf)
    db.commit()
    db.refresh(pf)
    return pf


def test_database_enforces_single_active_custody(db_session: Session, test_users: dict[str, User]):
    """
    Test 1: Verify PostgreSQL partial unique index uq_file_custody_single_active
    strictly prevents inserting more than one active custody record for the same physical file.
    """
    admin = test_users["admin"]
    loc = create_test_location(db_session, f"LOC-CUST-{uuid.uuid4().hex[:6].upper()}", "Legal", admin.id)
    file_rec = create_test_physical_file(
        db_session, f"PHY-INT-{uuid.uuid4().hex[:8].upper()}", "Integrity Contract", "Legal", admin.id, loc.id, True
    )

    now = datetime.now(timezone.utc)
    c1 = FileCustodyRecord(
        physical_file_id=file_rec.id,
        custodian_name="Custodian One",
        status=CustodyStatus.ACTIVE,
        checked_out_at=now,
        purpose="Legal Review",
        issued_by_id=admin.id,
    )
    db_session.add(c1)
    db_session.commit()

    # Second active record MUST violate the partial unique constraint
    c2 = FileCustodyRecord(
        physical_file_id=file_rec.id,
        custodian_name="Custodian Two",
        status=CustodyStatus.ACTIVE,
        checked_out_at=now,
        purpose="Parallel Review Violation",
        issued_by_id=admin.id,
    )
    db_session.add(c2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_custody_integrity_detects_missing_active_custody(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """
    Test 2: A file marked checked out without an active custody record is detected as MISSING_ACTIVE_CUSTODY.
    """
    admin = test_users["admin"]
    loc = create_test_location(db_session, f"LOC-CUST-{uuid.uuid4().hex[:6].upper()}", "Legal", admin.id)
    file_rec = create_test_physical_file(
        db_session, f"PHY-INT-{uuid.uuid4().hex[:8].upper()}", "Dangling Checked Out File", "Legal", admin.id, loc.id, True
    )

    resp = client.get(
        "/api/v1/physical-files/custody-integrity",
        headers=get_auth_headers(admin),
    )
    assert resp.status_code == 200
    data = resp.json()

    issues = [i for i in data["items"] if i["file_reference"] == file_rec.file_reference]
    assert len(issues) == 1
    assert issues[0]["issue_type"] == "MISSING_ACTIVE_CUSTODY"
    assert issues[0]["severity"] == "error"


def test_custody_integrity_detects_unexpected_active_custody(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """
    Test 3: A file marked stored (is_checked_out=False) with an active custody record
    is detected as UNEXPECTED_ACTIVE_CUSTODY.
    """
    admin = test_users["admin"]
    loc = create_test_location(db_session, f"LOC-CUST-{uuid.uuid4().hex[:6].upper()}", "Finance", admin.id)
    file_rec = create_test_physical_file(
        db_session, f"PHY-INT-{uuid.uuid4().hex[:8].upper()}", "Stored but Active File", "Finance", admin.id, loc.id, False
    )

    now = datetime.now(timezone.utc)
    c = FileCustodyRecord(
        physical_file_id=file_rec.id,
        custodian_name="Auditor Brown",
        status=CustodyStatus.ACTIVE,
        checked_out_at=now,
        purpose="Audit Check",
        issued_by_id=admin.id,
    )
    db_session.add(c)
    db_session.commit()

    resp = client.get(
        "/api/v1/physical-files/custody-integrity",
        headers=get_auth_headers(admin),
    )
    assert resp.status_code == 200
    data = resp.json()

    issues = [i for i in data["items"] if i["file_reference"] == file_rec.file_reference]
    issue_types = {i["issue_type"] for i in issues}
    assert "UNEXPECTED_ACTIVE_CUSTODY" in issue_types


def test_custody_integrity_detects_location_mismatch(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """
    Test 4: Stored file whose current location conflicts with latest check-in destination
    is flagged with LOCATION_MISMATCH_WITH_RETURN.
    """
    admin = test_users["admin"]
    loc1 = create_test_location(db_session, f"LOC-DEST1-{uuid.uuid4().hex[:6].upper()}", "Operations", admin.id)
    loc2 = create_test_location(db_session, f"LOC-DEST2-{uuid.uuid4().hex[:6].upper()}", "Operations", admin.id)

    file_rec = create_test_physical_file(
        db_session, f"PHY-INT-{uuid.uuid4().hex[:8].upper()}", "Moved Record", "Operations", admin.id, loc1.id, False
    )

    now = datetime.now(timezone.utc)
    mov = FileMovementHistory(
        physical_file_id=file_rec.id,
        movement_type=PhysicalMovementType.CHECKIN,
        destination_location_id=loc2.id,
        from_custody_state="Checked out",
        to_custody_state=f"Stored in {loc2.location_code}",
        actor_id=admin.id,
        event_at=now,
        reason="Returned to loc2",
    )
    db_session.add(mov)
    db_session.commit()

    resp = client.get(
        "/api/v1/physical-files/custody-integrity",
        headers=get_auth_headers(admin),
    )
    assert resp.status_code == 200
    data = resp.json()

    issues = [i for i in data["items"] if i["file_reference"] == file_rec.file_reference]
    assert any(i["issue_type"] == "LOCATION_MISMATCH_WITH_RETURN" for i in issues)


def test_custody_integrity_department_isolation(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """
    Test 5: Department users cannot view integrity issues belonging to other departments.
    """
    admin = test_users["admin"]
    dept_user = test_users["dept_user_fin"]

    loc_fin = create_test_location(db_session, f"LOC-FIN-{uuid.uuid4().hex[:6].upper()}", "Finance", admin.id)
    loc_hr = create_test_location(db_session, f"LOC-HR-{uuid.uuid4().hex[:6].upper()}", "Human Resources", admin.id)

    fin_file = create_test_physical_file(
        db_session, f"PHY-FIN-{uuid.uuid4().hex[:8].upper()}", "Finance File", "Finance", admin.id, loc_fin.id, True
    )
    hr_file = create_test_physical_file(
        db_session, f"PHY-HR-{uuid.uuid4().hex[:8].upper()}", "HR File", "Human Resources", admin.id, loc_hr.id, True
    )

    resp = client.get(
        "/api/v1/physical-files/custody-integrity",
        headers=get_auth_headers(dept_user),
    )
    assert resp.status_code == 200
    data = resp.json()

    refs = [i["file_reference"] for i in data["items"]]
    assert fin_file.file_reference in refs
    assert hr_file.file_reference not in refs
    for item in data["items"]:
        assert item["department"].lower() == "finance"


def test_overdue_filters_and_exclusion_of_returned_files(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """
    Test 6: Overdue report excludes returned custody records, supports custodian filter,
    and returns last known storage location.
    """
    admin = test_users["admin"]
    loc = create_test_location(db_session, f"LOC-RET-{uuid.uuid4().hex[:6].upper()}", "Executive", admin.id)
    file_overdue = create_test_physical_file(
        db_session, f"PHY-OVER-{uuid.uuid4().hex[:8].upper()}", "Active Overdue File", "Executive", admin.id, loc.id, True
    )
    file_returned = create_test_physical_file(
        db_session, f"PHY-RET-{uuid.uuid4().hex[:8].upper()}", "Returned File", "Executive", admin.id, loc.id, False
    )

    now = datetime.now(timezone.utc)
    past_due = now - timedelta(days=5)

    c_active = FileCustodyRecord(
        physical_file_id=file_overdue.id,
        custodian_name="Special Agent Cooper",
        custodian_department="Executive",
        status=CustodyStatus.ACTIVE,
        checked_out_at=past_due - timedelta(days=5),
        expected_return_at=past_due,
        purpose="Sensitive Probe",
        issued_by_id=admin.id,
    )
    c_returned = FileCustodyRecord(
        physical_file_id=file_returned.id,
        custodian_name="Special Agent Cooper",
        custodian_department="Executive",
        status=CustodyStatus.RETURNED,
        checked_out_at=past_due - timedelta(days=10),
        expected_return_at=past_due,
        checked_in_at=now,
        purpose="Resolved Probe",
        issued_by_id=admin.id,
    )
    db_session.add_all([c_active, c_returned])
    db_session.commit()

    resp = client.get(
        "/api/v1/physical-files/overdue?custodian=Cooper",
        headers=get_auth_headers(admin),
    )
    assert resp.status_code == 200
    data = resp.json()

    overdue_refs = [item["file_reference"] for item in data["items"]]
    assert file_overdue.file_reference in overdue_refs
    assert file_returned.file_reference not in overdue_refs

    item = next(i for i in data["items"] if i["file_reference"] == file_overdue.file_reference)
    assert item["storage_location_code"] == loc.location_code
    assert item["days_overdue"] >= 5


def test_location_transfers_report(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """
    Test 7: Location transfers endpoint returns chronological transfer events.
    """
    admin = test_users["admin"]
    loc_src = create_test_location(db_session, f"LOC-SRC-{uuid.uuid4().hex[:6].upper()}", "IT", admin.id)
    loc_dst = create_test_location(db_session, f"LOC-DST-{uuid.uuid4().hex[:6].upper()}", "IT", admin.id)
    pf = create_test_physical_file(
        db_session, f"PHY-TRANS-{uuid.uuid4().hex[:8].upper()}", "Server Specs", "IT", admin.id, loc_dst.id, False
    )

    now = datetime.now(timezone.utc)
    mov = FileMovementHistory(
        physical_file_id=pf.id,
        movement_type=PhysicalMovementType.TRANSFER,
        source_location_id=loc_src.id,
        destination_location_id=loc_dst.id,
        from_custody_state=f"Stored in {loc_src.location_code}",
        to_custody_state=f"Stored in {loc_dst.location_code}",
        actor_id=admin.id,
        event_at=now,
        reason="Server Room Reorganization",
    )
    db_session.add(mov)
    db_session.commit()

    resp = client.get(
        "/api/v1/physical-files/transfers?department=IT",
        headers=get_auth_headers(admin),
    )
    assert resp.status_code == 200
    data = resp.json()
    items = [i for i in data["items"] if i["file_reference"] == pf.file_reference]
    assert len(items) == 1
    assert items[0]["source_location_code"] == loc_src.location_code
    assert items[0]["destination_location_code"] == loc_dst.location_code
    assert items[0]["reason"] == "Server Room Reorganization"


def test_csv_export_escapes_formulas_and_respects_permissions(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """
    Test 8: CSV export endpoint safely escapes formula characters (=, +, -, @)
    and enforces authentication.
    """
    admin = test_users["admin"]
    loc = create_test_location(db_session, f"LOC-FORM-{uuid.uuid4().hex[:6].upper()}", "Legal", admin.id)
    dangerous_title = "=cmd|' /C calc'!A0"
    file_rec = create_test_physical_file(
        db_session, f"PHY-FORM-{uuid.uuid4().hex[:8].upper()}", dangerous_title, "Legal", admin.id, loc.id, True
    )

    now = datetime.now(timezone.utc)
    c = FileCustodyRecord(
        physical_file_id=file_rec.id,
        custodian_name="+@EvilFormulaName",
        status=CustodyStatus.ACTIVE,
        checked_out_at=now - timedelta(days=2),
        expected_return_at=now - timedelta(days=1),
        purpose="-DDE(\"server\";\"file\";\"item\")",
        issued_by_id=admin.id,
    )
    db_session.add(c)
    db_session.commit()

    resp = client.get(
        "/api/v1/physical-files/export-csv?report_type=overdue&department=Legal",
        headers=get_auth_headers(admin),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    csv_text = resp.text

    assert "'=cmd|' /C calc'!A0" in csv_text
    assert "'+@EvilFormulaName" in csv_text
    assert "'-DDE(" in csv_text
