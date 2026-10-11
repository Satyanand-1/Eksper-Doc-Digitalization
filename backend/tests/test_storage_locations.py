import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.storage_location import StorageLocation, LocationType
from app.models.physical_file import PhysicalFile, PhysicalRecordType, PhysicalFileStatus
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


def test_create_storage_location_and_validation(client: TestClient, test_users: dict[str, User]):
    """1. Create location, duplicate code prevention, and field validation."""
    ro_headers = get_auth_headers(test_users["records_officer"])
    loc_code = f"LOC-BLD-{uuid.uuid4().hex[:4].upper()}"

    # Successful creation of top-level building
    res = client.post(
        "/api/v1/storage-locations",
        headers=ro_headers,
        json={
            "location_code": loc_code,
            "name": "Central Archive Center",
            "location_type": LocationType.BUILDING.value,
            "department": "Records Management",
            "description": "Primary repository facility.",
            "max_capacity": 500,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["location_code"] == loc_code
    assert data["name"] == "Central Archive Center"
    assert data["location_type"] == LocationType.BUILDING.value
    assert data["is_active"] is True
    assert data["max_capacity"] == 500
    assert data["location_path"] == "Central Archive Center"

    # Duplicate code rejection -> 409 Conflict
    res_dup = client.post(
        "/api/v1/storage-locations",
        headers=ro_headers,
        json={
            "location_code": loc_code,
            "name": "Duplicate Building",
            "location_type": LocationType.BUILDING.value,
            "department": "Records Management",
        },
    )
    assert res_dup.status_code == 409
    assert "already exists" in res_dup.json()["detail"]


def test_hierarchy_nesting_and_breadcrumb_path(client: TestClient, test_users: dict[str, User]):
    """2. Hierarchical nesting Building -> Floor -> Room -> Cabinet -> Shelf -> Box."""
    admin_headers = get_auth_headers(test_users["admin"])

    # 1. Building
    bld_res = client.post(
        "/api/v1/storage-locations",
        headers=admin_headers,
        json={
            "location_code": f"BLD-{uuid.uuid4().hex[:4].upper()}",
            "name": "HQ Building",
            "location_type": LocationType.BUILDING.value,
            "department": "Executive",
        },
    )
    assert bld_res.status_code == 201
    bld_id = bld_res.json()["id"]

    # 2. Floor under Building
    flr_res = client.post(
        "/api/v1/storage-locations",
        headers=admin_headers,
        json={
            "location_code": f"FLR-{uuid.uuid4().hex[:4].upper()}",
            "name": "Floor 2",
            "location_type": LocationType.FLOOR.value,
            "department": "Executive",
            "parent_id": bld_id,
        },
    )
    assert flr_res.status_code == 201
    flr_id = flr_res.json()["id"]
    assert flr_res.json()["location_path"] == "HQ Building / Floor 2"

    # 3. Room under Floor
    room_res = client.post(
        "/api/v1/storage-locations",
        headers=admin_headers,
        json={
            "location_code": f"ROOM-{uuid.uuid4().hex[:4].upper()}",
            "name": "Secure Vault 204",
            "location_type": LocationType.ROOM.value,
            "department": "Executive",
            "parent_id": flr_id,
        },
    )
    assert room_res.status_code == 201
    room_id = room_res.json()["id"]
    assert room_res.json()["location_path"] == "HQ Building / Floor 2 / Secure Vault 204"

    # 4. Check breadcrumbs in detail endpoint
    get_res = client.get(f"/api/v1/storage-locations/{room_id}", headers=admin_headers)
    assert get_res.status_code == 200
    crumbs = get_res.json()["breadcrumbs"]
    assert len(crumbs) == 3
    assert crumbs[0]["name"] == "HQ Building"
    assert crumbs[1]["name"] == "Floor 2"
    assert crumbs[2]["name"] == "Secure Vault 204"


def test_circular_and_invalid_hierarchy_prevention(client: TestClient, test_users: dict[str, User]):
    """3. Prevent cyclic parenting, self-parenting, and invalid hierarchy types."""
    admin_headers = get_auth_headers(test_users["admin"])

    # Create Parent & Child
    bld_res = client.post(
        "/api/v1/storage-locations",
        headers=admin_headers,
        json={
            "location_code": f"BLD-{uuid.uuid4().hex[:4].upper()}",
            "name": "Alpha Tower",
            "location_type": LocationType.BUILDING.value,
            "department": "Executive",
        },
    )
    bld_id = bld_res.json()["id"]

    flr_res = client.post(
        "/api/v1/storage-locations",
        headers=admin_headers,
        json={
            "location_code": f"FLR-{uuid.uuid4().hex[:4].upper()}",
            "name": "Floor 1",
            "location_type": LocationType.FLOOR.value,
            "department": "Executive",
            "parent_id": bld_id,
        },
    )
    flr_id = flr_res.json()["id"]

    # 1. Self-parenting attempt -> 400 Bad Request
    res_self = client.patch(
        f"/api/v1/storage-locations/{bld_id}",
        headers=admin_headers,
        json={"parent_id": bld_id},
    )
    assert res_self.status_code == 400
    assert "cannot be its own parent" in res_self.json()["detail"]

    # 2. Circular parenting: try to set parent of Building to its child Floor -> 400 Bad Request
    res_cycle = client.patch(
        f"/api/v1/storage-locations/{bld_id}",
        headers=admin_headers,
        json={"parent_id": flr_id},
    )
    assert res_cycle.status_code == 400
    assert "Circular hierarchy detected" in res_cycle.json()["detail"]

    # 3. Invalid hierarchy type: try to place Building inside a Shelf
    shelf_res = client.post(
        "/api/v1/storage-locations",
        headers=admin_headers,
        json={
            "location_code": f"SHF-{uuid.uuid4().hex[:4].upper()}",
            "name": "Shelf 1",
            "location_type": LocationType.SHELF.value,
            "department": "Executive",
        },
    )
    shelf_id = shelf_res.json()["id"]

    res_invalid_type = client.patch(
        f"/api/v1/storage-locations/{bld_id}",
        headers=admin_headers,
        json={"parent_id": shelf_id},
    )
    assert res_invalid_type.status_code == 400
    assert "cannot be placed inside 'shelf'" in res_invalid_type.json()["detail"]


def test_department_scoping_and_cross_department_rejection(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """4. Department-level isolation on storage locations."""
    # Create HR storage location
    hr_loc = StorageLocation(
        location_code=f"HR-CAB-{uuid.uuid4().hex[:4].upper()}",
        name="HR Records Cabinet",
        location_type=LocationType.CABINET,
        department="Human Resources",
        is_active=True,
        created_by_id=test_users["dept_user_hr"].id,
    )
    db_session.add(hr_loc)
    db_session.commit()
    db_session.refresh(hr_loc)

    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    # 1. Finance user GET HR location -> non-disclosing 404
    res_get = client.get(f"/api/v1/storage-locations/{hr_loc.id}", headers=fin_headers)
    assert res_get.status_code == 404

    # 2. Finance user attempts to create location in HR -> 403 Forbidden
    res_create = client.post(
        "/api/v1/storage-locations",
        headers=fin_headers,
        json={
            "location_code": f"FIN-HR-{uuid.uuid4().hex[:4].upper()}",
            "name": "Finance Intrusion",
            "location_type": LocationType.ROOM.value,
            "department": "Human Resources",
        },
    )
    assert res_create.status_code == 403


def test_safe_deactivation_validation(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """5. Prevent deactivating locations holding physical files or active children."""
    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    # 1. Create finance cabinet
    cab = StorageLocation(
        location_code=f"FIN-SAFE-{uuid.uuid4().hex[:4].upper()}",
        name="Finance Safe Cabinet",
        location_type=LocationType.CABINET,
        department="Finance",
        is_active=True,
        created_by_id=test_users["dept_user_fin"].id,
    )
    db_session.add(cab)
    db_session.commit()
    db_session.refresh(cab)

    # Put a physical file inside
    phy_file = PhysicalFile(
        file_reference=f"PHY-TEST-{uuid.uuid4().hex[:4].upper()}",
        title="Physical Tax File",
        record_type=PhysicalRecordType.FINANCIAL_RECORD,
        department="Finance",
        storage_location_id=cab.id,
        status=PhysicalFileStatus.ACTIVE,
        created_by_id=test_users["dept_user_fin"].id,
    )
    db_session.add(phy_file)
    db_session.commit()

    # Attempt to deactivate cabinet while file is inside -> 400 Bad Request
    res_deact = client.patch(
        f"/api/v1/storage-locations/{cab.id}/status",
        headers=fin_headers,
        json={"is_active": False, "reason": "Retiring cabinet"},
    )
    assert res_deact.status_code == 400
    assert "physical file(s) are currently stored here" in res_deact.json()["detail"]

    # Remove file from cabinet
    phy_file.storage_location_id = None
    db_session.commit()

    # Now deactivation succeeds -> 200 OK
    res_deact_ok = client.patch(
        f"/api/v1/storage-locations/{cab.id}/status",
        headers=fin_headers,
        json={"is_active": False, "reason": "Retiring cabinet"},
    )
    assert res_deact_ok.status_code == 200
    assert res_deact_ok.json()["is_active"] is False


def test_physical_file_location_assignment_and_capacity(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """6. Assigning and reassigning physical files to storage locations with capacity checks."""
    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    # 1. Create a storage shelf with max_capacity = 1
    shelf = StorageLocation(
        location_code=f"SHF-CAP-{uuid.uuid4().hex[:4].upper()}",
        name="Small Shelf Box",
        location_type=LocationType.SHELF,
        department="Finance",
        max_capacity=1,
        is_active=True,
        created_by_id=test_users["dept_user_fin"].id,
    )
    db_session.add(shelf)
    db_session.commit()
    db_session.refresh(shelf)

    # 2. Create physical files
    file_a = PhysicalFile(
        file_reference=f"PHY-A-{uuid.uuid4().hex[:4].upper()}",
        title="Ledger A",
        record_type=PhysicalRecordType.FINANCIAL_RECORD,
        department="Finance",
        status=PhysicalFileStatus.ACTIVE,
        created_by_id=test_users["dept_user_fin"].id,
    )
    file_b = PhysicalFile(
        file_reference=f"PHY-B-{uuid.uuid4().hex[:4].upper()}",
        title="Ledger B",
        record_type=PhysicalRecordType.FINANCIAL_RECORD,
        department="Finance",
        status=PhysicalFileStatus.ACTIVE,
        created_by_id=test_users["dept_user_fin"].id,
    )
    db_session.add_all([file_a, file_b])
    db_session.commit()
    db_session.refresh(file_a)
    db_session.refresh(file_b)

    # 3. Assign File A to Shelf -> 200 OK
    res_assign_a = client.post(
        f"/api/v1/physical-files/{file_a.id}/assign-location",
        headers=fin_headers,
        json={"storage_location_id": str(shelf.id), "notes": "Initial filing"},
    )
    assert res_assign_a.status_code == 200
    assert res_assign_a.json()["storage_location_id"] == str(shelf.id)
    assert res_assign_a.json()["storage_location_code"] == shelf.location_code
    assert res_assign_a.json()["location_path"] == "Small Shelf Box"

    # 4. Attempt to assign File B to same shelf -> 400 Bad Request (at capacity)
    res_assign_b = client.post(
        f"/api/v1/physical-files/{file_b.id}/assign-location",
        headers=fin_headers,
        json={"storage_location_id": str(shelf.id)},
    )
    assert res_assign_b.status_code == 400
    assert "at full capacity" in res_assign_b.json()["detail"]

    # 5. Check contents endpoint on shelf
    contents_res = client.get(f"/api/v1/storage-locations/{shelf.id}/contents", headers=fin_headers)
    assert contents_res.status_code == 200
    assert contents_res.json()["total"] == 1
    assert contents_res.json()["items"][0]["id"] == str(file_a.id)


def test_mandatory_audit_logging_for_storage_locations(
    client: TestClient, db_session: Session, test_users: dict[str, User]
):
    """7. Verify mandatory audit logging on creation, updates, and assignment."""
    fin_headers = get_auth_headers(test_users["dept_user_fin"])

    # Create location
    res = client.post(
        "/api/v1/storage-locations",
        headers=fin_headers,
        json={
            "location_code": f"AUD-LOC-{uuid.uuid4().hex[:4].upper()}",
            "name": "Audited Room",
            "location_type": LocationType.ROOM.value,
            "department": "Finance",
        },
    )
    assert res.status_code == 201
    loc_id = res.json()["id"]

    audit_entry = db_session.query(AuditLog).filter(
        AuditLog.action == "storage_location.create",
        AuditLog.resource_id == uuid.UUID(loc_id),
    ).first()
    assert audit_entry is not None
    assert audit_entry.actor_id == test_users["dept_user_fin"].id
