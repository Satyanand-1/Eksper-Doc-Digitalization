import uuid
import math
import logging
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, status, Request, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select, asc
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus, ExtractionStatus
from app.models.workflow import ReviewWorkflow, ReviewAssignment, WorkflowState
from app.models.audit import AuditOutcome
from app.schemas.document import (
    DocumentUploadResponse,
    DocumentSummaryResponse,
    DocumentDetailResponse,
    DocumentVersionResponse,
    PaginatedDocumentResponse,
    VersionUploadResponse,
    CreatorInfo,
)
from app.schemas.workflow import (
    SubmitForReviewRequest,
    WorkflowSubmissionResponse,
    ReviewAssignmentResponse,
    DocumentWorkflowHistoryResponse,
    WorkflowHistoryAttempt,
    WorkflowHistoryAssignment,
    UserDisplayInfo,
)

from app.services.storage import storage_service, StorageSecurityError, StorageFileExistsError
from app.services.file_validator import (
    sanitize_filename,
    inspect_file_content,
    validate_filename_and_content_match,
    FileValidationError,
)
from app.services.reference_generator import generate_document_reference
from app.services.authorization import document_auth_service
from app.services.notification import notification_service
from app.services.audit import audit_service, AuditWriteError
from app.services.ocr_worker import ocr_job_service
from app.services.ocr import process_version_background


logger = logging.getLogger("edrms.documents")

router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new digital document",
    description="Uploads a PDF, JPEG, PNG, or TIFF document. Validates content magic bytes, stores binary securely, assigns a reference code, and creates version 1.",
)
def upload_document(
    request: Request,
    file: Annotated[UploadFile, File(description="File binary (PDF, JPEG, PNG, or TIFF)")],
    title: Annotated[str, Form(min_length=1, max_length=255, description="Document title")],
    background_tasks: BackgroundTasks,
    subject: Annotated[str | None, Form(max_length=500, description="Optional subject or summary")] = None,
    department: Annotated[str | None, Form(max_length=100, description="Optional department")] = None,
    classification: Annotated[str | None, Form(max_length=100, description="Optional classification (e.g., Contract, Policy, Invoice)")] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Authenticated document upload handler.
    Follows two-phase staging with database transaction and compensation cleanup.
    """
    # 1. Validate metadata fields
    clean_title = title.strip()
    if not clean_title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Title cannot be empty.",
        )

    assigned_department = (department or current_user.department or "General").strip()
    assigned_classification = (classification or "General").strip()
    clean_subject = subject.strip() if subject else None

    # Sanitize user-provided filename
    raw_filename = file.filename or "uploaded_document"
    safe_filename = sanitize_filename(raw_filename)

    # 2. Stage file to temporary storage while calculating hash and size
    staged_temp_path = None
    final_file_path = None

    try:
        staged_temp_path, computed_sha256, file_size = storage_service.stage_file(file.file)
    except Exception as exc:
        logger.error(f"Failed to stage uploaded file: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read and stage the uploaded file.",
        )

    try:
        # Check size constraints
        if file_size == 0:
            raise FileValidationError("Uploaded file is empty (0 bytes).")
        if file_size > settings.MAX_UPLOAD_SIZE_BYTES:
            max_mb = settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
            raise FileValidationError(f"File size exceeds the maximum limit of {max_mb} MB.")

        # 3. Content inspection via magic bytes directly from disk
        canonical_ext, canonical_mime = inspect_file_content(staged_temp_path)

        # Ensure filename extension matches magic bytes
        validate_filename_and_content_match(safe_filename, canonical_ext)

        # 4. Generate unique document reference and server-controlled storage key
        doc_reference = generate_document_reference(db)
        storage_key = storage_service.generate_storage_key(canonical_ext)

        # 5. Create DigitalDocument and DocumentVersion in database transaction
        doc = DigitalDocument(
            document_reference=doc_reference,
            title=clean_title,
            subject=clean_subject,
            department=assigned_department,
            classification=assigned_classification,
            mime_type=canonical_mime,
            status=DocumentStatus.DRAFT,
            created_by_id=current_user.id,
        )
        db.add(doc)
        db.flush()  # Flush to obtain doc.id for version foreign key

        version = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            storage_key=storage_key,
            original_filename=safe_filename,
            mime_type=canonical_mime,
            file_size_bytes=file_size,
            file_hash_sha256=computed_sha256,
            created_by_id=current_user.id,
        )
        db.add(version)
        db.flush()

        # Read staged file bytes for PostgreSQL persistent store
        try:
            with open(staged_temp_path, "rb") as f_staged:
                file_bytes = f_staged.read()
            storage_service.persist_binary_to_db(db=db, version_id=version.id, file_bytes=file_bytes)
        except Exception as store_err:
            logger.warning(f"Failed to persist binary to DB: {store_err}")

        # 6. Finalize file into permanent storage
        final_file_path = storage_service.finalize_staged_file(staged_temp_path, storage_key)
        staged_temp_path = None  # Moved successfully

        # 7. Create durable OCR job in the same database transaction
        ocr_job_service.enqueue_job(db=db, version_id=version.id)

        # 8. Commit database transaction (persists doc, version, and durable OCR job together)
        db.commit()
        db.refresh(doc)
        db.refresh(version)

        # 9. Trigger background OCR processing (works in conjunction with persistent job queue)
        background_tasks.add_task(process_version_background, version.id)

        # 10. Record mandatory audit log for initial document upload
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.upload",
            resource_type="document",
            outcome=AuditOutcome.SUCCESS,
            actor_id=current_user.id,
            resource_id=doc.id,
            details={
                "document_reference": doc.document_reference,
                "title": doc.title,
                "department": doc.department,
                "classification": doc.classification,
                "version_number": version.version_number,
                "file_size_bytes": version.file_size_bytes,
                "file_hash_sha256": version.file_hash_sha256,
            },
            raise_on_failure=True,
        )

        return DocumentUploadResponse(
            document_id=doc.id,
            document_reference=doc.document_reference,
            version_id=version.id,
            version_number=version.version_number,
            title=doc.title,
            subject=doc.subject,
            department=doc.department,
            classification=doc.classification,
            original_filename=version.original_filename,
            mime_type=version.mime_type,
            file_size_bytes=version.file_size_bytes,
            file_hash_sha256=version.file_hash_sha256,
            created_at=doc.created_at,
            status=doc.status,
            extraction_status=version.extraction_status,
        )

    except FileValidationError as val_err:
        # Cleanup temporary file
        if staged_temp_path:
            storage_service.cleanup_temp_file(staged_temp_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )

    except IntegrityError as integ_err:
        # Database conflict cleanup
        db.rollback()
        if staged_temp_path:
            storage_service.cleanup_temp_file(staged_temp_path)
        if final_file_path and final_file_path.exists():
            final_file_path.unlink(missing_ok=True)
        logger.error(f"Database integrity error during document upload: {integ_err}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A document reference or version conflict occurred. Please retry.",
        )

    except Exception as exc:
        # Compensation: Roll back DB and clean up all disk artifacts
        db.rollback()
        if staged_temp_path:
            storage_service.cleanup_temp_file(staged_temp_path)
        if final_file_path and final_file_path.exists():
            final_file_path.unlink(missing_ok=True)
        logger.error(f"Unexpected error during document upload: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while saving the document.",
        )


@router.get(
    "/{document_id}/versions/{version_number}/download",
    status_code=status.HTTP_200_OK,
    summary="Download a specific version of a document",
    description="Streams the binary content of the requested document version after verifying authentication and authorization.",
)
def download_document_version(
    document_id: uuid.UUID,
    version_number: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Secure document download endpoint:
    1. Authenticates user via Bearer JWT.
    2. Resolves document and version.
    3. Evaluates authorization rules based on role, department, and classification.
    4. Audits successful downloads and denied attempts.
    5. Resolves storage path and verifies storage-root boundaries.
    6. Streams binary content with sanitized Content-Disposition, nosniff, and cache-control headers.
    """
    # 1. Fetch document
    doc = db.query(DigitalDocument).filter(DigitalDocument.id == document_id).first()
    if not doc:
        # Record denial/not found in audit log
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.download",
            resource_type="document",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=document_id,
            details={"reason": "Document not found", "version_number": version_number},
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    # 2. Evaluate access authorization
    decision = document_auth_service.can_download(current_user, doc)
    if not decision.allowed:
        # Record authorization denial in audit log
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.download",
            resource_type="document",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=document_id,
            details={
                "reason": decision.reason,
                "version_number": version_number,
                "user_role": current_user.role.value,
                "user_dept": current_user.department,
                "doc_dept": doc.department,
                "doc_classification": doc.classification,
            },
            raise_on_failure=True,  # Mandatory audit enforcement
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {decision.reason}",
        )

    # 3. Fetch requested document version
    version = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_number == version_number,
        )
        .first()
    )
    if not version:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.download",
            resource_type="document_version",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=document_id,
            details={"reason": "Document version not found", "version_number": version_number},
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version_number} not found for this document.",
        )

    # 4. Resolve file path safely and ensure content is on disk (auto-restore from DB if cleared)
    try:
        file_path = storage_service.ensure_file_on_disk(db=db, version=version, doc=doc)
    except StorageSecurityError as sec_err:
        logger.critical(f"Storage path security anomaly detected: {sec_err}")
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.download",
            resource_type="document_version",
            outcome=AuditOutcome.FAILED,
            actor_id=current_user.id,
            resource_id=version.id,
            details={"reason": "Path traversal or security violation"},
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid storage reference.",
        )

    if not file_path.is_file():
        logger.error(f"Stored binary missing from disk for version {version.id}")
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.download",
            resource_type="document_version",
            outcome=AuditOutcome.FAILED,
            actor_id=current_user.id,
            resource_id=version.id,
            details={"reason": "Stored file binary missing on disk"},
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested file content was not found.",
        )


    # 5. Audit successful download
    audit_service.log_from_request(
        db=db,
        request=request,
        action="document.download",
        resource_type="document_version",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=version.id,
        details={
            "document_id": doc.id,
            "version_number": version.version_number,
            "file_size_bytes": version.file_size_bytes,
            "file_hash_sha256": version.file_hash_sha256,
        },
        raise_on_failure=True,  # Mandatory audit enforcement
    )

    # 6. Stream file content with secure headers
    def file_iterator(chunk_size: int = 64 * 1024):
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                yield chunk

    # Sanitize presentation filename for header
    safe_download_filename = sanitize_filename(version.original_filename)

    headers = {
        "Content-Disposition": f'attachment; filename="{safe_download_filename}"',
        "Content-Length": str(version.file_size_bytes),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    return StreamingResponse(
        file_iterator(),
        media_type=version.mime_type,
        headers=headers,
    )


@router.get(
    "/{document_id}/versions/{version_number}/preview",
    status_code=status.HTTP_200_OK,
    summary="Preview a specific version of a document inline",
    description="Streams the binary content of the requested document version inline for browser preview with restrictive CSP and security headers. Supports PDF, JPEG, PNG, and TIFF.",
)
def preview_document_version(
    document_id: uuid.UUID,
    version_number: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Secure document preview endpoint:
    1. Authenticates user via Bearer JWT.
    2. Resolves document and requested version from PostgreSQL.
    3. Enforces authorization using can_download/can_view_metadata. Non-disclosing 404 for unauthorized attempts.
    4. Validates that the document version is one of the supported preview formats (PDF, JPEG, PNG, TIFF).
    5. Resolves storage key safely and verifies containment inside storage root.
    6. Streams content inline with restrictive CSP, X-Content-Type-Options: nosniff, and Cache-Control: private, no-store.
    7. Records audit event before streaming begins.
    """
    # 1. Fetch document
    doc = db.query(DigitalDocument).filter(DigitalDocument.id == document_id).first()
    if not doc:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.preview",
            resource_type="document",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=document_id,
            details={"reason": "Document not found", "version_number": version_number},
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    # 2. Evaluate access authorization
    decision = document_auth_service.can_view_metadata(current_user, doc)
    if not decision.allowed:
        # Non-disclosing 404
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.preview",
            resource_type="document",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=document_id,
            details={
                "reason": decision.reason,
                "version_number": version_number,
                "user_role": current_user.role.value,
                "user_dept": current_user.department,
                "doc_dept": doc.department,
                "doc_classification": doc.classification,
            },
            raise_on_failure=True,  # Mandatory audit enforcement
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    # 3. Fetch requested document version
    version = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_number == version_number,
        )
        .first()
    )
    if not version:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.preview",
            resource_type="document_version",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=document_id,
            details={"reason": "Document version not found", "version_number": version_number},
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version_number} not found for this document.",
        )

    # 4. Validate preview format compatibility (PDF, JPEG, PNG, TIFF only)
    allowed_preview_mimes = {
        "application/pdf": "application/pdf",
        "image/jpeg": "image/jpeg",
        "image/jpg": "image/jpeg",
        "image/png": "image/png",
        "image/tiff": "image/tiff",
        "image/tif": "image/tiff",
    }
    clean_mime = (version.mime_type or "").strip().lower()
    if clean_mime not in allowed_preview_mimes:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Preview is not supported for MIME type '{version.mime_type}'. Supported formats are PDF, JPEG, PNG, and TIFF.",
        )
    preview_content_type = allowed_preview_mimes[clean_mime]

    # 5. Resolve storage path safely and ensure content is on disk (auto-restore from DB if cleared)
    try:
        file_path = storage_service.ensure_file_on_disk(db=db, version=version, doc=doc)
    except StorageSecurityError as sec_err:
        logger.critical(f"Storage path security anomaly detected during preview: {sec_err}")
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.preview",
            resource_type="document_version",
            outcome=AuditOutcome.FAILED,
            actor_id=current_user.id,
            resource_id=version.id,
            details={"reason": "Path traversal or security violation"},
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid storage reference.",
        )

    if not file_path.is_file():
        logger.error(f"Stored binary missing from disk for preview version {version.id}")
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.preview",
            resource_type="document_version",
            outcome=AuditOutcome.FAILED,
            actor_id=current_user.id,
            resource_id=version.id,
            details={"reason": "Stored file binary missing on disk"},
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested file content was not found.",
        )

    # 6. Audit successful preview before initiating response stream
    audit_service.log_from_request(
        db=db,
        request=request,
        action="document.preview",
        resource_type="document_version",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=version.id,
        details={
            "document_id": doc.id,
            "version_number": version.version_number,
            "file_size_bytes": version.file_size_bytes,
            "file_hash_sha256": version.file_hash_sha256,
            "mime_type": preview_content_type,
        },
        raise_on_failure=True,  # Mandatory audit enforcement
    )

    # 7. Stream file content with inline disposition and restrictive security headers
    def file_iterator(chunk_size: int = 64 * 1024):
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                yield chunk

    safe_preview_filename = sanitize_filename(version.original_filename)

    headers = {
        "Content-Disposition": f'inline; filename="{safe_preview_filename}"',
        "Content-Length": str(version.file_size_bytes),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        "X-Frame-Options": "SAMEORIGIN",
    }

    return StreamingResponse(
        file_iterator(),
        media_type=preview_content_type,
        headers=headers,
    )



@router.get(
    "",
    response_model=PaginatedDocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="List documents in repository with pagination and filters",
    description="Returns authorized documents matching query filters. Department and classification boundaries are enforced at the database level before counting and pagination.",
)
def list_documents(
    request: Request,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    search: Annotated[str | None, Query(max_length=100, description="Case-insensitive search across reference, title, and subject")] = None,
    department: Annotated[str | None, Query(max_length=100, description="Department filter")] = None,
    classification: Annotated[str | None, Query(max_length=100, description="Classification filter")] = None,
    status: Annotated[DocumentStatus | None, Query(description="Lifecycle status filter")] = None,
    sort_by: Annotated[Literal["created_at", "updated_at", "title", "document_reference"], Query(description="Sort field")] = "created_at",
    sort_order: Annotated[Literal["asc", "desc"], Query(description="Sort direction")] = "desc",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Paginated repository listing endpoint:
    - Automatically scopes queries to authorized records using document_auth_service.build_document_scope_filter
    - Applies search and metadata filters
    - Counts only authorized records
    - Returns deterministic, paginated summaries
    """
    # 1. Base query strictly scoped to authorized records
    auth_scope = document_auth_service.build_document_scope_filter(current_user)
    query = db.query(DigitalDocument).filter(auth_scope)

    # 2. Search filter (matches reference, title, subject, or OCR extracted text)
    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                DigitalDocument.document_reference.ilike(search_term),
                DigitalDocument.title.ilike(search_term),
                DigitalDocument.subject.ilike(search_term),
                DigitalDocument.versions.any(DocumentVersion.extracted_text.ilike(search_term)),
            )
        )

    # 3. Department filter
    if department:
        clean_dept = department.strip()
        query = query.filter(func.lower(DigitalDocument.department) == clean_dept.lower())

    # 4. Classification filter
    if classification:
        clean_class = classification.strip()
        query = query.filter(func.lower(DigitalDocument.classification) == clean_class.lower())

    # 5. Status filter
    if status:
        query = query.filter(DigitalDocument.status == status)

    # 6. Total count of authorized records matching filters
    total_count = query.count()
    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

    # 7. Sorting with deterministic secondary sort
    sort_column = getattr(DigitalDocument, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc(), DigitalDocument.id.desc())
    else:
        query = query.order_by(sort_column.asc(), DigitalDocument.id.asc())

    # 8. Pagination offset and limit
    offset = (page - 1) * page_size
    documents = query.offset(offset).limit(page_size).all()

    # 9. Build response items
    # Fetch version counts in batch to avoid N+1 query overhead
    doc_ids = [d.id for d in documents]
    version_counts = {}
    if doc_ids:
        counts = (
            db.query(DocumentVersion.document_id, func.count(DocumentVersion.id))
            .filter(DocumentVersion.document_id.in_(doc_ids))
            .group_by(DocumentVersion.document_id)
            .all()
        )
        version_counts = {doc_id: cnt for doc_id, cnt in counts}

    items = [
        DocumentSummaryResponse(
            id=d.id,
            document_reference=d.document_reference,
            title=d.title,
            subject=d.subject,
            department=d.department,
            classification=d.classification,
            mime_type=d.mime_type,
            status=d.status,
            created_at=d.created_at,
            updated_at=d.updated_at,
            version_count=version_counts.get(d.id, 1),
        )
        for d in documents
    ]

    return PaginatedDocumentResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total_count,
        total_pages=total_pages,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve document metadata",
    description="Returns detailed metadata and version numbers for a document. Enforces authorization; unauthorized requests receive 404 to avoid disclosing record existence.",
)
def get_document_metadata(
    document_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Single document metadata retrieval endpoint:
    1. Looks up document by UUID.
    2. Enforces document-level access authorization.
    3. Returns non-disclosing 404 on access denial to prevent enumeration of confidential records.
    4. Audits successful access.
    """
    doc = db.query(DigitalDocument).filter(DigitalDocument.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    # Check authorization using consistent rules
    decision = document_auth_service.can_view_metadata(current_user, doc)
    if not decision.allowed:
        # Record denial in audit log
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.view_metadata",
            resource_type="document",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=document_id,
            details={
                "reason": decision.reason,
                "user_role": current_user.role.value,
                "doc_dept": doc.department,
                "doc_classification": doc.classification,
            },
            raise_on_failure=True,
        )
        # Non-disclosing 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    # Fetch available version numbers
    versions = (
        db.query(DocumentVersion.version_number)
        .filter(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
        .all()
    )
    version_numbers = [v[0] for v in versions]

    # Safe creator info
    creator_info = None
    if doc.created_by:
        creator_info = CreatorInfo(
            id=doc.created_by.id,
            email=doc.created_by.email,
            full_name=doc.created_by.full_name,
            department=doc.created_by.department,
        )

    # Record successful metadata view
    audit_service.log_from_request(
        db=db,
        request=request,
        action="document.view_metadata",
        resource_type="document",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=doc.id,
        details={"document_reference": doc.document_reference},
        raise_on_failure=False,
    )

    return DocumentDetailResponse(
        id=doc.id,
        document_reference=doc.document_reference,
        title=doc.title,
        subject=doc.subject,
        department=doc.department,
        classification=doc.classification,
        mime_type=doc.mime_type,
        status=doc.status,
        created_by_id=doc.created_by_id,
        creator=creator_info,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        archived_at=doc.archived_at,
        retention_rule_id=doc.retention_rule_id,
        retention_start_date=doc.retention_start_date,
        retention_end_date=doc.retention_end_date,
        available_versions=version_numbers,
        version_count=len(version_numbers),
    )


@router.get(
    "/{document_id}/versions",
    response_model=list[DocumentVersionResponse],
    status_code=status.HTTP_200_OK,
    summary="List document versions",
    description="Returns metadata for all revisions of a document ordered newest first. Enforces authorization on parent document.",
)
def list_document_versions(
    document_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Version history enumeration endpoint:
    1. Looks up parent document.
    2. Enforces access authorization on parent document.
    3. Returns non-disclosing 404 on access denial to prevent enumeration.
    4. Returns deterministic, newest-first version metadata (excluding internal disk paths).
    """
    doc = db.query(DigitalDocument).filter(DigitalDocument.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    decision = document_auth_service.can_view_metadata(current_user, doc)
    if not decision.allowed:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.list_versions",
            resource_type="document",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=document_id,
            details={
                "reason": decision.reason,
                "user_role": current_user.role.value,
            },
            raise_on_failure=True,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    versions = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
        .all()
    )

    items = []
    for v in versions:
        creator_info = None
        if v.created_by:
            creator_info = CreatorInfo(
                id=v.created_by.id,
                email=v.created_by.email,
                full_name=v.created_by.full_name,
                department=v.created_by.department,
            )
        items.append(
            DocumentVersionResponse(
                id=v.id,
                document_id=v.document_id,
                version_number=v.version_number,
                original_filename=v.original_filename,
                mime_type=v.mime_type,
                file_size_bytes=v.file_size_bytes,
                file_hash_sha256=v.file_hash_sha256,
                extraction_status=v.extraction_status,
                extraction_completed_at=v.extraction_completed_at,
                extraction_error=v.extraction_error,
                extracted_text=v.extracted_text,
                created_by_id=v.created_by_id,
                creator=creator_info,
                created_at=v.created_at,
            )
        )

    return items


@router.post(
    "/{document_id}/versions",
    response_model=VersionUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new version of an existing document",
    description="Uploads a new file version for a draft document. Preserves document identity, increments version number safely, and writes audit event.",
)
def upload_new_version(
    document_id: uuid.UUID,
    file: Annotated[UploadFile, File(description="File binary (PDF, JPEG, PNG, or TIFF)")],
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    New version upload handler:
    1. Looks up parent document.
    2. Enforces version write authorization (can_upload_version) and draft status requirement.
    3. Stages file to temporary storage with size check and SHA-256 calculation.
    4. Validates magic bytes and extension consistency.
    5. Calculates next sequential version number and finalizes file into storage.
    6. Persists DocumentVersion record and updates parent document updated_at.
    7. Emits mandatory audit event.
    8. Handles failures with cleanup compensation (never deleting prior versions).
    """
    # 1. Fetch document
    doc = db.query(DigitalDocument).filter(DigitalDocument.id == document_id).first()
    if not doc:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.version_upload",
            resource_type="document",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=document_id,
            details={"reason": "Document not found"},
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    # 2. Enforce version write authorization & draft status
    decision = document_auth_service.can_upload_version(current_user, doc)
    if not decision.allowed:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.version_upload",
            resource_type="document",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=doc.id,
            details={
                "reason": decision.reason,
                "document_reference": doc.document_reference,
                "document_status": doc.status.value,
                "user_role": current_user.role.value,
                "user_dept": current_user.department,
                "doc_dept": doc.department,
            },
            raise_on_failure=True,  # Mandatory audit enforcement
        )

        # Distinguish between 400 Bad Request (invalid status) and 403 Forbidden (authorization)
        if doc.status != DocumentStatus.DRAFT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=decision.reason,
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {decision.reason}",
        )

    # 3. Sanitize user-provided filename
    raw_filename = file.filename or "uploaded_version"
    safe_filename = sanitize_filename(raw_filename)

    staged_temp_path = None
    final_file_path = None

    # Stage file to temp storage while computing SHA-256 and size
    try:
        staged_temp_path, computed_sha256, file_size = storage_service.stage_file(file.file)
    except Exception as exc:
        logger.error(f"Failed to stage version file: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read and stage the uploaded file.",
        )

    try:
        # Size validation
        if file_size == 0:
            raise FileValidationError("Uploaded file is empty (0 bytes).")
        if file_size > settings.MAX_UPLOAD_SIZE_BYTES:
            max_mb = settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
            raise FileValidationError(f"File size exceeds the maximum limit of {max_mb} MB.")

        # Magic byte inspection
        canonical_ext, canonical_mime = inspect_file_content(staged_temp_path)
        validate_filename_and_content_match(safe_filename, canonical_ext)

        # 4. Safely compute next sequential version number
        # Query highest version number for this document with a row lock / scalar max
        max_version = (
            db.query(func.max(DocumentVersion.version_number))
            .filter(DocumentVersion.document_id == doc.id)
            .scalar()
        )
        next_version_number = (max_version or 0) + 1

        # Generate storage key for new version
        storage_key = storage_service.generate_storage_key(canonical_ext)

        # 5. Create new DocumentVersion entity
        new_version = DocumentVersion(
            document_id=doc.id,
            version_number=next_version_number,
            storage_key=storage_key,
            original_filename=safe_filename,
            mime_type=canonical_mime,
            file_size_bytes=file_size,
            file_hash_sha256=computed_sha256,
            created_by_id=current_user.id,
        )
        db.add(new_version)
        db.flush()

        # Read staged file bytes for PostgreSQL persistent store
        try:
            with open(staged_temp_path, "rb") as f_staged:
                file_bytes = f_staged.read()
            storage_service.persist_binary_to_db(db=db, version_id=new_version.id, file_bytes=file_bytes)
        except Exception as store_err:
            logger.warning(f"Failed to persist version binary to DB: {store_err}")

        # 6. Finalize file into permanent storage
        final_file_path = storage_service.finalize_staged_file(staged_temp_path, storage_key)
        staged_temp_path = None

        # 7. Create durable OCR job in the same database transaction
        ocr_job_service.enqueue_job(db=db, version_id=new_version.id)

        # 8. Update parent document's updated_at timestamp and commit
        from app.models.document import utc_now
        doc.updated_at = utc_now()
        db.commit()
        db.refresh(new_version)

        # 9. Trigger background OCR processing (works in conjunction with persistent job queue)
        background_tasks.add_task(process_version_background, new_version.id)

        # 10. Record successful audit event (mandatory)
        audit_service.log_from_request(
            db=db,
            request=request,
            action="document.version_upload",
            resource_type="document_version",
            outcome=AuditOutcome.SUCCESS,
            actor_id=current_user.id,
            resource_id=new_version.id,
            details={
                "document_id": doc.id,
                "document_reference": doc.document_reference,
                "version_number": new_version.version_number,
                "file_size_bytes": new_version.file_size_bytes,
                "file_hash_sha256": new_version.file_hash_sha256,
            },
            raise_on_failure=True,
        )

        return VersionUploadResponse(
            document_id=doc.id,
            document_reference=doc.document_reference,
            version_id=new_version.id,
            version_number=new_version.version_number,
            original_filename=new_version.original_filename,
            mime_type=new_version.mime_type,
            file_size_bytes=new_version.file_size_bytes,
            file_hash_sha256=new_version.file_hash_sha256,
            extraction_status=new_version.extraction_status,
            created_at=new_version.created_at,
        )

    except FileValidationError as val_err:
        if staged_temp_path:
            storage_service.cleanup_temp_file(staged_temp_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )

    except IntegrityError as integ_err:
        db.rollback()
        if staged_temp_path:
            storage_service.cleanup_temp_file(staged_temp_path)
        if final_file_path and final_file_path.exists():
            final_file_path.unlink(missing_ok=True)
        logger.error(f"Version integrity conflict on document {doc.id}: {integ_err}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A concurrent version upload conflict occurred. Please retry.",
        )

    except Exception as exc:
        db.rollback()
        if staged_temp_path:
            storage_service.cleanup_temp_file(staged_temp_path)
        if final_file_path and final_file_path.exists():
            final_file_path.unlink(missing_ok=True)
        logger.error(f"Unexpected error uploading document version: {exc}")
        # If the exception is already an HTTPException or AuditWriteError re-raise appropriately
        if isinstance(exc, HTTPException):
            raise exc
        from app.services.audit import AuditWriteError
        if isinstance(exc, AuditWriteError):
            raise exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while saving the document version.",
        )


@router.post(
    "/{document_id}/submit-for-review",
    response_model=WorkflowSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a draft document for review",
    description="Submits a draft document for review by an explicitly assigned approver. Transitions document status from 'draft' to 'under_review' and creates a durable review workflow record.",
)
def submit_document_for_review(
    document_id: uuid.UUID,
    payload: SubmitForReviewRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Submits a draft document for review by an eligible approver.
    - Requires authenticated user with submission rights (Admin, Records Officer, or Department User in owning department).
    - Requires document to be in 'draft' status.
    - Approver must be active, hold 'approver' role, match document department, and not be the submitter.
    - Transitions document to 'under_review' and records 'workflow.submit_for_review' audit event.
    - Uses SELECT FOR UPDATE to prevent concurrent race conditions.
    """
    client_ip = request.client.host if request.client else "unknown"

    # 1. Fetch document with exclusive row lock to prevent concurrent state transitions
    doc = db.query(DigitalDocument).filter(DigitalDocument.id == document_id).with_for_update().first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found",
        )

    # 2. Check if document is in draft status
    if doc.status != DocumentStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document is in '{doc.status.value}' status. Only draft documents can be submitted for review.",
        )

    # 3. Check submitter authorization
    auth_decision = document_auth_service.can_submit_for_review(current_user, doc)
    if not auth_decision.allowed:
        # Audit log access denied event
        audit_service.log_from_request(
            db=db,
            request=request,
            action="workflow.submit_for_review.denied",
            resource_type="document",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=doc.id,
            details={
                "reason": auth_decision.reason,
                "user_role": current_user.role.value,
                "document_department": doc.department,
                "approver_id": str(payload.approver_id),
            },
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=auth_decision.reason,
        )

    # 4. Check if document already has an active pending review workflow
    existing_active_workflow = (
        db.query(ReviewWorkflow)
        .filter(
            ReviewWorkflow.document_id == doc.id,
            ReviewWorkflow.state == WorkflowState.PENDING,
        )
        .first()
    )
    if existing_active_workflow:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document already has an active review workflow pending.",
        )

    # 5. Fetch assigned approver
    approver = db.query(User).filter(User.id == payload.approver_id).first()
    if not approver:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Assigned approver with ID {payload.approver_id} not found.",
        )

    # 6. Validate approver eligibility
    approver_decision = document_auth_service.validate_approver_eligibility(
        approver=approver,
        document=doc,
        submitter=current_user,
    )
    if not approver_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=approver_decision.reason,
        )

    # 7. Create Workflow and Assignment, update document status
    try:
        workflow = ReviewWorkflow(
            document_id=doc.id,
            submitter_id=current_user.id,
            state=WorkflowState.PENDING,
            submission_comments=payload.comments,
        )
        db.add(workflow)
        db.flush()  # Generates workflow.id

        assignment = ReviewAssignment(
            workflow_id=workflow.id,
            assigned_approver_id=approver.id,
        )
        db.add(assignment)

        # Transition document status to UNDER_REVIEW
        doc.status = DocumentStatus.UNDER_REVIEW

        # Create in-app workflow notification for assigned approver
        notification_service.notify_workflow_submitted(
            db=db,
            workflow=workflow,
            document=doc,
            approver_id=approver.id,
        )

        db.flush()

        # Audit logging (mandatory: raise_on_failure=True)
        audit_service.log_from_request(
            db=db,
            request=request,
            action="workflow.submit_for_review",
            resource_type="document",
            outcome=AuditOutcome.SUCCESS,
            actor_id=current_user.id,
            resource_id=doc.id,
            details={
                "workflow_id": str(workflow.id),
                "assignment_id": str(assignment.id),
                "assigned_approver_id": str(approver.id),
                "assigned_approver_email": approver.email,
                "previous_status": DocumentStatus.DRAFT.value,
                "new_status": DocumentStatus.UNDER_REVIEW.value,
                "workflow_state": WorkflowState.PENDING.value,
                "comments": payload.comments,
            },
            raise_on_failure=True,
        )

        db.commit()
        db.refresh(workflow)
        db.refresh(assignment)
        db.refresh(doc)

        logger.info(
            f"Document {doc.document_reference} ({doc.id}) submitted for review by {current_user.email}. "
            f"Assigned approver: {approver.email} ({approver.id}). Workflow ID: {workflow.id}"
        )

        return WorkflowSubmissionResponse(
            workflow_id=workflow.id,
            document_id=doc.id,
            document_reference=doc.document_reference,
            document_status=doc.status,
            workflow_state=workflow.state,
            submitter_id=workflow.submitter_id,
            submitted_at=workflow.submitted_at,
            comments=workflow.submission_comments,
            assignment=ReviewAssignmentResponse(
                id=assignment.id,
                workflow_id=assignment.workflow_id,
                assigned_approver_id=assignment.assigned_approver_id,
                assigned_at=assignment.assigned_at,
                decision=assignment.decision,
                decided_at=assignment.decided_at,
                decision_comments=assignment.decision_comments,
            ),
        )

    except IntegrityError as integ_err:
        db.rollback()
        logger.error(f"Integrity conflict when submitting document {doc.id} for review: {integ_err}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A workflow conflict occurred. This document may already have an active workflow.",
        )
    except AuditWriteError as a_err:
        db.rollback()
        logger.error(f"Mandatory audit write failure on document {doc.id} submission: {a_err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security audit recording failed.",
        )
    except Exception as exc:
        db.rollback()
        logger.error(f"Error submitting document {doc.id} for review: {exc}")
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while submitting the document for review.",
        )


@router.get(
    "/{document_id}/workflow-history",
    response_model=DocumentWorkflowHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve workflow review history for a document",
    description="Returns the historical and current review workflow attempts for a document in chronological order (oldest first). Includes submitter, approver assignments, decisions, comments, and timestamps. Requires authentication and authorized role.",
)
def get_document_workflow_history(
    document_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Workflow History API:
    - Requires active authenticated user.
    - Resolves document; returns non-disclosing 404 if not found or caller lacks document visibility.
    - Evaluates can_view_workflow_history authorization policy.
    - Eager-loads ReviewWorkflow attempts (ordered by submitted_at ASC, id ASC).
    - Filters workflow attempts so that approvers only see attempts where they were explicitly assigned.
    - Returns structured chronological history without exposing file paths, internal keys, or secrets.
    """
    # 1. Fetch document
    doc = db.query(DigitalDocument).filter(DigitalDocument.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    # 2. Check workflow history access authorization
    auth_decision = document_auth_service.can_view_workflow_history(current_user, doc)
    if not auth_decision.allowed:
        # Non-disclosing 404 response to prevent enumeration of documents or workflows
        audit_service.log_from_request(
            db=db,
            request=request,
            action="workflow.history.denied",
            resource_type="document",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=doc.id,
            details={"reason": auth_decision.reason, "user_role": current_user.role.value},
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    # 3. Query all workflow attempts for this document with eager loading (oldest first)
    workflows = (
        db.query(ReviewWorkflow)
        .options(
            joinedload(ReviewWorkflow.submitter),
            joinedload(ReviewWorkflow.cancelled_by),
            selectinload(ReviewWorkflow.assignments).joinedload(ReviewAssignment.assigned_approver),
        )
        .filter(ReviewWorkflow.document_id == doc.id)
        .order_by(asc(ReviewWorkflow.submitted_at), asc(ReviewWorkflow.id))
        .all()
    )

    # 4. Filter workflow attempts based on role visibility (e.g. approvers only see assigned attempts)
    visible_workflows = document_auth_service.filter_workflows_for_user(current_user, workflows)

    # If the user is an approver and has no visible workflow attempts for this document,
    # return non-disclosing 404 so they cannot enumerate unassigned document workflows
    if current_user.role == UserRole.APPROVER and len(workflows) > 0 and len(visible_workflows) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    # 5. Build safe response model
    attempts = []
    for wf in visible_workflows:
        assignments_list = []
        for assign in sorted(wf.assignments, key=lambda a: (a.assigned_at, a.id)):
            appr = assign.assigned_approver
            assignments_list.append(
                WorkflowHistoryAssignment(
                    id=assign.id,
                    workflow_id=assign.workflow_id,
                    assigned_approver=UserDisplayInfo(
                        id=appr.id,
                        email=appr.email,
                        full_name=appr.full_name,
                        department=appr.department,
                    ),
                    assigned_at=assign.assigned_at,
                    decision=assign.decision,
                    decided_at=assign.decided_at,
                    decision_comments=assign.decision_comments,
                )
            )

        sub = wf.submitter
        canceller_info = (
            UserDisplayInfo(
                id=wf.cancelled_by.id,
                email=wf.cancelled_by.email,
                full_name=wf.cancelled_by.full_name,
                department=wf.cancelled_by.department,
            )
            if wf.cancelled_by
            else None
        )

        attempts.append(
            WorkflowHistoryAttempt(
                workflow_id=wf.id,
                state=wf.state,
                submitted_at=wf.submitted_at,
                submission_comments=wf.submission_comments,
                submitter=UserDisplayInfo(
                    id=sub.id,
                    email=sub.email,
                    full_name=sub.full_name,
                    department=sub.department,
                ),
                cancelled_by=canceller_info,
                cancelled_at=wf.cancelled_at,
                cancellation_comments=wf.cancellation_comments,
                assignments=assignments_list,
            )
        )

    return DocumentWorkflowHistoryResponse(
        document_id=doc.id,
        document_reference=doc.document_reference,
        document_status=doc.status,
        total_attempts=len(attempts),
        attempts=attempts,
    )





