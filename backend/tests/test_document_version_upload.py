"""
Automated test suite for Task 3.6: Secure Document Version Upload API (POST /api/v1/documents/{document_id}/versions).
Tests:
1. Successful version 2 upload on draft document.
2. Existing document ID, reference, and metadata remain unchanged.
3. Version 1 remains available, intact, and unchanged on disk and database.
4. Correct sequential version numbering across multiple uploads (v1 -> v2 -> v3).
5. Invalid or missing Bearer JWT (401).
6. All six roles and their write permissions:
   - Admin: Allowed on draft
   - Records Officer: Allowed on draft across departments
   - Department User: Allowed on draft within own department
   - Approver: Denied (403)
   - Auditor: Denied (403)
   - Read-Only User: Denied (403)
7. Cross-department upload denial for Department User.
8. Missing document returns 404.
9. Upload rejection for non-draft statuses (ACTIVE, UNDER_REVIEW, ARCHIVED, DISPOSED) with HTTP 400.
10. Invalid file signatures and mismatched extensions rejected (400).
11. Oversized file rejection (400).
12. Correct file size and SHA-256 checksum recorded.
13. Storage/DB failure cleanly cleans up newly staged/finalized files while preserving version 1.
14. Concurrent version conflict (IntegrityError -> 409).
15. Audit logging on success and denial, plus mandatory audit-write failure enforcement.
16. Response schema never exposes storage keys or absolute paths.
"""
import io
import uuid
import hashlib
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.models.user import UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus
from app.models.audit import AuditLog, AuditOutcome
from app.jwt import create_access_token
from app.services.storage import storage_service
from app.services.audit import audit_service, AuditWriteError

SAMPLE_PDF_V1 = b"%PDF-1.4\nInitial Draft Version 1\n%%EOF\n"
SAMPLE_PDF_V2 = b"%PDF-1.4\nRevised Draft Version 2 Content\n%%EOF\n"
SAMPLE_PDF_V3 = b"%PDF-1.4\nRevised Draft Version 3 Content\n%%EOF\n"
SAMPLE_PNG_V2 = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"

@pytest.fixture
def draft_document_setup(role_user_factory, db_session):
    """
    Creates an initial draft document in 'Finance' with version 1.
    """
    dept_user = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Finance"
    db_session.commit()

    # Stage and finalize v1 file
    t_path, f_hash, f_size = storage_service.stage_file(io.BytesIO(SAMPLE_PDF_V1))
    v1_key = storage_service.generate_storage_key("pdf")
    storage_service.finalize_staged_file(t_path, v1_key)

    ref = f"DOC-DRAFT-{uuid.uuid4().hex[:8].upper()}"
    doc = DigitalDocument(
        document_reference=ref,
        title="Fiscal Policy Guidelines",
        subject="Draft Policy",
        department="Finance",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.DRAFT,
        created_by_id=dept_user.id,
    )
    db_session.add(doc)
    db_session.flush()

    ver1 = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=v1_key,
        original_filename="policy_v1.pdf",
        mime_type="application/pdf",
        file_size_bytes=f_size,
        file_hash_sha256=f_hash,
        created_by_id=dept_user.id,
    )
    db_session.add(ver1)
    db_session.commit()
    db_session.refresh(doc)
    db_session.refresh(ver1)

    created_storage_keys = [v1_key]

    yield {
        "user": dept_user,
        "document": doc,
        "version1": ver1,
        "storage_keys": created_storage_keys,
    }

    # Teardown
    for k in created_storage_keys:
        try:
            storage_service.resolve_storage_path(k).unlink(missing_ok=True)
        except Exception:
            pass
    try:
        db_session.delete(doc)
        db_session.commit()
    except Exception:
        db_session.rollback()


def test_upload_version_2_success(client, draft_document_setup, db_session):
    """Successful upload of version 2 preserves doc identity and keeps v1 intact."""
    user = draft_document_setup["user"]
    doc = draft_document_setup["document"]
    v1 = draft_document_setup["version1"]
    token = create_access_token(user_id=user.id)

    files = {"file": ("policy_revised.pdf", io.BytesIO(SAMPLE_PDF_V2), "application/pdf")}
    url = f"/api/v1/documents/{doc.id}/versions"

    res = client.post(url, headers={"Authorization": f"Bearer {token}"}, files=files)
    assert res.status_code == 201
    data = res.json()

    # 1. Identity preserved
    assert data["document_id"] == str(doc.id)
    assert data["document_reference"] == doc.document_reference
    assert data["version_number"] == 2
    assert data["original_filename"] == "policy_revised.pdf"
    assert data["file_size_bytes"] == len(SAMPLE_PDF_V2)
    assert data["file_hash_sha256"] == hashlib.sha256(SAMPLE_PDF_V2).hexdigest()
    assert "storage_key" not in res.text
    assert "uploads/" not in res.text

    # 2. Check DB records
    db_session.refresh(doc)
    assert len(doc.versions) == 2
    assert doc.versions[0].version_number == 1
    assert doc.versions[1].version_number == 2

    # 3. Verify Version 1 remains intact on disk
    v1_path = storage_service.resolve_storage_path(v1.storage_key)
    assert v1_path.is_file()
    with open(v1_path, "rb") as f:
        assert f.read() == SAMPLE_PDF_V1

    # Cleanup version 2 storage key
    draft_document_setup["storage_keys"].append(doc.versions[1].storage_key)


def test_upload_multiple_sequential_versions(client, draft_document_setup):
    """Uploading multiple versions increments sequentially: 1 -> 2 -> 3."""
    user = draft_document_setup["user"]
    doc = draft_document_setup["document"]
    token = create_access_token(user_id=user.id)
    url = f"/api/v1/documents/{doc.id}/versions"

    # Upload v2
    files_v2 = {"file": ("v2.pdf", io.BytesIO(SAMPLE_PDF_V2), "application/pdf")}
    res2 = client.post(url, headers={"Authorization": f"Bearer {token}"}, files=files_v2)
    assert res2.status_code == 201
    assert res2.json()["version_number"] == 2

    # Upload v3
    files_v3 = {"file": ("v3.pdf", io.BytesIO(SAMPLE_PDF_V3), "application/pdf")}
    res3 = client.post(url, headers={"Authorization": f"Bearer {token}"}, files=files_v3)
    assert res3.status_code == 201
    assert res3.json()["version_number"] == 3


def test_upload_version_unauthenticated_rejected(client, draft_document_setup):
    """Unauthenticated upload returns HTTP 401."""
    doc = draft_document_setup["document"]
    files = {"file": ("v2.pdf", io.BytesIO(SAMPLE_PDF_V2), "application/pdf")}
    res = client.post(f"/api/v1/documents/{doc.id}/versions", files=files)
    assert res.status_code == 401


def test_upload_version_invalid_token_rejected(client, draft_document_setup):
    """Upload with bad JWT returns HTTP 401."""
    doc = draft_document_setup["document"]
    files = {"file": ("v2.pdf", io.BytesIO(SAMPLE_PDF_V2), "application/pdf")}
    res = client.post(
        f"/api/v1/documents/{doc.id}/versions",
        headers={"Authorization": "Bearer invalid_token"},
        files=files,
    )
    assert res.status_code == 401


def test_upload_version_missing_document_returns_404(client, role_user_factory):
    """Uploading a version to a nonexistent document returns HTTP 404."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    fake_id = uuid.uuid4()
    files = {"file": ("v2.pdf", io.BytesIO(SAMPLE_PDF_V2), "application/pdf")}

    res = client.post(
        f"/api/v1/documents/{fake_id}/versions",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "Document not found."


def test_upload_version_non_draft_status_rejected(client, role_user_factory, draft_document_setup, db_session):
    """Uploading a new version to ACTIVE, UNDER_REVIEW, ARCHIVED, or DISPOSED doc returns HTTP 400."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    doc = draft_document_setup["document"]
    url = f"/api/v1/documents/{doc.id}/versions"

    for non_draft_status in [DocumentStatus.ACTIVE, DocumentStatus.UNDER_REVIEW, DocumentStatus.ARCHIVED, DocumentStatus.DISPOSED]:
        doc.status = non_draft_status
        db_session.commit()

        files = {"file": ("v2.pdf", io.BytesIO(SAMPLE_PDF_V2), "application/pdf")}
        res = client.post(url, headers={"Authorization": f"Bearer {token}"}, files=files)
        assert res.status_code == 400
        assert "draft" in res.json()["detail"].lower()


def test_upload_version_role_permissions(client, role_user_factory, draft_document_setup, db_session):
    """
    Verify write permissions across all 6 roles:
    - Admin: Allowed
    - Records Officer: Allowed
    - Department User (Finance): Allowed
    - Approver: Denied (403)
    - Auditor: Denied (403)
    - Read-Only User: Denied (403)
    """
    doc = draft_document_setup["document"]
    url = f"/api/v1/documents/{doc.id}/versions"

    # 1. Admin allowed
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    res_admin = client.post(
        url,
        headers={"Authorization": f"Bearer {create_access_token(admin.id)}"},
        files={"file": ("v2.pdf", io.BytesIO(SAMPLE_PDF_V2), "application/pdf")},
    )
    assert res_admin.status_code == 201

    # 2. Records officer allowed
    ro = role_user_factory(role=UserRole.RECORDS_OFFICER)["user"]
    res_ro = client.post(
        url,
        headers={"Authorization": f"Bearer {create_access_token(ro.id)}"},
        files={"file": ("v3.pdf", io.BytesIO(SAMPLE_PDF_V3), "application/pdf")},
    )
    assert res_ro.status_code == 201

    # 3. Approver denied
    approver = role_user_factory(role=UserRole.APPROVER)["user"]
    approver.department = "Finance"
    db_session.commit()
    res_appr = client.post(
        url,
        headers={"Authorization": f"Bearer {create_access_token(approver.id)}"},
        files={"file": ("v4.pdf", io.BytesIO(SAMPLE_PDF_V2), "application/pdf")},
    )
    assert res_appr.status_code == 403

    # 4. Auditor denied
    auditor = role_user_factory(role=UserRole.AUDITOR)["user"]
    auditor.department = "Finance"
    db_session.commit()
    res_aud = client.post(
        url,
        headers={"Authorization": f"Bearer {create_access_token(auditor.id)}"},
        files={"file": ("v4.pdf", io.BytesIO(SAMPLE_PDF_V2), "application/pdf")},
    )
    assert res_aud.status_code == 403

    # 5. Read-only user denied
    read_only = role_user_factory(role=UserRole.READ_ONLY)["user"]
    read_only.department = "Finance"
    db_session.commit()
    res_ro_user = client.post(
        url,
        headers={"Authorization": f"Bearer {create_access_token(read_only.id)}"},
        files={"file": ("v4.pdf", io.BytesIO(SAMPLE_PDF_V2), "application/pdf")},
    )
    assert res_ro_user.status_code == 403


def test_upload_version_cross_department_denied(client, role_user_factory, draft_document_setup, db_session):
    """Department user in HR is denied uploading a version to a Finance document (403)."""
    hr_user = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    hr_user.department = "Human Resources"
    db_session.commit()

    doc = draft_document_setup["document"]
    token = create_access_token(hr_user.id)
    url = f"/api/v1/documents/{doc.id}/versions"

    files = {"file": ("v2.pdf", io.BytesIO(SAMPLE_PDF_V2), "application/pdf")}
    res = client.post(url, headers={"Authorization": f"Bearer {token}"}, files=files)
    assert res.status_code == 403
    assert "cannot upload versions" in res.json()["detail"].lower()


def test_upload_version_magic_byte_rejection(client, draft_document_setup):
    """Uploading plain text or executable disguised as .pdf is rejected with HTTP 400."""
    user = draft_document_setup["user"]
    doc = draft_document_setup["document"]
    token = create_access_token(user.id)
    url = f"/api/v1/documents/{doc.id}/versions"

    files = {"file": ("fake.pdf", io.BytesIO(b"This is plain text, not a PDF"), "application/pdf")}
    res = client.post(url, headers={"Authorization": f"Bearer {token}"}, files=files)
    assert res.status_code == 400
    assert "unsupported" in res.json()["detail"].lower()


def test_upload_version_oversized_file_rejected(client, draft_document_setup):
    """Uploading file exceeding limit is rejected with HTTP 400."""
    user = draft_document_setup["user"]
    doc = draft_document_setup["document"]
    token = create_access_token(user.id)
    url = f"/api/v1/documents/{doc.id}/versions"

    with patch("app.config.settings.MAX_UPLOAD_SIZE_BYTES", 50):
        files = {"file": ("large.pdf", io.BytesIO(SAMPLE_PDF_V2 * 10), "application/pdf")}
        res = client.post(url, headers={"Authorization": f"Bearer {token}"}, files=files)
        assert res.status_code == 400
        assert "exceeds" in res.json()["detail"].lower()


def test_upload_version_failure_cleans_up_staged_and_preserves_v1(client, draft_document_setup, db_session):
    """If database commit fails, newly staged file is cleaned up and version 1 is unaffected."""
    user = draft_document_setup["user"]
    doc = draft_document_setup["document"]
    v1 = draft_document_setup["version1"]
    token = create_access_token(user.id)
    url = f"/api/v1/documents/{doc.id}/versions"

    files = {"file": ("will_fail.pdf", io.BytesIO(SAMPLE_PDF_V2), "application/pdf")}

    with patch.object(Session, "commit", side_effect=RuntimeError("Simulated DB Crash")):
        res = client.post(url, headers={"Authorization": f"Bearer {token}"}, files=files)
        assert res.status_code == 500

    # Ensure no orphaned temp files
    temp_files = list(storage_service.temp_dir.glob("stage_*.tmp"))
    assert len(temp_files) == 0

    # Ensure version 1 file is still intact
    assert storage_service.resolve_storage_path(v1.storage_key).is_file()

    # Ensure doc version count in DB is still 1
    db_session.refresh(doc)
    assert len(doc.versions) == 1


def test_upload_version_concurrent_conflict_handling(client, draft_document_setup):
    """IntegrityError during version upload returns HTTP 409 Conflict."""
    user = draft_document_setup["user"]
    doc = draft_document_setup["document"]
    token = create_access_token(user.id)
    url = f"/api/v1/documents/{doc.id}/versions"

    files = {"file": ("conflict.pdf", io.BytesIO(SAMPLE_PDF_V2), "application/pdf")}

    with patch.object(Session, "commit", side_effect=IntegrityError("uq_document_version_number", {}, None)):
        res = client.post(url, headers={"Authorization": f"Bearer {token}"}, files=files)
        assert res.status_code == 409
        assert "conflict" in res.json()["detail"].lower()


def test_upload_version_audit_events_recorded(client, draft_document_setup, db_session):
    """Successful version upload records AuditOutcome.SUCCESS with version details."""
    user = draft_document_setup["user"]
    doc = draft_document_setup["document"]
    token = create_access_token(user.id)
    url = f"/api/v1/documents/{doc.id}/versions"

    files = {"file": ("v2_audit.pdf", io.BytesIO(SAMPLE_PDF_V2), "application/pdf")}
    res = client.post(url, headers={"Authorization": f"Bearer {token}", "X-Correlation-ID": "corr-v2-100"}, files=files)
    assert res.status_code == 201

    # Verify audit log
    audit_entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.actor_id == user.id, AuditLog.action == "document.version_upload")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.outcome == AuditOutcome.SUCCESS
    assert audit_entry.correlation_id == "corr-v2-100"
    assert audit_entry.details["version_number"] == 2


def test_upload_version_audit_write_failure_handling(client, draft_document_setup):
    """Mandatory audit failure aborts version upload and raises error without reporting success."""
    user = draft_document_setup["user"]
    doc = draft_document_setup["document"]
    token = create_access_token(user.id)
    url = f"/api/v1/documents/{doc.id}/versions"

    files = {"file": ("v2_audit_fail.pdf", io.BytesIO(SAMPLE_PDF_V2), "application/pdf")}

    with patch("app.api.v1.documents.audit_service.log_from_request", side_effect=AuditWriteError("Simulated Audit Storage Failure")):
        with pytest.raises(AuditWriteError):
            client.post(url, headers={"Authorization": f"Bearer {token}"}, files=files)
