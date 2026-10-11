"""
Automated test suite for Task 3.3: Secure Document Download and Role-Based Access Checks.
Tests:
- Authorized administrator download
- Authorized records officer download
- Department user accessing an allowed department document
- Department user denied access to another department's document
- Approver access based on explicit authorization (department vs other department)
- Auditor read-only restrictions
- Read-only user restrictions
- Confidential document restrictions
- Missing and invalid bearer tokens
- Missing document and missing version
- Missing stored binary on disk
- Malicious storage keys and path traversal
- Correct response content and checksum
- Correct Content-Disposition and security headers
- Access to historical versions
- Audit events recorded for successful downloads and denied attempts
- Audit-write failure handling
"""
import io
import uuid
import hashlib
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus
from app.models.audit import AuditLog, AuditOutcome
from app.jwt import create_access_token
from app.services.storage import storage_service
from app.services.audit import AuditWriteError, audit_service

SAMPLE_PDF_V1 = b"%PDF-1.4\nVersion 1 Content\n%%EOF\n"
SAMPLE_PDF_V2 = b"%PDF-1.4\nVersion 2 Revised Content\n%%EOF\n"

@pytest.fixture
def test_document_setup(role_user_factory, db_session):
    """
    Creates an isolated document with 2 versions belonging to 'Finance' department.
    Classification: 'General'.
    """
    creator = role_user_factory(role=UserRole.DEPARTMENT_USER)
    creator_user = creator["user"]
    creator_user.department = "Finance"
    db_session.commit()

    # Stage and finalize Version 1
    v1_temp, v1_hash, v1_size = storage_service.stage_file(io.BytesIO(SAMPLE_PDF_V1))
    v1_key = storage_service.generate_storage_key("pdf")
    storage_service.finalize_staged_file(v1_temp, v1_key)

    doc = DigitalDocument(
        document_reference=f"DOC-TEST-{uuid.uuid4().hex[:8].upper()}",
        title="Q3 Financial Overview",
        subject="Quarterly Financials",
        department="Finance",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=creator_user.id,
    )
    db_session.add(doc)
    db_session.flush()

    ver1 = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=v1_key,
        original_filename="Finance_Q3_v1.pdf",
        mime_type="application/pdf",
        file_size_bytes=v1_size,
        file_hash_sha256=v1_hash,
        created_by_id=creator_user.id,
    )
    db_session.add(ver1)

    # Stage and finalize Version 2 (historical version test)
    v2_temp, v2_hash, v2_size = storage_service.stage_file(io.BytesIO(SAMPLE_PDF_V2))
    v2_key = storage_service.generate_storage_key("pdf")
    storage_service.finalize_staged_file(v2_temp, v2_key)

    ver2 = DocumentVersion(
        document_id=doc.id,
        version_number=2,
        storage_key=v2_key,
        original_filename="Finance_Q3_v2.pdf",
        mime_type="application/pdf",
        file_size_bytes=v2_size,
        file_hash_sha256=v2_hash,
        created_by_id=creator_user.id,
    )
    db_session.add(ver2)
    db_session.commit()
    db_session.refresh(doc)

    yield {
        "document": doc,
        "version1": ver1,
        "version2": ver2,
        "creator": creator_user,
    }

    # Teardown: delete stored files and DB records
    p1 = storage_service.resolve_storage_path(v1_key)
    p2 = storage_service.resolve_storage_path(v2_key)
    p1.unlink(missing_ok=True)
    p2.unlink(missing_ok=True)
    try:
        db_session.delete(doc)
        db_session.commit()
    except Exception:
        db_session.rollback()

@pytest.fixture
def confidential_document_setup(role_user_factory, db_session):
    """Creates a CONFIDENTIAL document in Legal department."""
    creator = role_user_factory(role=UserRole.DEPARTMENT_USER)
    creator_user = creator["user"]
    creator_user.department = "Legal"
    db_session.commit()

    temp_path, f_hash, f_size = storage_service.stage_file(io.BytesIO(SAMPLE_PDF_V1))
    s_key = storage_service.generate_storage_key("pdf")
    storage_service.finalize_staged_file(temp_path, s_key)

    doc = DigitalDocument(
        document_reference=f"DOC-CONF-{uuid.uuid4().hex[:8].upper()}",
        title="Merger Agreement",
        department="Legal",
        classification="CONFIDENTIAL",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=creator_user.id,
    )
    db_session.add(doc)
    db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=s_key,
        original_filename="Merger_Contract.pdf",
        mime_type="application/pdf",
        file_size_bytes=f_size,
        file_hash_sha256=f_hash,
        created_by_id=creator_user.id,
    )
    db_session.add(ver)
    db_session.commit()
    db_session.refresh(doc)

    yield {
        "document": doc,
        "version": ver,
        "creator": creator_user,
    }

    path = storage_service.resolve_storage_path(s_key)
    path.unlink(missing_ok=True)
    try:
        db_session.delete(doc)
        db_session.commit()
    except Exception:
        db_session.rollback()


def test_download_administrator_success(client, role_user_factory, test_document_setup):
    """Administrator can download across any department."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    doc = test_document_setup["document"]

    url = f"/api/v1/documents/{doc.id}/versions/1/download"
    res = client.get(url, headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    assert res.content == SAMPLE_PDF_V1
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["x-content-type-options"] == "nosniff"
    assert 'attachment; filename="Finance_Q3_v1.pdf"' in res.headers["content-disposition"]


def test_download_records_officer_success(client, role_user_factory, test_document_setup):
    """Records Officer can download across departments for records administration."""
    ro = role_user_factory(role=UserRole.RECORDS_OFFICER)["user"]
    token = create_access_token(user_id=ro.id)
    doc = test_document_setup["document"]

    url = f"/api/v1/documents/{doc.id}/versions/1/download"
    res = client.get(url, headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    assert res.content == SAMPLE_PDF_V1


def test_download_department_user_same_department(client, role_user_factory, test_document_setup, db_session):
    """Department user in 'Finance' can download a 'Finance' document."""
    dept_user = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Finance"
    db_session.commit()
    token = create_access_token(user_id=dept_user.id)
    doc = test_document_setup["document"]

    url = f"/api/v1/documents/{doc.id}/versions/1/download"
    res = client.get(url, headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    assert res.content == SAMPLE_PDF_V1


def test_download_department_user_different_department_denied(client, role_user_factory, test_document_setup, db_session):
    """Department user in 'HR' is denied downloading a 'Finance' document."""
    dept_user = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Human Resources"
    db_session.commit()
    token = create_access_token(user_id=dept_user.id)
    doc = test_document_setup["document"]

    url = f"/api/v1/documents/{doc.id}/versions/1/download"
    res = client.get(url, headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]


def test_download_approver_explicit_authorization(client, role_user_factory, test_document_setup, db_session):
    """Approver can download from own department, but is denied for external department without explicit scope."""
    approver_same_dept = role_user_factory(role=UserRole.APPROVER)["user"]
    approver_same_dept.department = "Finance"
    db_session.commit()
    token_allowed = create_access_token(user_id=approver_same_dept.id)

    approver_other_dept = role_user_factory(role=UserRole.APPROVER)["user"]
    approver_other_dept.department = "Procurement"
    db_session.commit()
    token_denied = create_access_token(user_id=approver_other_dept.id)

    doc = test_document_setup["document"]
    url = f"/api/v1/documents/{doc.id}/versions/1/download"

    # Same department allowed
    res1 = client.get(url, headers={"Authorization": f"Bearer {token_allowed}"})
    assert res1.status_code == 200

    # Other department denied
    res2 = client.get(url, headers={"Authorization": f"Bearer {token_denied}"})
    assert res2.status_code == 403


def test_download_auditor_restrictions(client, role_user_factory, confidential_document_setup, test_document_setup, db_session):
    """Auditor can download documents within assigned audit department, but is denied for external departments."""
    auditor = role_user_factory(role=UserRole.AUDITOR)["user"]
    auditor.department = "Finance"
    db_session.commit()
    token = create_access_token(user_id=auditor.id)

    # 1. Allowed: Finance document (own audit scope)
    doc_fin = test_document_setup["document"]
    res1 = client.get(f"/api/v1/documents/{doc_fin.id}/versions/1/download", headers={"Authorization": f"Bearer {token}"})
    assert res1.status_code == 200

    # 2. Denied: Legal document (outside audit scope)
    doc_legal = confidential_document_setup["document"]
    res2 = client.get(f"/api/v1/documents/{doc_legal.id}/versions/1/download", headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 403
    assert "not authorized" in res2.json()["detail"].lower()



def test_download_readonly_user_restrictions(client, role_user_factory, test_document_setup, confidential_document_setup, db_session):
    """Read-only user can access general document in own department, but cannot access other departments or confidential files."""
    ro_user = role_user_factory(role=UserRole.READ_ONLY)["user"]
    ro_user.department = "Finance"
    db_session.commit()
    token = create_access_token(user_id=ro_user.id)

    # 1. Allowed: General document in Finance
    doc_finance = test_document_setup["document"]
    res1 = client.get(f"/api/v1/documents/{doc_finance.id}/versions/1/download", headers={"Authorization": f"Bearer {token}"})
    assert res1.status_code == 200

    # 2. Denied: Confidential document even if in same department
    conf_doc = confidential_document_setup["document"]
    res2 = client.get(f"/api/v1/documents/{conf_doc.id}/versions/1/download", headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 403


def test_download_historical_version(client, role_user_factory, test_document_setup):
    """Verify downloading historical versions 1 and 2 returns distinct content."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    doc = test_document_setup["document"]

    res_v1 = client.get(f"/api/v1/documents/{doc.id}/versions/1/download", headers={"Authorization": f"Bearer {token}"})
    assert res_v1.status_code == 200
    assert res_v1.content == SAMPLE_PDF_V1

    res_v2 = client.get(f"/api/v1/documents/{doc.id}/versions/2/download", headers={"Authorization": f"Bearer {token}"})
    assert res_v2.status_code == 200
    assert res_v2.content == SAMPLE_PDF_V2


def test_download_missing_authentication(client, test_document_setup):
    """Verify request without Authorization header returns HTTP 401."""
    doc = test_document_setup["document"]
    url = f"/api/v1/documents/{doc.id}/versions/1/download"
    res = client.get(url)
    assert res.status_code == 401


def test_download_invalid_token(client, test_document_setup):
    """Verify request with invalid JWT returns HTTP 401."""
    doc = test_document_setup["document"]
    url = f"/api/v1/documents/{doc.id}/versions/1/download"
    res = client.get(url, headers={"Authorization": "Bearer bad_token"})
    assert res.status_code == 401


def test_download_nonexistent_document(client, role_user_factory):
    """Verify nonexistent document returns HTTP 404."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    fake_id = uuid.uuid4()
    url = f"/api/v1/documents/{fake_id}/versions/1/download"
    res = client.get(url, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 404


def test_download_nonexistent_version(client, role_user_factory, test_document_setup):
    """Verify requesting version 99 returns HTTP 404."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    doc = test_document_setup["document"]
    url = f"/api/v1/documents/{doc.id}/versions/99/download"
    res = client.get(url, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 404


def test_download_missing_stored_binary(client, role_user_factory, test_document_setup, db_session):
    """Verify that if binary file on disk is deleted, HTTP 404 is returned without exposing paths."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    doc = test_document_setup["document"]
    ver = test_document_setup["version1"]

    # Delete disk file
    path = storage_service.resolve_storage_path(ver.storage_key)
    path.unlink(missing_ok=True)

    url = f"/api/v1/documents/{doc.id}/versions/1/download"
    res = client.get(url, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()
    assert "storage" not in res.json()["detail"].lower()
    assert "/" not in res.json()["detail"]


def test_download_path_traversal_rejection(client, role_user_factory, test_document_setup, db_session):
    """Verify malicious storage key with path traversal in DB triggers security rejection."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    doc = test_document_setup["document"]
    ver = test_document_setup["version1"]

    # Temporarily set malicious storage key in DB
    original_key = ver.storage_key
    ver.storage_key = "../../etc/passwd"
    db_session.commit()

    try:
        url = f"/api/v1/documents/{doc.id}/versions/1/download"
        res = client.get(url, headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 400
        assert "Invalid storage reference" in res.json()["detail"]
    finally:
        ver.storage_key = original_key
        db_session.commit()


def test_download_audit_events_recorded(client, role_user_factory, test_document_setup, db_session):
    """Verify successful download and denied download create persistent AuditLog entries."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token_admin = create_access_token(user_id=admin.id)

    dept_user = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Human Resources"  # Document is in Finance
    db_session.commit()
    token_hr = create_access_token(user_id=dept_user.id)

    doc = test_document_setup["document"]
    url = f"/api/v1/documents/{doc.id}/versions/1/download"

    # 1. Successful download by Admin
    res1 = client.get(url, headers={"Authorization": f"Bearer {token_admin}", "X-Correlation-ID": "corr-12345"})
    assert res1.status_code == 200

    # Verify audit success entry
    success_audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.actor_id == admin.id, AuditLog.outcome == AuditOutcome.SUCCESS)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert success_audit is not None
    assert success_audit.action == "document.download"
    assert success_audit.correlation_id == "corr-12345"

    # 2. Denied download by HR user
    res2 = client.get(url, headers={"Authorization": f"Bearer {token_hr}", "X-Correlation-ID": "corr-denied-99"})
    assert res2.status_code == 403

    # Verify audit denial entry
    denied_audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.actor_id == dept_user.id, AuditLog.outcome == AuditOutcome.DENIED)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert denied_audit is not None
    assert denied_audit.action == "document.download"
    assert denied_audit.correlation_id == "corr-denied-99"
    assert "user_role" in denied_audit.details


def test_download_audit_write_failure_handling(client, role_user_factory, test_document_setup):
    """
    Verify that if audit recording fails on download or denial,
    the endpoint does not silently pretend auditing succeeded.
    """
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    doc = test_document_setup["document"]
    url = f"/api/v1/documents/{doc.id}/versions/1/download"

    # Simulate audit write failure on log_from_request
    with patch("app.api.v1.documents.audit_service.log_from_request", side_effect=AuditWriteError("Simulated Audit Storage Failure")):
        with pytest.raises(AuditWriteError):
            client.get(url, headers={"Authorization": f"Bearer {token}"})

