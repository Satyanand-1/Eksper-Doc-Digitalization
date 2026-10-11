"""
Durable OCR Worker and Queue Service.
Handles polling, atomic lease acquisition (FOR UPDATE SKIP LOCKED),
job execution, bounded exponential retries, recovery of expired leases,
and audit trail recording.
"""
import logging
import socket
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, or_, and_, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.document import DocumentVersion, ExtractionStatus, utc_now
from app.models.ocr_job import OCRJob, OCRJobStatus
from app.models.audit import AuditOutcome
from app.services.ocr import (
    ocr_service,
    UnsupportedFormatError,
    CorruptFileError,
    EncryptedFileError,
)
from app.services.audit import audit_service

logger = logging.getLogger("edrms.ocr_worker")


def get_worker_identity() -> str:
    """Returns a unique worker identifier incorporating hostname and random UUID."""
    hostname = socket.gethostname()
    return f"{hostname}-{uuid.uuid4().hex[:6]}"


class OCRJobService:
    """
    Manages creation, claiming, execution, and recovery of durable OCR jobs.
    """

    def __init__(self, worker_id: Optional[str] = None):
        self.worker_id = worker_id or get_worker_identity()
        self.lease_duration_seconds = settings.OCR_WORKER_LEASE_SECONDS
        self.max_attempts = settings.OCR_WORKER_MAX_ATTEMPTS
        self.base_retry_delay = settings.OCR_WORKER_BASE_RETRY_DELAY_SECONDS

    def enqueue_job(self, db: Session, version_id: uuid.UUID) -> OCRJob:
        """
        Creates a durable OCRJob in the current database transaction.
        Idempotent: if a job record already exists for the version, returns the existing record.
        """
        existing = db.query(OCRJob).filter(OCRJob.document_version_id == version_id).first()
        if existing:
            return existing

        now = utc_now()
        job = OCRJob(
            document_version_id=version_id,
            status=OCRJobStatus.QUEUED,
            attempt_count=0,
            max_attempts=self.max_attempts,
            next_retry_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(job)
        return job

    def requeue_failed_job(self, db: Session, job: OCRJob, reset_attempts: bool = False) -> OCRJob:
        """
        Requeues an existing failed job for execution.
        Resets scheduling timestamps and document version extraction status.
        Preserves previously extracted text.
        """
        now = utc_now()
        job.status = OCRJobStatus.QUEUED
        job.next_retry_at = now
        job.lease_expires_at = None
        job.worker_id = None
        job.started_at = None
        job.completed_at = None
        job.last_error = None
        job.updated_at = now

        if reset_attempts:
            job.attempt_count = 0

        version = db.query(DocumentVersion).filter(DocumentVersion.id == job.document_version_id).first()
        if version:
            version.extraction_status = ExtractionStatus.PENDING
            version.extraction_error = None
            # version.extracted_text is preserved

        return job

    def recover_expired_leases(self, db: Session) -> int:
        """
        Detects abandoned jobs whose worker lease has expired and resets them to QUEUED
        if they have remaining attempt budget, or marks them FAILED if exhausted.
        """
        now = utc_now()
        # Find RUNNING jobs with lease_expires_at < now
        abandoned_jobs = (
            db.query(OCRJob)
            .filter(
                OCRJob.status == OCRJobStatus.RUNNING,
                OCRJob.lease_expires_at != None,
                OCRJob.lease_expires_at < now,
            )
            .with_for_update(skip_locked=True)
            .all()
        )

        recovered_count = 0
        for job in abandoned_jobs:
            logger.warning(
                f"Recovering abandoned OCR job {job.id} for version {job.document_version_id} "
                f"(lease expired at {job.lease_expires_at}, last worker: {job.worker_id})"
            )
            if job.attempt_count < job.max_attempts:
                job.status = OCRJobStatus.QUEUED
                job.worker_id = None
                job.lease_expires_at = None
                job.next_retry_at = now
                job.last_error = "Recovered from expired worker lease"
                job.updated_at = now
            else:
                job.status = OCRJobStatus.FAILED
                job.worker_id = None
                job.lease_expires_at = None
                job.completed_at = now
                job.last_error = "Worker lease expired and retry budget exhausted"
                job.updated_at = now

                # Also update corresponding version status to failed
                version = db.query(DocumentVersion).filter(DocumentVersion.id == job.document_version_id).first()
                if version and version.extraction_status != ExtractionStatus.COMPLETED:
                    version.extraction_status = ExtractionStatus.FAILED
                    version.extraction_error = job.last_error

            recovered_count += 1

        if recovered_count > 0:
            db.commit()

        return recovered_count

    def claim_next_job(self, db: Session) -> Optional[OCRJob]:
        """
        Atomically claims one eligible QUEUED job using SELECT ... FOR UPDATE SKIP LOCKED.
        Returns the claimed OCRJob with status=RUNNING and updated lease, or None if no job available.
        """
        now = utc_now()
        lease_expiry = now + timedelta(seconds=self.lease_duration_seconds)

        # Select one eligible job
        # An eligible job has status=QUEUED, next_retry_at <= now, and attempt_count < max_attempts
        candidate = (
            db.query(OCRJob)
            .filter(
                OCRJob.status == OCRJobStatus.QUEUED,
                OCRJob.next_retry_at <= now,
                OCRJob.attempt_count < OCRJob.max_attempts,
            )
            .order_by(OCRJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .first()
        )

        if not candidate:
            return None

        # Atomically transition to RUNNING
        candidate.status = OCRJobStatus.RUNNING
        candidate.worker_id = self.worker_id
        candidate.started_at = now
        candidate.lease_expires_at = lease_expiry
        candidate.attempt_count += 1
        candidate.updated_at = now

        # Also set document version status to processing
        version = db.query(DocumentVersion).filter(DocumentVersion.id == candidate.document_version_id).first()
        if version and version.extraction_status != ExtractionStatus.COMPLETED:
            version.extraction_status = ExtractionStatus.PROCESSING

        db.commit()
        try:
            db.refresh(candidate)
        except Exception:
            return None
        return candidate

    def execute_job(self, db: Session, job: OCRJob) -> bool:
        """
        Executes text extraction for the claimed job.
        Updates job and version statuses, handles retries or permanent failures.
        Returns True if completed successfully, False otherwise.
        """
        version = db.query(DocumentVersion).filter(DocumentVersion.id == job.document_version_id).first()
        if not version:
            logger.error(f"OCR Job {job.id} aborted: DocumentVersion {job.document_version_id} not found in DB")
            job.status = OCRJobStatus.FAILED
            job.completed_at = utc_now()
            job.last_error = "Document version not found"
            job.updated_at = utc_now()
            db.commit()
            return False

        # If version was already completed by another task or historical backfill
        if version.extraction_status == ExtractionStatus.COMPLETED and version.extracted_text is not None:
            logger.info(f"Version {version.id} already completed; marking job {job.id} as completed.")
            job.status = OCRJobStatus.COMPLETED
            job.completed_at = utc_now()
            job.lease_expires_at = None
            job.updated_at = utc_now()
            db.commit()
            return True

        try:
            # Call existing extraction service
            result = ocr_service.process_and_persist_version(db=db, version=version)

            # Mark job completed
            now = utc_now()
            job.status = OCRJobStatus.COMPLETED
            job.completed_at = now
            job.lease_expires_at = None
            job.last_error = None
            job.updated_at = now
            db.commit()

            # Record audit event
            audit_service.log_event(
                db=db,
                action="document.ocr_processed",
                resource_type="document_version",
                outcome=AuditOutcome.SUCCESS,
                actor_id=None,
                resource_id=version.id,
                details={
                    "job_id": job.id,
                    "attempt_count": job.attempt_count,
                    "strategy": result.strategy.value if result.strategy else None,
                    "char_count": result.char_count,
                },
                raise_on_failure=False,
            )
            return True

        except (UnsupportedFormatError, CorruptFileError, EncryptedFileError) as perm_exc:
            # Non-retryable permanent failure
            db.rollback()
            job_record = db.query(OCRJob).filter(OCRJob.id == job.id).first()
            if not job_record:
                return False

            now = utc_now()
            sanitized_err = str(perm_exc)[:250] if str(perm_exc) else perm_exc.__class__.__name__
            logger.warning(f"Permanent failure for job {job.id}: {sanitized_err}")

            job_record.status = OCRJobStatus.FAILED
            job_record.completed_at = now
            job_record.lease_expires_at = None
            job_record.last_error = sanitized_err
            job_record.updated_at = now

            version = db.query(DocumentVersion).filter(DocumentVersion.id == job_record.document_version_id).first()
            if version and version.extraction_status != ExtractionStatus.COMPLETED:
                version.extraction_status = ExtractionStatus.FAILED
                version.extraction_error = sanitized_err

            db.commit()

            audit_service.log_event(
                db=db,
                action="document.ocr_failed",
                resource_type="document_version",
                outcome=AuditOutcome.FAILED,
                actor_id=None,
                resource_id=job_record.document_version_id,
                details={
                    "job_id": job_record.id,
                    "attempt_count": job_record.attempt_count,
                    "error": sanitized_err,
                    "permanent": True,
                },
                raise_on_failure=False,
            )
            return False

        except Exception as exc:
            # Transient or unexpected error -> evaluate retry budget
            db.rollback()
            job_record = db.query(OCRJob).filter(OCRJob.id == job.id).first()
            if not job_record:
                return False

            now = utc_now()
            raw_err = str(exc)[:250] if str(exc) else exc.__class__.__name__
            logger.error(f"Error executing OCR job {job.id} (attempt {job_record.attempt_count}/{job_record.max_attempts}): {raw_err}")

            if job_record.attempt_count < job_record.max_attempts:
                # Schedule retry with exponential backoff
                delay_seconds = self.base_retry_delay * (2 ** (job_record.attempt_count - 1))
                job_record.status = OCRJobStatus.QUEUED
                job_record.next_retry_at = now + timedelta(seconds=delay_seconds)
                job_record.lease_expires_at = None
                job_record.last_error = raw_err
                job_record.updated_at = now

                # Version status remains PENDING until retries are exhausted
                version = db.query(DocumentVersion).filter(DocumentVersion.id == job_record.document_version_id).first()
                if version and version.extraction_status != ExtractionStatus.COMPLETED:
                    version.extraction_status = ExtractionStatus.PENDING
                    version.extraction_error = f"Retry scheduled (attempt {job_record.attempt_count}/{job_record.max_attempts}): {raw_err}"

                db.commit()
                return False
            else:
                # Exhausted retry attempts -> permanently mark FAILED
                job_record.status = OCRJobStatus.FAILED
                job_record.completed_at = now
                job_record.lease_expires_at = None
                job_record.last_error = f"Exceeded max attempts ({job_record.max_attempts}): {raw_err}"
                job_record.updated_at = now

                version = db.query(DocumentVersion).filter(DocumentVersion.id == job_record.document_version_id).first()
                if version and version.extraction_status != ExtractionStatus.COMPLETED:
                    version.extraction_status = ExtractionStatus.FAILED
                    version.extraction_error = job_record.last_error

                db.commit()

                audit_service.log_event(
                    db=db,
                    action="document.ocr_failed",
                    resource_type="document_version",
                    outcome=AuditOutcome.FAILED,
                    actor_id=None,
                    resource_id=job_record.document_version_id,
                    details={
                        "job_id": job_record.id,
                        "attempt_count": job_record.attempt_count,
                        "error": job_record.last_error,
                        "permanent": True,
                    },
                    raise_on_failure=False,
                )
                return False

    def process_one(self) -> bool:
        """
        Executes one recovery check followed by claiming and executing one job.
        Uses an isolated database session and releases all resources on exit.
        Returns True if a job was processed, False if queue was empty.
        """
        db = SessionLocal()
        try:
            # 1. Recover any expired leases first
            self.recover_expired_leases(db)

            # 2. Claim next available job
            job = self.claim_next_job(db)
            if not job:
                return False

            # 3. Execute claimed job
            self.execute_job(db, job)
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def run_worker_loop(self, stop_event=None, max_iterations: Optional[int] = None) -> None:
        """
        Main worker polling loop.
        """
        logger.info(f"Starting OCR worker {self.worker_id} (poll interval: {settings.OCR_WORKER_POLL_INTERVAL_SECONDS}s)")
        iterations = 0

        while True:
            if stop_event and stop_event.is_set():
                logger.info(f"Worker {self.worker_id} stopping on shutdown signal.")
                break

            if max_iterations is not None and iterations >= max_iterations:
                break

            try:
                processed = self.process_one()
                iterations += 1

                if not processed:
                    time.sleep(settings.OCR_WORKER_POLL_INTERVAL_SECONDS)
            except Exception as e:
                logger.error(f"Unexpected error in worker loop: {e}")
                time.sleep(settings.OCR_WORKER_POLL_INTERVAL_SECONDS)


ocr_job_service = OCRJobService()
