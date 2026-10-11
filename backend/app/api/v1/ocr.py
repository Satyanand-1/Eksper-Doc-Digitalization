import math
import uuid
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.document import DocumentVersion, ExtractionStatus
from app.models.ocr_job import OCRJob, OCRJobStatus
from app.models.audit import AuditOutcome
from app.schemas.ocr import OCRJobResponse, PaginatedOCRJobResponse
from app.services.storage import storage_service, StorageSecurityError
from app.services.audit import audit_service, AuditWriteError
from app.services.ocr_worker import ocr_job_service

logger = logging.getLogger("edrms.ocr_api")

router = APIRouter(prefix="/api/v1/ocr", tags=["OCR Operations"])


def require_admin(current_user: User, db: Session, request: Request, action: str, resource_id: uuid.UUID | None = None) -> None:
    """
    Enforces that the authenticated user possesses the Administrator role.
    Records an audit denial if unauthorized.
    """
    if current_user.role != UserRole.ADMIN:
        audit_service.log_from_request(
            db=db,
            request=request,
            action=action,
            resource_type="ocr_job",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=resource_id,
            details={
                "reason": "Operation restricted to administrator role",
                "user_role": current_user.role.value,
            },
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation restricted to administrator role.",
        )


@router.get(
    "/jobs",
    response_model=PaginatedOCRJobResponse,
    status_code=status.HTTP_200_OK,
    summary="List OCR jobs with pagination and filters",
    description="Returns paginated operational metadata for durable OCR jobs. Restricted to administrators.",
)
def list_ocr_jobs(
    request: Request,
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    status_filter: Annotated[OCRJobStatus | None, Query(alias="status", description="Filter by OCR job status")] = None,
    document_version_id: Annotated[uuid.UUID | None, Query(description="Filter by document version ID")] = None,
    created_from: Annotated[datetime | None, Query(description="Filter jobs created at or after UTC timestamp")] = None,
    created_to: Annotated[datetime | None, Query(description="Filter jobs created at or before UTC timestamp")] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user, db, request, action="ocr.jobs_list")

    # Date range validation
    if created_from and created_to and created_from > created_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="created_from must be earlier than or equal to created_to.",
        )

    query = db.query(OCRJob)

    if status_filter:
        query = query.filter(OCRJob.status == status_filter)
    if document_version_id:
        query = query.filter(OCRJob.document_version_id == document_version_id)
    if created_from:
        query = query.filter(OCRJob.created_at >= created_from)
    if created_to:
        query = query.filter(OCRJob.created_at <= created_to)

    total_count = query.count()
    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

    offset = (page - 1) * page_size
    jobs = (
        query.order_by(OCRJob.created_at.desc(), OCRJob.id.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    # Mandatory audit logging
    try:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="ocr.jobs_list",
            resource_type="ocr_job",
            outcome=AuditOutcome.SUCCESS,
            actor_id=current_user.id,
            resource_id=None,
            details={
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "status_filter": status_filter.value if status_filter else None,
                "document_version_id": str(document_version_id) if document_version_id else None,
            },
            raise_on_failure=True,
        )
    except AuditWriteError as a_err:
        logger.error(f"Mandatory audit write failure on OCR jobs list: {a_err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security audit recording failed.",
        )

    return PaginatedOCRJobResponse(
        items=[OCRJobResponse.model_validate(j) for j in jobs],
        page=page,
        page_size=page_size,
        total=total_count,
        total_pages=total_pages,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=OCRJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Get OCR job operational detail",
    description="Returns operational metadata for a specific OCR job. Restricted to administrators.",
)
def get_ocr_job(
    job_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user, db, request, action="ocr.job_detail", resource_id=job_id)

    job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
    if not job:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="ocr.job_detail",
            resource_type="ocr_job",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=job_id,
            details={"reason": "OCR job not found"},
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OCR job not found.",
        )

    # Mandatory audit logging
    try:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="ocr.job_detail",
            resource_type="ocr_job",
            outcome=AuditOutcome.SUCCESS,
            actor_id=current_user.id,
            resource_id=job.id,
            details={
                "status": job.status.value,
                "attempt_count": job.attempt_count,
                "document_version_id": str(job.document_version_id),
            },
            raise_on_failure=True,
        )
    except AuditWriteError as a_err:
        logger.error(f"Mandatory audit write failure on OCR job detail: {a_err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security audit recording failed.",
        )

    return OCRJobResponse.model_validate(job)


@router.post(
    "/jobs/{job_id}/retry",
    response_model=OCRJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Retry a failed OCR job",
    description="Requeues an existing failed OCR job for processing. Enforces retry limits and verifies resource existence.",
)
def retry_ocr_job(
    job_id: uuid.UUID,
    request: Request,
    reset_attempts: Annotated[bool, Query(description="Explicit administrator authorization to reset attempt count for exhausted jobs")] = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user, db, request, action="ocr.job_retry", resource_id=job_id)

    # 1. Acquire row lock to prevent concurrent retry race conditions
    job = (
        db.query(OCRJob)
        .filter(OCRJob.id == job_id)
        .with_for_update()
        .first()
    )
    if not job:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="ocr.job_retry",
            resource_type="ocr_job",
            outcome=AuditOutcome.FAILED,
            actor_id=current_user.id,
            resource_id=job_id,
            details={"reason": "OCR job not found"},
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OCR job not found.",
        )

    # 2. State validation: only FAILED jobs can be retried
    if job.status != OCRJobStatus.FAILED:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="ocr.job_retry",
            resource_type="ocr_job",
            outcome=AuditOutcome.FAILED,
            actor_id=current_user.id,
            resource_id=job.id,
            details={
                "reason": f"Cannot retry job in '{job.status.value}' status",
                "current_status": job.status.value,
            },
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot retry job in '{job.status.value}' status. Only failed jobs can be retried.",
        )

    # 3. Retry limit validation
    if job.attempt_count >= job.max_attempts and not reset_attempts:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="ocr.job_retry",
            resource_type="ocr_job",
            outcome=AuditOutcome.FAILED,
            actor_id=current_user.id,
            resource_id=job.id,
            details={
                "reason": "Retry limit reached without explicit reset authorization",
                "attempt_count": job.attempt_count,
                "max_attempts": job.max_attempts,
            },
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Retry limit reached: job has reached maximum attempts ({job.attempt_count}/{job.max_attempts}). Explicit administrator authorization is required via reset_attempts=true.",
        )

    # 4. Verify associated DocumentVersion and stored file still exist
    version = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.id == job.document_version_id)
        .first()
    )
    if not version:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="ocr.job_retry",
            resource_type="ocr_job",
            outcome=AuditOutcome.FAILED,
            actor_id=current_user.id,
            resource_id=job.id,
            details={
                "reason": "Associated document version missing from database",
                "version_id": str(job.document_version_id),
            },
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated document version not found.",
        )

    try:
        storage_path = storage_service.resolve_storage_path(version.storage_key)
    except StorageSecurityError as sec_err:
        logger.critical(f"Storage path security anomaly detected: {sec_err}")
        audit_service.log_from_request(
            db=db,
            request=request,
            action="ocr.job_retry",
            resource_type="ocr_job",
            outcome=AuditOutcome.FAILED,
            actor_id=current_user.id,
            resource_id=job.id,
            details={"reason": "Storage path traversal or security anomaly"},
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid storage reference.",
        )

    if not storage_path.is_file():
        logger.error(f"Stored binary missing from disk for version {version.id}")
        audit_service.log_from_request(
            db=db,
            request=request,
            action="ocr.job_retry",
            resource_type="ocr_job",
            outcome=AuditOutcome.FAILED,
            actor_id=current_user.id,
            resource_id=job.id,
            details={"reason": "Stored binary file missing from disk", "version_id": str(version.id)},
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated document file not found in storage.",
        )

    # 5. Mutate job and version fields via OCRJobService
    prev_attempts = job.attempt_count
    ocr_job_service.requeue_failed_job(db=db, job=job, reset_attempts=reset_attempts)

    # 6. Atomic commit with mandatory audit write failure recovery
    try:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="ocr.job_retry",
            resource_type="ocr_job",
            outcome=AuditOutcome.SUCCESS,
            actor_id=current_user.id,
            resource_id=job.id,
            details={
                "document_version_id": str(job.document_version_id),
                "previous_attempt_count": prev_attempts,
                "new_attempt_count": job.attempt_count,
                "reset_attempts": reset_attempts,
            },
            raise_on_failure=True,
        )
        db.commit()
        db.refresh(job)
    except AuditWriteError as a_err:
        db.rollback()
        logger.error(f"Mandatory audit write failure on OCR job retry: {a_err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security audit recording failed.",
        )
    except Exception as exc:
        db.rollback()
        logger.error(f"Unexpected database error during OCR job retry: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to requeue OCR job.",
        )

    return OCRJobResponse.model_validate(job)
