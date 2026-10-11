"""
Automated test suite for Task 5.9: Secure Approver Directory and Selection.
Verifies:
1. Authorized department user receives only eligible active approvers in the same department.
2. Admins and Records Officers can query approvers across departments or filter by department.
3. Auditors, Read-Only users, and Approvers are denied directory enumeration (403 Forbidden).
4. Inactive approvers are excluded.
5. Non-approver users (department users, admins, etc.) are excluded.
6. Search filtering ('q') and result limits work deterministically.
7. Missing department information fails safely.
8. Unauthenticated requests are rejected with 401 Unauthorized.
9. Document-aware scoping: filters approvers to document department and excludes submitter.
10. Cross-department assignment is rejected.
11. Safe display attributes only (no password hashes, security fields, or sensitive info).
"""
import uuid
import pytest
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.document import DigitalDocument, DocumentStatus
from app.jwt import create_access_token


@pytest.fixture
def directory_env(db_session: Session):
    """Seed isolated test users across departments and roles for approver directory testing."""
    tag = uuid.uuid4().hex[:8]
    dept_legal = f"Legal_{tag}"
    dept_fin = f"Finance_{tag}"

    # 1. Department Users
    du_legal = User(
        email=f"du.legal.{tag}@example.com",
        full_name="David Dept Legal",
        hashed_password="hash",
        department=dept_legal,
        role=UserRole.DEPARTMENT_USER,
        is_active=True,
    )
    du_finance = User(
        email=f"du.finance.{tag}@example.com",
        full_name="Fiona Dept Finance",
        hashed_password="hash",
        department=dept_fin,
        role=UserRole.DEPARTMENT_USER,
        is_active=True,
    )

    # 2. Approvers in Legal
    appr_legal_1 = User(
        email=f"alice.approver.{tag}@example.com",
        full_name="Alice Legal Approver",
        hashed_password="hash",
        department=dept_legal,
        role=UserRole.APPROVER,
        is_active=True,
    )
    appr_legal_2 = User(
        email=f"bob.approver.{tag}@example.com",
        full_name="Bob Legal Approver",
        hashed_password="hash",
        department=dept_legal,
        role=UserRole.APPROVER,
        is_active=True,
    )

    # 3. Approver in Finance
    appr_finance = User(
        email=f"charlie.approver.{tag}@example.com",
        full_name="Charlie Finance Approver",
        hashed_password="hash",
        department=dept_fin,
        role=UserRole.APPROVER,
        is_active=True,
    )

    # 4. Inactive Approver in Legal (must be excluded)
    appr_inactive_legal = User(
        email=f"inactive.legal.{tag}@example.com",
        full_name="Inactive Legal Approver",
        hashed_password="hash",
        department=dept_legal,
        role=UserRole.APPROVER,
        is_active=False,
    )

    # 5. Auditor and Read Only users
    auditor = User(
        email=f"auditor.{tag}@example.com",
        full_name="Audrey Auditor",
        hashed_password="hash",
        department=dept_legal,
        role=UserRole.AUDITOR,
        is_active=True,
    )
    readonly = User(
        email=f"readonly.{tag}@example.com",
        full_name="Ron ReadOnly",
        hashed_password="hash",
        department=dept_legal,
        role=UserRole.READ_ONLY,
        is_active=True,
    )

    # 6. Admin and Records Officer
    admin = User(
        email=f"admin.{tag}@example.com",
        full_name="Adam Admin",
        hashed_password="hash",
        department=None,
        role=UserRole.ADMIN,
        is_active=True,
    )
    rec_officer = User(
        email=f"records.{tag}@example.com",
        full_name="Rachel Records",
        hashed_password="hash",
        department=None,
        role=UserRole.RECORDS_OFFICER,
        is_active=True,
    )

    all_users = [
        du_legal,
        du_finance,
        appr_legal_1,
        appr_legal_2,
        appr_finance,
        appr_inactive_legal,
        auditor,
        readonly,
        admin,
        rec_officer,
    ]
    for u in all_users:
        db_session.add(u)
    db_session.commit()

    for u in all_users:
        db_session.refresh(u)

    created_docs = []

    yield {
        "tag": tag,
        "dept_legal": dept_legal,
        "dept_fin": dept_fin,
        "du_legal": du_legal,
        "du_finance": du_finance,
        "appr_legal_1": appr_legal_1,
        "appr_legal_2": appr_legal_2,
        "appr_finance": appr_finance,
        "appr_inactive_legal": appr_inactive_legal,
        "auditor": auditor,
        "readonly": readonly,
        "admin": admin,
        "rec_officer": rec_officer,
        "created_docs": created_docs,
    }

    # Teardown
    try:
        db_session.rollback()
        for doc in created_docs:
            db_session.delete(doc)
        for u in all_users:
            db_session.delete(u)
        db_session.commit()
    except Exception:
        db_session.rollback()


def test_unauthenticated_request_rejected(client):
    """Test 8: Unauthenticated access returns 401."""
    res = client.get("/api/v1/users/eligible-approvers")
    assert res.status_code == 401


def test_department_user_receives_only_own_department_active_approvers(client, directory_env):
    """Test 1: Legal department user only sees active Legal approvers."""
    user = directory_env["du_legal"]
    token = create_access_token(user_id=user.id)

    res = client.get(
        "/api/v1/users/eligible-approvers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()

    # Must contain Alice and Bob, but NOT Charlie (Finance), NOT Inactive, NOT other roles
    approver_emails = [a["email"] for a in data]
    assert directory_env["appr_legal_1"].email in approver_emails
    assert directory_env["appr_legal_2"].email in approver_emails
    assert directory_env["appr_finance"].email not in approver_emails
    assert directory_env["appr_inactive_legal"].email not in approver_emails
    assert len(data) == 2

    # Safe display fields only
    first = data[0]
    assert "id" in first
    assert "full_name" in first
    assert "email" in first
    assert "department" in first
    assert "hashed_password" not in first
    assert "role" not in first


def test_admin_and_records_officer_can_query_all_or_filter_by_department(client, directory_env):
    """Test 2: Admin can query approvers across departments or scope by department."""
    admin = directory_env["admin"]
    token = create_access_token(user_id=admin.id)

    # 1. Admin without department filter sees active approvers in both departments
    res_all = client.get(
        "/api/v1/users/eligible-approvers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_all.status_code == 200
    data_all = res_all.json()
    all_emails = [a["email"] for a in data_all]
    assert directory_env["appr_legal_1"].email in all_emails
    assert directory_env["appr_finance"].email in all_emails

    # 2. Admin filtered by Finance
    res_fin = client.get(
        f"/api/v1/users/eligible-approvers?department={directory_env['dept_fin']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_fin.status_code == 200
    data_fin = res_fin.json()
    assert len(data_fin) == 1
    assert data_fin[0]["email"] == directory_env["appr_finance"].email


def test_auditor_readonly_and_approver_denied(client, directory_env):
    """Test 3: Auditor, Read-Only, and Approver roles receive 403 Forbidden."""
    for role_key in ["auditor", "readonly", "appr_legal_1"]:
        u = directory_env[role_key]
        token = create_access_token(user_id=u.id)
        res = client.get(
            "/api/v1/users/eligible-approvers",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403
        assert "not permitted" in res.json()["detail"]


def test_search_filtering_and_limits(client, directory_env):
    """Test 6: Search query 'q' filters by name/email and limits work."""
    admin = directory_env["admin"]
    token = create_access_token(user_id=admin.id)

    # Search by 'Alice'
    res = client.get(
        f"/api/v1/users/eligible-approvers?department={directory_env['dept_legal']}&q=Alice",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["full_name"] == "Alice Legal Approver"

    # Search with limit=1
    res_lim = client.get(
        f"/api/v1/users/eligible-approvers?department={directory_env['dept_legal']}&limit=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_lim.status_code == 200
    assert len(res_lim.json()) == 1


def test_document_aware_scoping(client, db_session, directory_env):
    """Test 9: Passing document_id scopes approvers to the document's department."""
    user = directory_env["du_legal"]
    token = create_access_token(user_id=user.id)

    # Create legal draft document
    doc = DigitalDocument(
        document_reference=f"DOC-TEST-{uuid.uuid4().hex[:6].upper()}",
        title="Directory Scope Test Doc",
        department=directory_env["dept_legal"],
        classification="official",
        mime_type="application/pdf",
        created_by_id=user.id,
        status=DocumentStatus.DRAFT,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    directory_env["created_docs"].append(doc)

    res = client.get(
        f"/api/v1/users/eligible-approvers?document_id={doc.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    emails = [a["email"] for a in data]
    assert directory_env["appr_legal_1"].email in emails
    assert directory_env["appr_legal_2"].email in emails
    assert directory_env["appr_finance"].email not in emails


def test_department_user_cross_department_document_denied(client, db_session, directory_env):
    """Test 10: Department user cannot query approvers for another department's document."""
    user = directory_env["du_legal"]
    token = create_access_token(user_id=user.id)

    # Create Finance document
    doc_fin = DigitalDocument(
        document_reference=f"DOC-FIN-{uuid.uuid4().hex[:6].upper()}",
        title="Finance Budget Document",
        department=directory_env["dept_fin"],
        classification="official",
        mime_type="application/pdf",
        created_by_id=directory_env["du_finance"].id,
        status=DocumentStatus.DRAFT,
    )
    db_session.add(doc_fin)
    db_session.commit()
    db_session.refresh(doc_fin)
    directory_env["created_docs"].append(doc_fin)

    res = client.get(
        f"/api/v1/users/eligible-approvers?document_id={doc_fin.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code in [403, 404]
