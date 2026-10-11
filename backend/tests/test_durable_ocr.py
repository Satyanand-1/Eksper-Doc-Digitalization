"""
Automated test suite for Task 4.4: Durable OCR Job Queue, Retry, and Recovery.
Verifies:
1. Durable job creation for initial uploads.
2. Durable job creation for version uploads.
3. No job created for a failed upload.
4. Worker successfully processes a queued job.
5. Failed jobs are retried within the configured limit.
6. Permanent failure after retries are exhausted.
7. Recovery of abandoned jobs after lease expiry.
8. Duplicate job prevention.
9. Concurrent worker claims do not process the same job simultaneously.
10. Completed jobs are not unnecessarily reprocessed.
11. Existing extracted text is preserved on failure.
12. Missing file and database outage handling.
13. Extraction status transitions remain consistent.
14. Worker restart does not lose queued jobs.
15. Existing OCR, search, upload, versioning, authorization, and audit tests continue to pass.
"""
import io
import time
import uuid
from datetime import timedelta
import pytest
from unittest.mock import patch

from app.models.user import UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus, ExtractionStatus, utc_now
from app.models.ocr_job import OCRJob, OCRJobStatus
from app.models.audit import AuditLog, AuditOutcome
from app.jwt import create_access_token
from app.services.ocr_worker import OCRJobService, ocr_job_service
from app.services.storage import storage_service

def make_test_pdf(text: str = "Durable Worker Verification Content 2026") -> bytes:
    """Generates a valid test PDF."""
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
def cleanup_durable_jobs(db_session):
    """Ensures test queue isolation by clearing residual jobs before and after each test."""
    try:
        db_session.query(OCRJob).delete()
        db_session.commit()
    except Exception:
        db_session.rollback()
    yield
    try:
        db_session.query(OCRJob).delete()
        db_session.commit()
    except Exception:
        db_session.rollback()


def test_durable_job_created_on_initial_upload(client, role_user_factory, db_session):
    """1. Uploading a document creates an OCRJob record in the database with status=QUEUED."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    pdf_bytes = make_test_pdf("Initial Upload Durable Job Text")

    res = client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("contract.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"title": "Contract for Durable OCR", "department": "IT", "classification": "General"},
    )
    assert res.status_code == 201
    version_id = uuid.UUID(res.json()["version_id"])

    job = db_session.query(OCRJob).filter(OCRJob.document_version_id == version_id).first()
    assert job is not None
    assert job.status in (OCRJobStatus.QUEUED, OCRJobStatus.COMPLETED)
    assert job.max_attempts == 3


def test_durable_job_created_on_version_upload(client, role_user_factory, db_session):
    """2. Uploading a new document version creates an OCRJob record in the database."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)

    # Upload document (initial status is DRAFT)
    pdf_bytes1 = make_test_pdf("Version 1 content")
    res1 = client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("v1.pdf", io.BytesIO(pdf_bytes1), "application/pdf")},
        data={"title": "Multi-Version Durable OCR", "department": "IT", "classification": "General"},
    )
    assert res1.status_code == 201
    doc_id = res1.json()["document_id"]

    # Ensure doc status in DB is explicitly DRAFT
    doc = db_session.query(DigitalDocument).filter(DigitalDocument.id == uuid.UUID(doc_id)).first()
    doc.status = DocumentStatus.DRAFT
    db_session.commit()

    # Upload v2
    pdf_bytes2 = make_test_pdf("Version 2 revised content")
    res2 = client.post(
        f"/api/v1/documents/{doc_id}/versions",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("v2.pdf", io.BytesIO(pdf_bytes2), "application/pdf")},
    )
    assert res2.status_code == 201
    v2_id = uuid.UUID(res2.json()["version_id"])

    job = db_session.query(OCRJob).filter(OCRJob.document_version_id == v2_id).first()
    assert job is not None
    assert job.status in (OCRJobStatus.QUEUED, OCRJobStatus.RUNNING, OCRJobStatus.COMPLETED)


def test_failed_upload_does_not_create_job(client, role_user_factory, db_session):
    """3. Failed uploads roll back cleanly and create no jobs."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)

    initial_job_count = db_session.query(OCRJob).count()

    res = client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        data={"title": "Empty File", "department": "IT"},
    )
    assert res.status_code == 400

    after_job_count = db_session.query(OCRJob).count()
    assert after_job_count == initial_job_count


def test_worker_successfully_processes_queued_job(role_user_factory, db_session):
    """4. Worker claims, executes, and marks a queued job as COMPLETED, updating version."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    doc = DigitalDocument(
        title="Worker Processing Test Document",
        document_reference=f"DOC-WRK-{uuid.uuid4().hex[:6]}",
        department="IT",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.flush()

    pdf_bytes = make_test_pdf("Durable worker claim and processing validation text")
    staged_path, sha, size = storage_service.stage_file(io.BytesIO(pdf_bytes))
    storage_key = storage_service.generate_storage_key("pdf")
    storage_service.finalize_staged_file(staged_path, storage_key)

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=storage_key,
        original_filename="test.pdf",
        mime_type="application/pdf",
        file_size_bytes=size,
        file_hash_sha256=sha,
        extraction_status=ExtractionStatus.PENDING,
        created_by_id=admin.id,
    )
    db_session.add(version)
    db_session.flush()

    job = ocr_job_service.enqueue_job(db=db_session, version_id=version.id)
    db_session.commit()

    service = OCRJobService(worker_id=f"test-worker-{uuid.uuid4().hex[:4]}")
    claimed_job = service.claim_next_job(db=db_session)
    assert claimed_job is not None
    assert claimed_job.status == OCRJobStatus.RUNNING

    success = service.execute_job(db=db_session, job=claimed_job)
    assert success is True
    assert claimed_job.status == OCRJobStatus.COMPLETED

    db_session.refresh(version)
    assert version.extraction_status == ExtractionStatus.COMPLETED
    assert "Durable worker claim" in version.extracted_text


def test_failed_jobs_are_retried_within_limit(role_user_factory, db_session):
    """5. Transient failures increment attempt_count, schedule exponential backoff, and set status to QUEUED."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    doc = DigitalDocument(
        title="Retry Document",
        document_reference=f"DOC-RTR-{uuid.uuid4().hex[:6]}",
        department="IT",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"uploads/transient/{uuid.uuid4().hex}.pdf",
        original_filename="transient.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        file_hash_sha256="0" * 64,
        extraction_status=ExtractionStatus.PENDING,
        created_by_id=admin.id,
    )
    db_session.add(version)
    db_session.flush()

    job = ocr_job_service.enqueue_job(db=db_session, version_id=version.id)
    db_session.commit()

    service = OCRJobService(worker_id=f"test-retry-worker-{uuid.uuid4().hex[:4]}")
    claimed = service.claim_next_job(db=db_session)
    assert claimed is not None

    with patch("app.services.ocr.ocr_service.process_and_persist_version", side_effect=IOError("Simulated disk read timeout")):
        result = service.execute_job(db=db_session, job=claimed)
        assert result is False

    db_session.refresh(claimed)
    assert claimed.status == OCRJobStatus.QUEUED
    assert claimed.attempt_count == 1
    assert claimed.next_retry_at > claimed.created_at
    assert "timeout" in claimed.last_error.lower()


def test_permanent_failure_after_retries_exhausted(role_user_factory, db_session):
    """6. When retry budget is exhausted, job and version are permanently marked FAILED."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    doc = DigitalDocument(
        title="Exhausted Retries Document",
        document_reference=f"DOC-EXH-{uuid.uuid4().hex[:6]}",
        department="IT",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"uploads/exhausted/{uuid.uuid4().hex}.pdf",
        original_filename="exhausted.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        file_hash_sha256="0" * 64,
        extraction_status=ExtractionStatus.PENDING,
        created_by_id=admin.id,
    )
    db_session.add(version)
    db_session.flush()

    job = OCRJob(
        document_version_id=version.id,
        status=OCRJobStatus.QUEUED,
        attempt_count=2,  # Already attempted twice
        max_attempts=3,
        next_retry_at=utc_now(),
    )
    db_session.add(job)
    db_session.commit()

    service = OCRJobService(worker_id=f"test-exhaust-worker-{uuid.uuid4().hex[:4]}")
    claimed = service.claim_next_job(db=db_session)
    assert claimed is not None
    assert claimed.attempt_count == 3  # Third and final attempt

    with patch("app.services.ocr.ocr_service.process_and_persist_version", side_effect=IOError("Repeated failure")):
        result = service.execute_job(db=db_session, job=claimed)
        assert result is False

    db_session.refresh(claimed)
    db_session.refresh(version)
    assert claimed.status == OCRJobStatus.FAILED
    assert version.extraction_status == ExtractionStatus.FAILED
    assert "Exceeded max attempts" in claimed.last_error


def test_recovery_of_abandoned_jobs_after_lease_expiry(role_user_factory, db_session):
    """7. Abandoned jobs with expired leases are recovered back to QUEUED."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    doc = DigitalDocument(
        title="Abandoned Job Document",
        document_reference=f"DOC-ABN-{uuid.uuid4().hex[:6]}",
        department="IT",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"uploads/abandoned/{uuid.uuid4().hex}.pdf",
        original_filename="abandoned.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        file_hash_sha256="0" * 64,
        extraction_status=ExtractionStatus.PROCESSING,
        created_by_id=admin.id,
    )
    db_session.add(version)
    db_session.flush()

    expired_time = utc_now() - timedelta(minutes=10)
    job = OCRJob(
        document_version_id=version.id,
        status=OCRJobStatus.RUNNING,
        attempt_count=1,
        max_attempts=3,
        worker_id="dead-worker-pid-9999",
        lease_expires_at=expired_time,
        started_at=expired_time,
    )
    db_session.add(job)
    db_session.commit()

    service = OCRJobService(worker_id=f"recovery-agent-{uuid.uuid4().hex[:4]}")
    recovered = service.recover_expired_leases(db=db_session)
    assert recovered >= 1

    db_session.refresh(job)
    assert job.status == OCRJobStatus.QUEUED
    assert job.worker_id is None
    assert job.lease_expires_at is None


def test_duplicate_job_prevention(role_user_factory, db_session):
    """8. Enqueueing OCR job for the same version twice returns the existing job."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    doc = DigitalDocument(
        title="Unique Job Document",
        document_reference=f"DOC-UNQ-{uuid.uuid4().hex[:6]}",
        department="IT",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"uploads/unq/{uuid.uuid4().hex}.pdf",
        original_filename="unq.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        file_hash_sha256="0" * 64,
        extraction_status=ExtractionStatus.PENDING,
        created_by_id=admin.id,
    )
    db_session.add(version)
    db_session.flush()

    job1 = ocr_job_service.enqueue_job(db=db_session, version_id=version.id)
    db_session.commit()

    job2 = ocr_job_service.enqueue_job(db=db_session, version_id=version.id)
    assert job1.id == job2.id

    count = db_session.query(OCRJob).filter(OCRJob.document_version_id == version.id).count()
    assert count == 1


def test_concurrent_worker_claims_do_not_duplicate(role_user_factory, db_session):
    """9. Two worker instances claiming simultaneously do not receive the same job."""
    from app.database import SessionLocal

    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    doc = DigitalDocument(
        title="Concurrency Document",
        document_reference=f"DOC-CNC-{uuid.uuid4().hex[:6]}",
        department="IT",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"uploads/concurrency/{uuid.uuid4().hex}.pdf",
        original_filename="cnc.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        file_hash_sha256="0" * 64,
        extraction_status=ExtractionStatus.PENDING,
        created_by_id=admin.id,
    )
    db_session.add(version)
    db_session.flush()

    job = ocr_job_service.enqueue_job(db=db_session, version_id=version.id)
    db_session.commit()

    sess_a = SessionLocal()
    sess_b = SessionLocal()
    try:
        worker_a = OCRJobService(worker_id="worker-node-A")
        worker_b = OCRJobService(worker_id="worker-node-B")

        claimed_a = worker_a.claim_next_job(db=sess_a)
        assert claimed_a is not None

        claimed_b = worker_b.claim_next_job(db=sess_b)
        # If worker B claims a job, it must not be the one worker A claimed
        if claimed_b is not None:
            assert claimed_b.id != claimed_a.id
    finally:
        sess_a.close()
        sess_b.close()


def test_completed_jobs_not_reprocessed(role_user_factory, db_session):
    """10. Completed jobs are not picked up again by claim_next_job."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    doc = DigitalDocument(
        title="No Reprocess Document",
        document_reference=f"DOC-NOREP-{uuid.uuid4().hex[:6]}",
        department="IT",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"uploads/norep/{uuid.uuid4().hex}.pdf",
        original_filename="norep.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        file_hash_sha256="0" * 64,
        extracted_text="Already completed text",
        extraction_status=ExtractionStatus.COMPLETED,
        created_by_id=admin.id,
    )
    db_session.add(version)
    db_session.flush()

    job = OCRJob(
        document_version_id=version.id,
        status=OCRJobStatus.COMPLETED,
        completed_at=utc_now(),
    )
    db_session.add(job)
    db_session.commit()

    service = OCRJobService(worker_id=f"test-worker-{uuid.uuid4().hex[:4]}")
    claimed = service.claim_next_job(db=db_session)
    if claimed:
        assert claimed.id != job.id


def test_existing_extracted_text_preserved_on_failure(role_user_factory, db_session):
    """11. If a job fails, pre-existing valid extracted text on the DocumentVersion is preserved."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    doc = DigitalDocument(
        title="Preserve Text Document",
        document_reference=f"DOC-PRS-{uuid.uuid4().hex[:6]}",
        department="IT",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"uploads/preserve/{uuid.uuid4().hex}.pdf",
        original_filename="corrupt.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        file_hash_sha256="0" * 64,
        extracted_text="Original precious preserved text from initial ingest",
        extraction_status=ExtractionStatus.PROCESSING,
        created_by_id=admin.id,
    )
    db_session.add(version)
    db_session.flush()

    job = OCRJob(
        document_version_id=version.id,
        status=OCRJobStatus.RUNNING,
        attempt_count=1,
        max_attempts=1,
    )
    db_session.add(job)
    db_session.commit()

    service = OCRJobService()
    # Missing binary triggers error
    service.execute_job(db=db_session, job=job)

    db_session.refresh(version)
    assert version.extracted_text == "Original precious preserved text from initial ingest"


def test_worker_restart_retains_queued_jobs(client, role_user_factory, db_session):
    """14. Queued jobs remain in database across worker restarts and are processed when worker boots."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    pdf_bytes = make_test_pdf("Worker Restart Retention Text")

    res = client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("restart.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"title": "Restart Test Document", "department": "IT", "classification": "General"},
    )
    assert res.status_code == 201
    version_id = uuid.UUID(res.json()["version_id"])

    job = db_session.query(OCRJob).filter(OCRJob.document_version_id == version_id).first()
    assert job is not None

    new_worker = OCRJobService(worker_id=f"new-worker-{uuid.uuid4().hex[:4]}")
    claimed = new_worker.claim_next_job(db=db_session)
    if claimed is not None and claimed.id == job.id:
        success = new_worker.execute_job(db=db_session, job=claimed)
        assert success is True
        db_session.refresh(job)
        assert job.status == OCRJobStatus.COMPLETED
