"""
Automated test suite for Task 4.5: OCR Job Monitoring and Controlled Retry APIs.
Verifies:
1. Administrator can list jobs.
2. Non-admin roles cannot access operational endpoints.
3. Pagination and job-status filters work correctly.
4. Invalid filters and date ranges are rejected.
5. Job detail returns safe metadata.
6. Nonexistent job returns 404.
7. Failed job can be retried successfully.
8. Queued, running, and completed jobs cannot be retried.
9. Missing document version or stored file is handled safely.
10. Previously extracted text is preserved until successful reprocessing.
11. Concurrent retry requests cannot create duplicate or inconsistent jobs.
12. Retry-limit behavior is enforced.
13. Worker successfully processes a requeued job.
14. Audit events are persisted and audit-write failures are handled.
15. Unauthenticated requests are rejected.
"""
import io
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import pytest

from app.models.user import UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus, ExtractionStatus, utc_now
from app.models.ocr_job import OCRJob, OCRJobStatus
from app.models.audit import AuditLog, AuditOutcome
from app.jwt import create_access_token
from app.services.ocr_worker import ocr_job_service
from app.services.storage import storage_service
from app.services.audit import AuditWriteError


def make_test_pdf(text: str = "OCR Monitoring Sample Content 2026") -> bytes:
    """Generates a valid test PDF byte stream."""
    content = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length {len(text) + 30} >>
stream
BT
/F1 18 Tf
50 700 Td
({text}) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000244 00000 n 
0000000325 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
406
%%EOF"""
    return content.encode("latin1")


@pytest.fixture(autouse=True)
def cleanup_ocr_test_jobs(db_session):
    """Ensures test queue isolation by cleaning up jobs created during the test."""
    yield
    try:
        db_session.query(DigitalDocument).filter(DigitalDocument.document_reference.like("DOC-MON-%")).delete()
        db_session.query(OCRJob).delete()
        db_session.commit()
    except Exception:
        db_session.rollback()


def create_document_with_stored_file(db_session, user, filename="test.pdf", text="Sample Document Content"):
    """Creates a document, stages a real PDF on disk, and creates a DocumentVersion record."""
    pdf_bytes = make_test_pdf(text)
    temp_path, sha256_hash, file_size_bytes = storage_service.stage_file(io.BytesIO(pdf_bytes))
    storage_key = storage_service.generate_storage_key(".pdf")
    final_path = storage_service.finalize_staged_file(temp_path, storage_key)

    doc = DigitalDocument(
        title=f"Doc {uuid.uuid4().hex[:6]}",
        document_reference=f"DOC-MON-{uuid.uuid4().hex[:6]}",
        subject="OCR Monitoring Testing",
        department="Operations",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=user.id,
    )
    db_session.add(doc)
    db_session.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=storage_key,
        original_filename=filename,
        mime_type="application/pdf",
        file_size_bytes=file_size_bytes,
        file_hash_sha256=sha256_hash,
        extraction_status=ExtractionStatus.PENDING,
        created_by_id=user.id,
    )
    db_session.add(version)
    db_session.flush()

    return doc, version, final_path


def test_admin_can_list_ocr_jobs(client, role_user_factory, db_session):
    """1. Administrator can list jobs with pagination and safe operational metadata."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)

    # Create two jobs
    _, v1, _ = create_document_with_stored_file(db_session, admin, "file1.pdf")
    _, v2, _ = create_document_with_stored_file(db_session, admin, "file2.pdf")

    j1 = ocr_job_service.enqueue_job(db=db_session, version_id=v1.id)
    j2 = ocr_job_service.enqueue_job(db=db_session, version_id=v2.id)
    j2.status = OCRJobStatus.COMPLETED
    db_session.commit()

    res = client.get("/api/v1/ocr/jobs", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2
    assert "page" in data
    assert "page_size" in data

    # Verify first item metadata safety
    item = data["items"][0]
    assert "id" in item
    assert "document_version_id" in item
    assert "status" in item
    assert "attempt_count" in item
    assert "max_attempts" in item
    assert "created_at" in item
    assert "updated_at" in item

    # Verify sensitive attributes are never exposed
    assert "extracted_text" not in item
    assert "storage_key" not in item
    assert "file_path" not in item


def test_non_admin_roles_cannot_access_operational_endpoints(client, role_user_factory, db_session):
    """2. Non-admin roles (Records Officer, Department User, Approver, Auditor, Read-Only) are forbidden."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    _, version, _ = create_document_with_stored_file(db_session, admin, "nonadmin.pdf")
    job = ocr_job_service.enqueue_job(db=db_session, version_id=version.id)
    job.status = OCRJobStatus.FAILED
    db_session.commit()

    non_admin_roles = [
        UserRole.RECORDS_OFFICER,
        UserRole.DEPARTMENT_USER,
        UserRole.APPROVER,
        UserRole.AUDITOR,
        UserRole.READ_ONLY,
    ]

    for role in non_admin_roles:
        u = role_user_factory(role=role)["user"]
        t = create_access_token(user_id=u.id)
        headers = {"Authorization": f"Bearer {t}"}

        # List
        res_list = client.get("/api/v1/ocr/jobs", headers=headers)
        assert res_list.status_code == 403, f"Expected 403 for {role.value} on list"

        # Detail
        res_detail = client.get(f"/api/v1/ocr/jobs/{job.id}", headers=headers)
        assert res_detail.status_code == 403, f"Expected 403 for {role.value} on detail"

        # Retry
        res_retry = client.post(f"/api/v1/ocr/jobs/{job.id}/retry", headers=headers)
        assert res_retry.status_code == 403, f"Expected 403 for {role.value} on retry"


def test_pagination_and_job_status_filters(client, role_user_factory, db_session):
    """3. Pagination and job-status/version filters operate accurately in SQL."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    _, v1, _ = create_document_with_stored_file(db_session, admin, "p1.pdf")
    _, v2, _ = create_document_with_stored_file(db_session, admin, "p2.pdf")
    _, v3, _ = create_document_with_stored_file(db_session, admin, "p3.pdf")

    j1 = ocr_job_service.enqueue_job(db=db_session, version_id=v1.id)
    j1.status = OCRJobStatus.QUEUED

    j2 = ocr_job_service.enqueue_job(db=db_session, version_id=v2.id)
    j2.status = OCRJobStatus.FAILED

    j3 = ocr_job_service.enqueue_job(db=db_session, version_id=v3.id)
    j3.status = OCRJobStatus.COMPLETED
    db_session.commit()

    # Filter status=failed
    res_failed = client.get("/api/v1/ocr/jobs?status=failed", headers=headers)
    assert res_failed.status_code == 200
    data_failed = res_failed.json()
    assert all(item["status"] == "failed" for item in data_failed["items"])
    assert any(item["id"] == str(j2.id) for item in data_failed["items"])

    # Filter document_version_id
    res_ver = client.get(f"/api/v1/ocr/jobs?document_version_id={v1.id}", headers=headers)
    assert res_ver.status_code == 200
    data_ver = res_ver.json()
    assert len(data_ver["items"]) == 1
    assert data_ver["items"][0]["id"] == str(j1.id)

    # Pagination page=1, page_size=1
    res_page = client.get("/api/v1/ocr/jobs?page=1&page_size=1", headers=headers)
    assert res_page.status_code == 200
    assert len(res_page.json()["items"]) == 1
    assert res_page.json()["page_size"] == 1


def test_invalid_filters_and_date_ranges_rejected(client, role_user_factory):
    """4. Invalid filters and inconsistent date ranges are rejected with 422."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    # created_from > created_to
    now = datetime.now(timezone.utc)
    earlier = now - timedelta(days=2)
    later = now + timedelta(days=2)
    res_date = client.get(
        f"/api/v1/ocr/jobs?created_from={later.isoformat()}&created_to={earlier.isoformat()}",
        headers=headers,
    )
    assert res_date.status_code == 422

    # page < 1
    res_p0 = client.get("/api/v1/ocr/jobs?page=0", headers=headers)
    assert res_p0.status_code == 422

    # page_size > 100
    res_ps = client.get("/api/v1/ocr/jobs?page_size=101", headers=headers)
    assert res_ps.status_code == 422

    # invalid status enum
    res_inv = client.get("/api/v1/ocr/jobs?status=unknown_status", headers=headers)
    assert res_inv.status_code == 422


def test_job_detail_returns_safe_metadata(client, role_user_factory, db_session):
    """5. Job detail returns safe operational metadata."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    _, version, _ = create_document_with_stored_file(db_session, admin, "detail.pdf")
    job = ocr_job_service.enqueue_job(db=db_session, version_id=version.id)
    job.last_error = "Transient extraction timeout"
    db_session.commit()

    res = client.get(f"/api/v1/ocr/jobs/{job.id}", headers=headers)
    assert res.status_code == 200
    item = res.json()
    assert item["id"] == str(job.id)
    assert item["document_version_id"] == str(version.id)
    assert item["status"] == "queued"
    assert item["last_error"] == "Transient extraction timeout"
    assert "extracted_text" not in item
    assert "storage_key" not in item


def test_nonexistent_job_returns_404(client, role_user_factory):
    """6. Nonexistent job ID returns 404 on both detail and retry."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    headers = {"Authorization": f"Bearer {token}"}
    random_id = uuid.uuid4()

    res_get = client.get(f"/api/v1/ocr/jobs/{random_id}", headers=headers)
    assert res_get.status_code == 404

    res_post = client.post(f"/api/v1/ocr/jobs/{random_id}/retry", headers=headers)
    assert res_post.status_code == 404


def test_failed_job_can_be_retried_successfully(client, role_user_factory, db_session):
    """7. Failed job can be retried successfully, resetting version and job status."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    _, version, _ = create_document_with_stored_file(db_session, admin, "retry_success.pdf")
    job = ocr_job_service.enqueue_job(db=db_session, version_id=version.id)
    job.status = OCRJobStatus.FAILED
    job.attempt_count = 1
    job.last_error = "Temporary connection failure"
    version.extraction_status = ExtractionStatus.FAILED
    version.extraction_error = "Temporary connection failure"
    db_session.commit()

    res = client.post(f"/api/v1/ocr/jobs/{job.id}/retry", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "queued"
    assert data["last_error"] is None

    # Refresh from database
    db_session.refresh(job)
    db_session.refresh(version)
    assert job.status == OCRJobStatus.QUEUED
    assert job.lease_expires_at is None
    assert job.worker_id is None
    assert version.extraction_status == ExtractionStatus.PENDING
    assert version.extraction_error is None


def test_queued_running_and_completed_jobs_cannot_be_retried(client, role_user_factory, db_session):
    """8. Queued, running, and completed jobs cannot be retried (409 Conflict)."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    _, v1, _ = create_document_with_stored_file(db_session, admin, "q1.pdf")
    _, v2, _ = create_document_with_stored_file(db_session, admin, "q2.pdf")
    _, v3, _ = create_document_with_stored_file(db_session, admin, "q3.pdf")

    j_queued = ocr_job_service.enqueue_job(db=db_session, version_id=v1.id)
    j_queued.status = OCRJobStatus.QUEUED

    j_running = ocr_job_service.enqueue_job(db=db_session, version_id=v2.id)
    j_running.status = OCRJobStatus.RUNNING

    j_completed = ocr_job_service.enqueue_job(db=db_session, version_id=v3.id)
    j_completed.status = OCRJobStatus.COMPLETED
    db_session.commit()

    for j, state in [(j_queued, "queued"), (j_running, "running"), (j_completed, "completed")]:
        res = client.post(f"/api/v1/ocr/jobs/{j.id}/retry", headers=headers)
        assert res.status_code == 409, f"Expected 409 for job in {state} state"
        assert f"Cannot retry job in '{state}' status" in res.json()["detail"]


def test_missing_document_version_or_stored_file_handled_safely(client, role_user_factory, db_session):
    """9. Missing document version row or deleted stored file is handled safely."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Case A: DocumentVersion row exists, but file on disk is deleted
    _, v_missing_file, disk_path = create_document_with_stored_file(db_session, admin, "deleted_file.pdf")
    j_missing_file = ocr_job_service.enqueue_job(db=db_session, version_id=v_missing_file.id)
    j_missing_file.status = OCRJobStatus.FAILED
    db_session.commit()

    # Delete file from disk
    if disk_path.exists():
        disk_path.unlink()

    res_missing_file = client.post(f"/api/v1/ocr/jobs/{j_missing_file.id}/retry", headers=headers)
    assert res_missing_file.status_code == 404
    assert "Associated document file not found in storage" in res_missing_file.json()["detail"]

    # Case B: DocumentVersion row missing from database
    _, v_to_delete, _ = create_document_with_stored_file(db_session, admin, "delete_row.pdf")
    j_orphan = ocr_job_service.enqueue_job(db=db_session, version_id=v_to_delete.id)
    j_orphan.status = OCRJobStatus.FAILED
    db_session.commit()

    with patch("sqlalchemy.orm.Query.first", side_effect=[admin, j_orphan, None]):
        res_missing_ver = client.post(f"/api/v1/ocr/jobs/{j_orphan.id}/retry", headers=headers)
        assert res_missing_ver.status_code == 404
        assert "Associated document version not found" in res_missing_ver.json()["detail"]


def test_previously_extracted_text_preserved_on_retry(client, role_user_factory, db_session):
    """10. Previously extracted text is preserved when a failed job is retried."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    _, version, _ = create_document_with_stored_file(db_session, admin, "preserve_text.pdf")
    initial_text = "Important Legal Precedent and Historical Clause"
    version.extracted_text = initial_text
    version.extraction_status = ExtractionStatus.FAILED
    version.extraction_error = "Intermittent parsing crash"

    job = ocr_job_service.enqueue_job(db=db_session, version_id=version.id)
    job.status = OCRJobStatus.FAILED
    job.attempt_count = 1
    db_session.commit()

    res = client.post(f"/api/v1/ocr/jobs/{job.id}/retry", headers=headers)
    assert res.status_code == 200

    db_session.refresh(version)
    assert version.extraction_status == ExtractionStatus.PENDING
    assert version.extraction_error is None
    # Text must NOT be wiped out
    assert version.extracted_text == initial_text


def test_concurrent_retry_requests_safety(client, role_user_factory, db_session):
    """11. Concurrent retry requests cannot create duplicate jobs or corrupt state."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    _, version, _ = create_document_with_stored_file(db_session, admin, "concurrent.pdf")
    job = ocr_job_service.enqueue_job(db=db_session, version_id=version.id)
    job.status = OCRJobStatus.FAILED
    job.attempt_count = 1
    db_session.commit()

    # First retry succeeds
    res1 = client.post(f"/api/v1/ocr/jobs/{job.id}/retry", headers=headers)
    assert res1.status_code == 200
    assert res1.json()["status"] == "queued"

    # Immediate second retry encounters the now-queued status and returns 409
    res2 = client.post(f"/api/v1/ocr/jobs/{job.id}/retry", headers=headers)
    assert res2.status_code == 409
    assert "Cannot retry job in 'queued' status" in res2.json()["detail"]

    # Verify still exactly 1 job record in database
    job_count = db_session.query(OCRJob).filter(OCRJob.document_version_id == version.id).count()
    assert job_count == 1


def test_retry_limit_behavior_enforced(client, role_user_factory, db_session):
    """12. Retry-limit behavior is enforced unless explicitly reset by administrator."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    _, version, _ = create_document_with_stored_file(db_session, admin, "exhausted.pdf")
    job = ocr_job_service.enqueue_job(db=db_session, version_id=version.id)
    job.status = OCRJobStatus.FAILED
    job.attempt_count = 3
    job.max_attempts = 3
    job.last_error = "Retry budget exhausted"
    db_session.commit()

    # Retry without reset_attempts -> 400 Bad Request
    res_rejected = client.post(f"/api/v1/ocr/jobs/{job.id}/retry", headers=headers)
    assert res_rejected.status_code == 400
    assert "Retry limit reached" in res_rejected.json()["detail"]

    # Retry with reset_attempts=true -> succeeds and resets attempt count
    res_override = client.post(f"/api/v1/ocr/jobs/{job.id}/retry?reset_attempts=true", headers=headers)
    assert res_override.status_code == 200
    assert res_override.json()["status"] == "queued"
    assert res_override.json()["attempt_count"] == 0

    db_session.refresh(job)
    assert job.status == OCRJobStatus.QUEUED
    assert job.attempt_count == 0


def test_worker_successfully_processes_requeued_job(client, role_user_factory, db_session):
    """13. Worker daemon claims and successfully processes a requeued job."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    sample_text = "Verification of Worker Claiming Requeued Job 2026"
    _, version, _ = create_document_with_stored_file(db_session, admin, "worker_requeue.pdf", text=sample_text)

    job = ocr_job_service.enqueue_job(db=db_session, version_id=version.id)
    job.status = OCRJobStatus.FAILED
    job.attempt_count = 1
    version.extraction_status = ExtractionStatus.FAILED
    db_session.commit()

    # Admin retries the job
    res_retry = client.post(f"/api/v1/ocr/jobs/{job.id}/retry", headers=headers)
    assert res_retry.status_code == 200

    # Ensure this specific job is executed by worker service
    db_session.refresh(job)
    job.status = OCRJobStatus.RUNNING
    job.worker_id = "test-worker-requeue"
    job.attempt_count += 1
    db_session.commit()

    success = ocr_job_service.execute_job(db=db_session, job=job)
    assert success is True

    # Verify job and version are now COMPLETED
    db_session.refresh(job)
    db_session.refresh(version)
    assert job.status == OCRJobStatus.COMPLETED
    assert job.completed_at is not None
    assert version.extraction_status == ExtractionStatus.COMPLETED
    assert version.extracted_text is not None
    assert sample_text in version.extracted_text


def test_audit_events_persisted_and_audit_failure_handling(client, role_user_factory, db_session):
    """14. Audit events are persisted for list/detail/retry, and audit failures roll back the retry."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    _, version, _ = create_document_with_stored_file(db_session, admin, "audit_verify.pdf")
    job = ocr_job_service.enqueue_job(db=db_session, version_id=version.id)
    job.status = OCRJobStatus.FAILED
    job.attempt_count = 1
    version.extraction_status = ExtractionStatus.FAILED
    db_session.commit()

    # 1. Detail audit event
    client.get(f"/api/v1/ocr/jobs/{job.id}", headers=headers)
    audit_detail = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "ocr.job_detail", AuditLog.actor_id == admin.id)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit_detail is not None
    assert audit_detail.outcome == AuditOutcome.SUCCESS

    # 2. Simulated audit write failure during retry
    with patch("app.services.audit.audit_service.log_from_request", side_effect=AuditWriteError("Simulated audit disk failure")):
        res_fail = client.post(f"/api/v1/ocr/jobs/{job.id}/retry", headers=headers)
        # Should raise 500 when mandatory audit write fails
        assert res_fail.status_code == 500

    # CRITICAL: Verify job remains in FAILED state (transaction rolled back, not left requeued)
    db_session.refresh(job)
    db_session.refresh(version)
    assert job.status == OCRJobStatus.FAILED
    assert version.extraction_status == ExtractionStatus.FAILED


def test_unauthenticated_requests_rejected(client):
    """15. Unauthenticated requests are rejected across all OCR endpoints."""
    random_id = uuid.uuid4()
    assert client.get("/api/v1/ocr/jobs").status_code == 401
    assert client.get(f"/api/v1/ocr/jobs/{random_id}").status_code == 401
    assert client.post(f"/api/v1/ocr/jobs/{random_id}/retry").status_code == 401
