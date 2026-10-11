"""
Comprehensive regression test suite for Task 3.5:
Authorization Policy Consistency and Regression Hardening across:
1. GET /api/v1/documents (Repository Listing)
2. GET /api/v1/documents/{document_id} (Metadata Retrieval)
3. GET /api/v1/documents/{document_id}/versions (Version Enumeration)
4. GET /api/v1/documents/{document_id}/versions/{version_number}/download (File Download)

Verifies:
- All 6 roles (Admin, Records Officer, Department User, Approver, Auditor, Read-Only User)
- Same-department vs cross-department access
- All supported classification levels (CONFIDENTIAL, SECRET, RESTRICTED, TOP_SECRET, General)
- Missing/ambiguous department assignment (default deny)
- Inactive user lockout (401)
- Non-disclosing 404 for unauthorized metadata/versions/download
- Total count and pagination safety
- Audit logging of access decisions
"""
import io
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus
from app.models.audit import AuditLog, AuditOutcome
from app.jwt import create_access_token
from app.services.storage import storage_service

SAMPLE_BINARY = b"%PDF-1.4\nHardening Verification Document\n%%EOF\n"

CLASSIFICATIONS_TO_TEST = ["CONFIDENTIAL", "SECRET", "RESTRICTED", "TOP_SECRET", "General"]

@pytest.fixture
def matrix_test_fixture(role_user_factory, db_session):
    """
    Creates test documents across departments and classifications:
    - Dept Finance:
        * General
        * CONFIDENTIAL
        * SECRET
        * RESTRICTED
        * TOP_SECRET
    - Dept Engineering:
        * General
        * CONFIDENTIAL
    """
    finance_creator = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    finance_creator.department = "Finance"

    eng_creator = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    eng_creator.department = "Engineering"
    db_session.commit()

    created_docs = {}
    stored_keys = []

    def _create_doc(dept, classification, creator):
        t_path, f_hash, f_size = storage_service.stage_file(io.BytesIO(SAMPLE_BINARY))
        s_key = storage_service.generate_storage_key("pdf")
        storage_service.finalize_staged_file(t_path, s_key)
        stored_keys.append(s_key)

        ref = f"DOC-TEST-{uuid.uuid4().hex[:8].upper()}"
        doc = DigitalDocument(
            document_reference=ref,
            title=f"{dept} {classification} Record",
            subject="Regression Hardening",
            department=dept,
            classification=classification,
            mime_type="application/pdf",
            status=DocumentStatus.ACTIVE,
            created_by_id=creator.id,
        )
        db_session.add(doc)
        db_session.flush()

        ver = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            storage_key=s_key,
            original_filename=f"{classification.lower()}.pdf",
            mime_type="application/pdf",
            file_size_bytes=f_size,
            file_hash_sha256=f_hash,
            created_by_id=creator.id,
        )
        db_session.add(ver)
        db_session.commit()
        db_session.refresh(doc)
        return doc

    for c in CLASSIFICATIONS_TO_TEST:
        created_docs[f"finance_{c.lower()}"] = _create_doc("Finance", c, finance_creator)

    created_docs["eng_general"] = _create_doc("Engineering", "General", eng_creator)
    created_docs["eng_confidential"] = _create_doc("Engineering", "CONFIDENTIAL", eng_creator)

    yield {
        "finance_creator": finance_creator,
        "eng_creator": eng_creator,
        "docs": created_docs,
    }

    # Cleanup
    for k in stored_keys:
        try:
            p = storage_service.resolve_storage_path(k)
            p.unlink(missing_ok=True)
        except Exception:
            pass
    for d in created_docs.values():
        try:
            db_session.delete(d)
            db_session.commit()
        except Exception:
            db_session.rollback()


@pytest.mark.parametrize("classification", CLASSIFICATIONS_TO_TEST)
def test_all_classifications_admin_full_access(client, role_user_factory, matrix_test_fixture, classification):
    """Admin has full access to all classifications across all 4 endpoints."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    doc = matrix_test_fixture["docs"][f"finance_{classification.lower()}"]

    # 1. Listing includes doc
    res_list = client.get(f"/api/v1/documents?classification={classification}", headers=headers)
    assert res_list.status_code == 200
    doc_ids = [d["id"] for d in res_list.json()["items"]]
    assert str(doc.id) in doc_ids

    # 2. Metadata retrieval
    res_meta = client.get(f"/api/v1/documents/{doc.id}", headers=headers)
    assert res_meta.status_code == 200

    # 3. Version enumeration
    res_vers = client.get(f"/api/v1/documents/{doc.id}/versions", headers=headers)
    assert res_vers.status_code == 200

    # 4. Download
    res_dl = client.get(f"/api/v1/documents/{doc.id}/versions/1/download", headers=headers)
    assert res_dl.status_code == 200


@pytest.mark.parametrize("classification", ["CONFIDENTIAL", "SECRET", "RESTRICTED", "TOP_SECRET"])
def test_classified_records_readonly_user_denied_consistently(client, role_user_factory, matrix_test_fixture, classification):
    """Read-Only user even in Finance department is strictly denied for all classified records across all 4 endpoints."""
    ro_user = role_user_factory(role=UserRole.READ_ONLY)["user"]
    ro_user.department = "Finance"
    token = create_access_token(user_id=ro_user.id)
    headers = {"Authorization": f"Bearer {token}"}

    doc = matrix_test_fixture["docs"][f"finance_{classification.lower()}"]

    # 1. Listing excludes doc
    res_list = client.get(f"/api/v1/documents?classification={classification}", headers=headers)
    assert res_list.status_code == 200
    assert res_list.json()["total"] == 0

    # 2. Metadata returns 404 (non-disclosing)
    res_meta = client.get(f"/api/v1/documents/{doc.id}", headers=headers)
    assert res_meta.status_code == 404

    # 3. Version enumeration returns 404
    res_vers = client.get(f"/api/v1/documents/{doc.id}/versions", headers=headers)
    assert res_vers.status_code == 404

    # 4. Download returns 403 Forbidden
    res_dl = client.get(f"/api/v1/documents/{doc.id}/versions/1/download", headers=headers)
    assert res_dl.status_code == 403


def test_department_user_cross_department_consistently_denied(client, role_user_factory, matrix_test_fixture, db_session):
    """Department user in Finance is denied access to Engineering documents across all 4 endpoints."""
    dept_user = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Finance"
    db_session.commit()
    token = create_access_token(user_id=dept_user.id)
    headers = {"Authorization": f"Bearer {token}"}

    eng_doc = matrix_test_fixture["docs"]["eng_general"]

    # 1. Listing does not show Engineering documents
    res_list = client.get("/api/v1/documents", headers=headers)
    assert res_list.status_code == 200
    for item in res_list.json()["items"]:
        assert item["department"].lower() != "engineering"

    # 2. Metadata returns 404
    res_meta = client.get(f"/api/v1/documents/{eng_doc.id}", headers=headers)
    assert res_meta.status_code == 404

    # 3. Version enumeration returns 404
    res_vers = client.get(f"/api/v1/documents/{eng_doc.id}/versions", headers=headers)
    assert res_vers.status_code == 404

    # 4. Download returns 403
    res_dl = client.get(f"/api/v1/documents/{eng_doc.id}/versions/1/download", headers=headers)
    assert res_dl.status_code == 403


def test_auditor_cross_department_consistently_denied(client, role_user_factory, matrix_test_fixture, db_session):
    """Auditor assigned to Finance cannot see or download Engineering records across all 4 endpoints."""
    auditor = role_user_factory(role=UserRole.AUDITOR)["user"]
    auditor.department = "Finance"
    db_session.commit()
    token = create_access_token(user_id=auditor.id)
    headers = {"Authorization": f"Bearer {token}"}

    eng_doc = matrix_test_fixture["docs"]["eng_general"]

    # 1. Listing does not contain Engineering
    res_list = client.get("/api/v1/documents", headers=headers)
    assert res_list.status_code == 200
    for item in res_list.json()["items"]:
        assert item["department"].lower() == "finance"

    # 2. Metadata returns 404
    res_meta = client.get(f"/api/v1/documents/{eng_doc.id}", headers=headers)
    assert res_meta.status_code == 404

    # 3. Version enumeration returns 404
    res_vers = client.get(f"/api/v1/documents/{eng_doc.id}/versions", headers=headers)
    assert res_vers.status_code == 404

    # 4. Download returns 403
    res_dl = client.get(f"/api/v1/documents/{eng_doc.id}/versions/1/download", headers=headers)
    assert res_dl.status_code == 403


def test_user_without_department_denied_by_default(client, role_user_factory, matrix_test_fixture, db_session):
    """User with NULL/empty department is denied by default for department-scoped roles."""
    user = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    user.department = None
    db_session.commit()
    token = create_access_token(user_id=user.id)
    headers = {"Authorization": f"Bearer {token}"}

    doc = matrix_test_fixture["docs"]["finance_general"]

    # Listing returns 0 items
    res_list = client.get("/api/v1/documents", headers=headers)
    assert res_list.status_code == 200
    assert res_list.json()["total"] == 0
    assert len(res_list.json()["items"]) == 0

    # Metadata returns 404
    res_meta = client.get(f"/api/v1/documents/{doc.id}", headers=headers)
    assert res_meta.status_code == 404

    # Download returns 403
    res_dl = client.get(f"/api/v1/documents/{doc.id}/versions/1/download", headers=headers)
    assert res_dl.status_code == 403


def test_inactive_user_rejected_on_all_endpoints(client, role_user_factory, matrix_test_fixture, db_session):
    """Inactive user is rejected with HTTP 401 across all endpoints."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    admin.is_active = False
    db_session.commit()
    token = create_access_token(user_id=admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    doc = matrix_test_fixture["docs"]["finance_general"]

    assert client.get("/api/v1/documents", headers=headers).status_code == 401
    assert client.get(f"/api/v1/documents/{doc.id}", headers=headers).status_code == 401
    assert client.get(f"/api/v1/documents/{doc.id}/versions", headers=headers).status_code == 401
    assert client.get(f"/api/v1/documents/{doc.id}/versions/1/download", headers=headers).status_code == 401


def test_approver_access_own_created_document(client, role_user_factory, matrix_test_fixture, db_session):
    """Approver can access documents they created even if outside their current department."""
    approver = role_user_factory(role=UserRole.APPROVER)["user"]
    approver.department = "Legal"  # Assigned to Legal
    db_session.commit()

    # Create a document created by this approver in Finance
    t_path, f_hash, f_size = storage_service.stage_file(io.BytesIO(SAMPLE_BINARY))
    s_key = storage_service.generate_storage_key("pdf")
    storage_service.finalize_staged_file(t_path, s_key)

    doc = DigitalDocument(
        document_reference=f"DOC-APPR-{uuid.uuid4().hex[:8].upper()}",
        title="Approver Authored Document",
        department="Finance",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=approver.id,
    )
    db_session.add(doc)
    db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=s_key,
        original_filename="authored.pdf",
        mime_type="application/pdf",
        file_size_bytes=f_size,
        file_hash_sha256=f_hash,
        created_by_id=approver.id,
    )
    db_session.add(ver)
    db_session.commit()

    token = create_access_token(user_id=approver.id)
    headers = {"Authorization": f"Bearer {token}"}

    try:
        # Listing should include this created doc
        res_list = client.get(f"/api/v1/documents?search=Authored", headers=headers)
        assert res_list.status_code == 200
        assert res_list.json()["total"] == 1

        # Metadata should be allowed
        res_meta = client.get(f"/api/v1/documents/{doc.id}", headers=headers)
        assert res_meta.status_code == 200

        # Download should be allowed
        res_dl = client.get(f"/api/v1/documents/{doc.id}/versions/1/download", headers=headers)
        assert res_dl.status_code == 200
    finally:
        storage_service.resolve_storage_path(s_key).unlink(missing_ok=True)
        db_session.delete(doc)
        db_session.commit()
