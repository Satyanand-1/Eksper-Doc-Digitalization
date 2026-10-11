import uuid
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.physical_file import PhysicalFile, PhysicalRecordType, PhysicalFileStatus
from app.models.storage_location import StorageLocation, LocationType
from app.models.custody import FileCustodyRecord, FileMovementHistory, CustodyStatus, PhysicalMovementType
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
def setup_locations_and_file(db_session: Session, test_users: dict[str, User]):
    """Helper fixture to create storage locations and an active physical file."""
    # Finance Cabinet (Max capacity: 2)
    fin_loc = StorageLocation(
        location_code=f"FIN-CAB-{uuid.uuid4().hex[:6].upper()}",
        name="Finance Archive Cabinet A",
        location_type=LocationType.CABINET,
        department="Finance",
        max_capacity=2,
        is_active=True,
        created_by_id=test_users["admin"].id,
    )
    # HR Cabinet
    hr_loc = StorageLocation(
        location_code=f"HR-CAB-{uuid.uuid4().hex[:6].upper()}",
        name="HR Records Cabinet B",
        location_type=LocationType.CABINET,
        department="Human Resources",
        max_capacity=5,
        is_active=True,
        created_by_id=test_users["admin"].id,
    )
    # Inactive Cabinet
    inactive_loc = StorageLocation(
        location_code=f"DIS-CAB-{uuid.uuid4().hex[:6].upper()}",
        name="Decommissioned Cabinet",
        location_type=LocationType.CABINET,
        department="Finance",
        max_capacity=10,
        is_active=False,
        created_by_id=test_users["admin"].id,
    )
    db_session.add_all([fin_loc, hr_loc, inactive_loc])
    db_session.commit()
    db_session.refresh(fin_loc)
    db_session.refresh(hr_loc)
    db_session.refresh(inactive_loc)

    # Physical File stored in fin_loc
    file_record = PhysicalFile(
        file_reference=f"PHY-2026-{uuid.uuid4().hex[:8].upper()}",
        title="2026 Fiscal Vendor Agreement",
        record_type=PhysicalRecordType.CONTRACT,
        department="Finance",
        status=PhysicalFileStatus.ACTIVE,
        storage_location_id=fin_loc.id,
        is_checked_out=False,
        created_by_id=test_users["dept_user_fin"].id,
    )
    db_session.add(file_record)
    db_session.commit()
    db_session.refresh(file_record)

    return {
        "fin_loc": fin_loc,
        "hr_loc": hr_loc,
        "inactive_loc": inactive_loc,
        "file": file_record,
    }


def test_successful_checkout_and_custody_creation(
    client: TestClient, db_session: Session, test_users: dict[str, User], setup_locations_and_file: dict
):
    """1. Test successful checkout creates custody record and movement event."""
    file_record = setup_locations_and_file["file"]
    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    payload = {
        "custodian_user_id": str(test_users["dept_user_fin"].id),
        "custodian_name": "Alice Auditor",
        "custodian_department": "Finance",
        "custodian_contact": "alice@edrms.test",
        "purpose": "Annual tax preparation audit",
        "expected_return_at": future_date,
    }

    res = client.post(f"/api/v1/physical-files/{file_record.id}/checkout", json=payload, headers=fin_headers)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["physical_file_id"] == str(file_record.id)
    assert data["custodian_name"] == "Alice Auditor"
    assert data["status"] == "active"
    assert data["purpose"] == "Annual tax preparation audit"
    assert data["is_overdue"] is False

    # Verify physical file state updated
    db_session.refresh(file_record)
    assert file_record.is_checked_out is True

    # Verify movement history event created
    movement = db_session.query(FileMovementHistory).filter(
        FileMovementHistory.physical_file_id == file_record.id
    ).first()
    assert movement is not None
    assert movement.movement_type == PhysicalMovementType.CHECKOUT
    assert "Checked out to Alice Auditor" in movement.to_custody_state

    # Verify audit log event
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "physical_file.checkout",
        AuditLog.resource_id == file_record.id,
    ).first()
    assert audit is not None
    assert audit.outcome.value == "success"


def test_duplicate_checkout_rejection(
    client: TestClient, db_session: Session, test_users: dict[str, User], setup_locations_and_file: dict
):
    """2. Prevent duplicate checkout when file is already checked out."""
    file_record = setup_locations_and_file["file"]
    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    payload = {
        "custodian_name": "Alice Auditor",
        "purpose": "Initial review",
    }
    res1 = client.post(f"/api/v1/physical-files/{file_record.id}/checkout", json=payload, headers=fin_headers)
    assert res1.status_code == 201

    # Second checkout attempt must fail with 409 Conflict
    res2 = client.post(f"/api/v1/physical-files/{file_record.id}/checkout", json=payload, headers=fin_headers)
    assert res2.status_code == 409
    assert "already checked out" in res2.json()["detail"].lower()


def test_successful_checkin_and_custody_closure(
    client: TestClient, db_session: Session, test_users: dict[str, User], setup_locations_and_file: dict
):
    """3. Test successful check-in closes custody record and returns file to storage."""
    file_record = setup_locations_and_file["file"]
    fin_loc = setup_locations_and_file["fin_loc"]
    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    # 1. Checkout first
    client.post(
        f"/api/v1/physical-files/{file_record.id}/checkout",
        json={"custodian_name": "Bob Records", "purpose": "Legal inspection"},
        headers=fin_headers,
    )

    # 2. Check-in
    checkin_payload = {
        "destination_location_id": str(fin_loc.id),
        "checkin_notes": "Returned in perfect condition, all signatures intact.",
    }
    res = client.post(f"/api/v1/physical-files/{file_record.id}/checkin", json=checkin_payload, headers=fin_headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "returned"
    assert data["checked_in_at"] is not None
    assert data["checkin_notes"] == "Returned in perfect condition, all signatures intact."

    # Verify physical file state
    db_session.refresh(file_record)
    assert file_record.is_checked_out is False

    # Verify movement history has both checkout and checkin events
    movements = db_session.query(FileMovementHistory).filter(
        FileMovementHistory.physical_file_id == file_record.id
    ).order_by(FileMovementHistory.event_at.asc()).all()
    assert len(movements) == 2
    assert movements[0].movement_type == PhysicalMovementType.CHECKOUT
    assert movements[1].movement_type == PhysicalMovementType.CHECKIN
    assert "Stored in" in movements[1].to_custody_state


def test_checkin_rejection_when_not_checked_out(
    client: TestClient, test_users: dict[str, User], setup_locations_and_file: dict
):
    """4. Reject check-in attempts when file is not currently checked out."""
    file_record = setup_locations_and_file["file"]
    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    res = client.post(
        f"/api/v1/physical-files/{file_record.id}/checkin",
        json={"checkin_notes": "Early return"},
        headers=fin_headers,
    )
    assert res.status_code == 400
    assert "not currently checked out" in res.json()["detail"].lower()


def test_transfer_between_storage_locations(
    client: TestClient, db_session: Session, test_users: dict[str, User], setup_locations_and_file: dict
):
    """5. Successful physical transfer updates location and creates movement event."""
    file_record = setup_locations_and_file["file"]
    admin_headers = get_auth_headers(test_users["admin"])
    hr_loc = setup_locations_and_file["hr_loc"]

    transfer_payload = {
        "destination_location_id": str(hr_loc.id),
        "reason": "Relocated to HR central filing for cross-department audit.",
    }
    res = client.post(f"/api/v1/physical-files/{file_record.id}/transfer", json=transfer_payload, headers=admin_headers)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["movement_type"] == "transfer"
    assert data["destination_location_id"] == str(hr_loc.id)

    db_session.refresh(file_record)
    assert file_record.storage_location_id == hr_loc.id

    # Verify movement history
    movement = db_session.query(FileMovementHistory).filter(
        FileMovementHistory.physical_file_id == file_record.id,
        FileMovementHistory.movement_type == PhysicalMovementType.TRANSFER,
    ).first()
    assert movement is not None
    assert movement.destination_location_id == hr_loc.id


def test_transfer_rejection_for_checked_out_file(
    client: TestClient, test_users: dict[str, User], setup_locations_and_file: dict
):
    """6. Prevent transferring a file that is currently checked out."""
    file_record = setup_locations_and_file["file"]
    fin_headers = get_auth_headers(test_users["dept_user_fin"])
    hr_loc = setup_locations_and_file["hr_loc"]

    # Check out file first
    client.post(
        f"/api/v1/physical-files/{file_record.id}/checkout",
        json={"custodian_name": "Charlie Clerk", "purpose": "Trial review"},
        headers=fin_headers,
    )

    # Attempt transfer while checked out
    admin_headers = get_auth_headers(test_users["admin"])
    res = client.post(
        f"/api/v1/physical-files/{file_record.id}/transfer",
        json={"destination_location_id": str(hr_loc.id), "reason": "Moving cabinet"},
        headers=admin_headers,
    )
    assert res.status_code == 400
    assert "currently checked out" in res.json()["detail"].lower()


def test_transfer_capacity_and_inactive_location_enforcement(
    client: TestClient, test_users: dict[str, User], setup_locations_and_file: dict
):
    """7. Enforce destination location capacity and active status during transfer."""
    file_record = setup_locations_and_file["file"]
    inactive_loc = setup_locations_and_file["inactive_loc"]
    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    # Attempt transfer to inactive location
    res = client.post(
        f"/api/v1/physical-files/{file_record.id}/transfer",
        json={"destination_location_id": str(inactive_loc.id), "reason": "Retiring"},
        headers=fin_headers,
    )
    assert res.status_code == 400
    assert "inactive" in res.json()["detail"].lower()


def test_department_isolation_on_checkout_and_transfer(
    client: TestClient, test_users: dict[str, User], setup_locations_and_file: dict
):
    """8. Department user cannot check out or transfer another department's file."""
    file_record = setup_locations_and_file["file"]
    hr_headers = get_auth_headers(test_users["dept_user_hr"])
    hr_loc = setup_locations_and_file["hr_loc"]

    # HR user attempts to check out Finance file
    res = client.post(
        f"/api/v1/physical-files/{file_record.id}/checkout",
        json={"custodian_name": "Eve HR", "purpose": "Unauthorized checkout"},
        headers=hr_headers,
    )
    assert res.status_code == 403
    assert "own department" in res.json()["detail"].lower()

    # HR user attempts to transfer Finance file
    res_transfer = client.post(
        f"/api/v1/physical-files/{file_record.id}/transfer",
        json={"destination_location_id": str(hr_loc.id), "reason": "Stealing file"},
        headers=hr_headers,
    )
    assert res_transfer.status_code == 403


def test_overdue_file_detection_and_reporting(
    client: TestClient, db_session: Session, test_users: dict[str, User], setup_locations_and_file: dict
):
    """9. Test overdue physical file query and reporting endpoint."""
    file_record = setup_locations_and_file["file"]
    fin_headers = get_auth_headers(test_users["dept_user_fin"])
    admin_headers = get_auth_headers(test_users["admin"])

    # Check out with expected return date in the past
    past_date = datetime.now(timezone.utc) - timedelta(days=3)
    custody_record = FileCustodyRecord(
        physical_file_id=file_record.id,
        custodian_name="Late Custodian",
        custodian_department="Finance",
        status=CustodyStatus.ACTIVE,
        checked_out_at=datetime.now(timezone.utc) - timedelta(days=10),
        expected_return_at=past_date,
        purpose="Past due project",
        issued_by_id=test_users["dept_user_fin"].id,
    )
    file_record.is_checked_out = True
    db_session.add(custody_record)
    db_session.commit()

    # Query overdue report as admin
    res = client.get("/api/v1/physical-files/overdue", headers=admin_headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total"] >= 1
    found = [item for item in data["items"] if item["physical_file_id"] == str(file_record.id)]
    assert len(found) == 1
    assert found[0]["custodian_name"] == "Late Custodian"
    assert found[0]["days_overdue"] >= 2

    # Query current custody endpoint to verify is_overdue flag
    res_custody = client.get(f"/api/v1/physical-files/{file_record.id}/custody", headers=fin_headers)
    assert res_custody.status_code == 200
    assert res_custody.json()["is_overdue"] is True


def test_custody_and_movement_history_endpoints(
    client: TestClient, test_users: dict[str, User], setup_locations_and_file: dict
):
    """10. Verify history endpoints return chronological records."""
    file_record = setup_locations_and_file["file"]
    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    # Perform checkout then checkin
    client.post(
        f"/api/v1/physical-files/{file_record.id}/checkout",
        json={"custodian_name": "Dan Reviewer", "purpose": "Quick check"},
        headers=fin_headers,
    )
    client.post(
        f"/api/v1/physical-files/{file_record.id}/checkin",
        json={"checkin_notes": "Returned"},
        headers=fin_headers,
    )

    # 1. Custody History
    res_ch = client.get(f"/api/v1/physical-files/{file_record.id}/custody-history", headers=fin_headers)
    assert res_ch.status_code == 200
    assert res_ch.json()["total"] == 1
    assert res_ch.json()["items"][0]["custodian_name"] == "Dan Reviewer"

    # 2. Movement History
    res_mh = client.get(f"/api/v1/physical-files/{file_record.id}/movement-history", headers=fin_headers)
    assert res_mh.status_code == 200
    assert res_mh.json()["total"] == 2
    types = [item["movement_type"] for item in res_mh.json()["items"]]
    assert "checkin" in types and "checkout" in types
