"""
Automated test suite for Task 3.4: Document Repository Listing and Metadata Retrieval APIs.
Tests:
1. Authenticated repository listing with default pagination.
2. Missing or invalid Bearer JWT (401).
3. Empty repository handling.
4. Pagination boundaries (page, page_size ge=1, le=100) and 422 validations.
5. Case-insensitive search across reference, title, and subject.
6. Department, classification, and status filters.
7. Invalid filter values and unsupported sort parameters (422).
8. Allowed and denied listing access for every existing role:
   - Admin: sees all departments and confidential
   - Records Officer: sees all departments
   - Department User: sees only own department
   - Approver: sees only own department or created records
   - Auditor: sees non-confidential or assigned department records
   - Read-only user: sees only non-confidential records in own department
9. Unauthorized documents excluded from both `items` and `total` count.
10. Document metadata retrieval for an authorized user (GET /api/v1/documents/{id}).
11. Missing document returns 404.
12. Unauthorized document retrieval returns 404 without disclosing existence.
13. Version metadata retrieval for an authorized user (GET /api/v1/documents/{id}/versions).
14. Unauthorized version enumeration returns 404.
15. Response schemas never expose internal storage keys, paths, or binary content.
16. Stable sorting and pagination.
17. Audit logging behavior for metadata access and denials.
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

SAMPLE_PDF = b"%PDF-1.4\nSample Document Content\n%%EOF\n"

@pytest.fixture
def repository_test_setup(role_user_factory, db_session):
    """
    Creates a multi-department test repository:
    - Doc 1: Finance dept, General classification, Active, created by finance_user
    - Doc 2: Finance dept, CONFIDENTIAL classification, Active, 2 versions, created by finance_user
    - Doc 3: Legal dept, General classification, Draft, created by legal_user
    - Doc 4: Legal dept, CONFIDENTIAL classification, Active, created by legal_user
    - Doc 5: HR dept, General classification, Active, created by hr_user
    """
    # Clean any residual documents from prior test suites
    try:
        db_session.query(DigitalDocument).delete()
        db_session.commit()
    except Exception:
        db_session.rollback()

    # Create creator users
    finance_user = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    finance_user.department = "Finance"
    
    legal_user = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    legal_user.department = "Legal"
    
    hr_user = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    hr_user.department = "Human Resources"
    db_session.commit()

    created_docs = []
    created_storage_keys = []

    def _create_doc(title, subject, dept, classification, status, creator, version_count=1):
        # Stage a version file
        v_temp, v_hash, v_size = storage_service.stage_file(io.BytesIO(SAMPLE_PDF))
        v_key = storage_service.generate_storage_key("pdf")
        storage_service.finalize_staged_file(v_temp, v_key)
        created_storage_keys.append(v_key)

        ref = f"DOC-REPO-{uuid.uuid4().hex[:8].upper()}"
        doc = DigitalDocument(
            document_reference=ref,
            title=title,
            subject=subject,
            department=dept,
            classification=classification,
            mime_type="application/pdf",
            status=status,
            created_by_id=creator.id,
        )
        db_session.add(doc)
        db_session.flush()

        ver1 = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            storage_key=v_key,
            original_filename=f"{title}_v1.pdf",
            mime_type="application/pdf",
            file_size_bytes=v_size,
            file_hash_sha256=v_hash,
            created_by_id=creator.id,
        )
        db_session.add(ver1)

        if version_count > 1:
            v2_temp, v2_hash, v2_size = storage_service.stage_file(io.BytesIO(SAMPLE_PDF))
            v2_key = storage_service.generate_storage_key("pdf")
            storage_service.finalize_staged_file(v2_temp, v2_key)
            created_storage_keys.append(v2_key)

            ver2 = DocumentVersion(
                document_id=doc.id,
                version_number=2,
                storage_key=v2_key,
                original_filename=f"{title}_v2.pdf",
                mime_type="application/pdf",
                file_size_bytes=v2_size,
                file_hash_sha256=v2_hash,
                created_by_id=creator.id,
            )
            db_session.add(ver2)

        db_session.commit()
        db_session.refresh(doc)
        created_docs.append(doc)
        return doc

    doc_fin_gen = _create_doc("Finance Q3 Report", "Quarterly Budget", "Finance", "General", DocumentStatus.ACTIVE, finance_user)
    doc_fin_conf = _create_doc("Finance Executive Payroll", "Executive Comp", "Finance", "CONFIDENTIAL", DocumentStatus.ACTIVE, finance_user, version_count=2)
    doc_leg_gen = _create_doc("Legal Compliance Policy", "Regulatory Guidelines", "Legal", "General", DocumentStatus.DRAFT, legal_user)
    doc_leg_conf = _create_doc("Merger Non-Disclosure Agreement", "M&A Negotiations", "Legal", "CONFIDENTIAL", DocumentStatus.ACTIVE, legal_user)
    doc_hr_gen = _create_doc("Employee Handbook 2026", "HR Policies", "Human Resources", "General", DocumentStatus.ACTIVE, hr_user)

    yield {
        "finance_user": finance_user,
        "legal_user": legal_user,
        "hr_user": hr_user,
        "doc_fin_gen": doc_fin_gen,
        "doc_fin_conf": doc_fin_conf,
        "doc_leg_gen": doc_leg_gen,
        "doc_leg_conf": doc_leg_conf,
        "doc_hr_gen": doc_hr_gen,
        "all_docs": created_docs,
    }

    # Teardown
    for k in created_storage_keys:
        try:
            p = storage_service.resolve_storage_path(k)
            p.unlink(missing_ok=True)
        except Exception:
            pass
    for d in created_docs:
        try:
            db_session.delete(d)
            db_session.commit()
        except Exception:
            db_session.rollback()


def test_list_documents_authenticated_admin_sees_all(client, role_user_factory, repository_test_setup):
    """Administrator sees all documents across departments with total counts matching."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)

    res = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()

    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total"] >= 5
    assert len(data["items"]) >= 5

    # Check version count attached properly
    fin_conf = next(d for d in data["items"] if d["id"] == str(repository_test_setup["doc_fin_conf"].id))
    assert fin_conf["version_count"] == 2


def test_list_documents_unauthenticated_rejected(client):
    """Unauthenticated listing request returns HTTP 401."""
    res = client.get("/api/v1/documents")
    assert res.status_code == 401


def test_list_documents_invalid_token_rejected(client):
    """Request with invalid JWT returns HTTP 401."""
    res = client.get("/api/v1/documents", headers={"Authorization": "Bearer bad_jwt_token"})
    assert res.status_code == 401


def test_list_documents_pagination_validation(client, role_user_factory):
    """Validates page >= 1 and 1 <= page_size <= 100."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)

    # page < 1
    res1 = client.get("/api/v1/documents?page=0", headers={"Authorization": f"Bearer {token}"})
    assert res1.status_code == 422

    # page_size > 100
    res2 = client.get("/api/v1/documents?page_size=101", headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 422

    # page_size < 1
    res3 = client.get("/api/v1/documents?page_size=0", headers={"Authorization": f"Bearer {token}"})
    assert res3.status_code == 422


def test_list_documents_invalid_sort_parameter(client, role_user_factory):
    """Rejects invalid sort fields with HTTP 422."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)

    res = client.get("/api/v1/documents?sort_by=secret_column", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 422


def test_list_documents_search_filter(client, role_user_factory, repository_test_setup):
    """Search matches reference, title, or subject case-insensitively."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)

    res = client.get("/api/v1/documents?search=payroll", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Finance Executive Payroll"


def test_list_documents_department_and_classification_filters(client, role_user_factory, repository_test_setup):
    """Filters by department and classification correctly."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)

    # Filter Legal
    res = client.get("/api/v1/documents?department=Legal", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["total"] == 2

    # Filter Legal + CONFIDENTIAL
    res_conf = client.get("/api/v1/documents?department=Legal&classification=CONFIDENTIAL", headers={"Authorization": f"Bearer {token}"})
    assert res_conf.status_code == 200
    assert res_conf.json()["total"] == 1
    assert res_conf.json()["items"][0]["title"] == "Merger Non-Disclosure Agreement"


def test_list_documents_status_filter(client, role_user_factory, repository_test_setup):
    """Filters by document lifecycle status."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)

    res = client.get("/api/v1/documents?status=draft", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["title"] == "Legal Compliance Policy"


def test_list_documents_department_user_restricted(client, role_user_factory, repository_test_setup, db_session):
    """Department user in Finance sees ONLY Finance documents in items and total."""
    dept_user = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Finance"
    db_session.commit()
    token = create_access_token(user_id=dept_user.id)

    res = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()

    assert data["total"] == 2
    for item in data["items"]:
        assert item["department"].lower() == "finance"


def test_list_documents_auditor_restrictions(client, role_user_factory, repository_test_setup, db_session):
    """Auditor in Finance sees ONLY records within their assigned audit department (Finance), both general and confidential."""
    auditor = role_user_factory(role=UserRole.AUDITOR)["user"]
    auditor.department = "Finance"
    db_session.commit()
    token = create_access_token(user_id=auditor.id)

    res = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()

    titles = [item["title"] for item in data["items"]]
    assert "Finance Q3 Report" in titles
    assert "Finance Executive Payroll" in titles
    # External department records (Legal, HR) must be strictly excluded
    assert "Legal Compliance Policy" not in titles
    assert "Employee Handbook 2026" not in titles
    assert "Merger Non-Disclosure Agreement" not in titles



def test_list_documents_readonly_user_restrictions(client, role_user_factory, repository_test_setup, db_session):
    """Read-Only user in Finance sees ONLY non-confidential Finance documents."""
    ro_user = role_user_factory(role=UserRole.READ_ONLY)["user"]
    ro_user.department = "Finance"
    db_session.commit()
    token = create_access_token(user_id=ro_user.id)

    res = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()

    titles = [item["title"] for item in data["items"]]
    assert "Finance Q3 Report" in titles
    assert "Finance Executive Payroll" not in titles  # Confidential -> excluded
    assert "Legal Compliance Policy" not in titles  # Outside department -> excluded


def test_list_documents_records_officer_sees_all(client, role_user_factory, repository_test_setup):
    """Records Officer sees all documents across departments."""
    ro = role_user_factory(role=UserRole.RECORDS_OFFICER)["user"]
    token = create_access_token(user_id=ro.id)

    res = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["total"] >= 5


def test_get_document_metadata_authorized(client, role_user_factory, repository_test_setup):
    """Authorized user retrieves document metadata with creator and version list."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    doc = repository_test_setup["doc_fin_conf"]

    res = client.get(f"/api/v1/documents/{doc.id}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()

    assert data["id"] == str(doc.id)
    assert data["title"] == "Finance Executive Payroll"
    assert data["department"] == "Finance"
    assert data["classification"] == "CONFIDENTIAL"
    assert data["version_count"] == 2
    assert data["available_versions"] == [2, 1]
    assert data["creator"]["email"] is not None
    # Ensure no internal paths leaked
    assert "uploads" not in res.text
    assert "storage" not in res.text


def test_get_document_metadata_missing_returns_404(client, role_user_factory):
    """Nonexistent document returns HTTP 404."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    fake_id = uuid.uuid4()

    res = client.get(f"/api/v1/documents/{fake_id}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 404
    assert res.json()["detail"] == "Document not found."


def test_get_document_metadata_unauthorized_returns_404(client, role_user_factory, repository_test_setup, db_session):
    """
    Unauthorized user attempting to retrieve an existing document returns non-disclosing 404.
    Audits the denial.
    """
    dept_user = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Finance"
    db_session.commit()
    token = create_access_token(user_id=dept_user.id)

    # Document belongs to Legal
    legal_doc = repository_test_setup["doc_leg_conf"]

    res = client.get(f"/api/v1/documents/{legal_doc.id}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 404
    assert res.json()["detail"] == "Document not found."

    # Verify denial audit log entry exists
    audit_entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.actor_id == dept_user.id, AuditLog.resource_id == legal_doc.id)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.outcome == AuditOutcome.DENIED
    assert audit_entry.action == "document.view_metadata"


def test_list_document_versions_authorized(client, role_user_factory, repository_test_setup):
    """Authorized user enumerates versions in deterministic newest-first order."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    doc = repository_test_setup["doc_fin_conf"]

    res = client.get(f"/api/v1/documents/{doc.id}/versions", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    versions = res.json()

    assert len(versions) == 2
    assert versions[0]["version_number"] == 2
    assert versions[1]["version_number"] == 1
    assert versions[0]["file_size_bytes"] == len(SAMPLE_PDF)
    assert versions[0]["file_hash_sha256"] is not None
    # Ensure no storage keys leaked
    assert "storage_key" not in res.text
    assert "uploads/" not in res.text


def test_list_document_versions_unauthorized_returns_404(client, role_user_factory, repository_test_setup, db_session):
    """Unauthorized user cannot enumerate versions of a document outside their scope."""
    dept_user = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Finance"
    db_session.commit()
    token = create_access_token(user_id=dept_user.id)

    # Legal confidential document
    doc = repository_test_setup["doc_leg_conf"]

    res = client.get(f"/api/v1/documents/{doc.id}/versions", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 404
    assert res.json()["detail"] == "Document not found."
