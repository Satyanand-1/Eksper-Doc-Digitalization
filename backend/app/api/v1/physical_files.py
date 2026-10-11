"""
Physical File Registry API Router.
Handles registration, search/listing, metadata retrieval, metadata updates,
storage location assignment, and status transitions for governed physical files.
"""
import uuid
import math
import logging
from typing import Annotated, Literal
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, Response
from sqlalchemy import desc, asc, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.document import DigitalDocument
from app.models.storage_location import StorageLocation
from app.models.physical_file import (
    PhysicalFile,
    PhysicalRecordType,
    PhysicalFileStatus,
    VALID_STATUS_TRANSITIONS,
    utc_now,
)
from app.models.custody import (
    FileCustodyRecord,
    FileMovementHistory,
    CustodyStatus,
    PhysicalMovementType,
)
from app.models.audit import AuditOutcome
from app.schemas.physical_file import (
    PhysicalFileRegisterRequest,
    PhysicalFileUpdateRequest,
    PhysicalFileStatusChangeRequest,
    PhysicalFileSummaryResponse,
    PhysicalFileDetailResponse,
    PaginatedPhysicalFilesResponse,
    LinkedDigitalDocumentInfo,
    UserShortInfo,
    LabelPrintAuditRequest,
)
from app.schemas.storage_location import AssignFileLocationRequest
from app.schemas.custody import (
    CustodyCheckoutRequest,
    CustodyCheckinRequest,
    FileTransferRequest,
    CustodyRecordResponse,
    MovementHistoryResponse,
    PaginatedCustodyRecordsResponse,
    PaginatedMovementHistoryResponse,
    OverdueFileSummary,
    PaginatedOverdueFilesResponse,
    CustodyIntegrityReport,
    CustodyIntegrityIssue,
    PaginatedLocationTransfersResponse,
    LocationTransferEventItem,
)
from app.services.reference_generator import generate_physical_file_reference
from app.services.authorization import (
    physical_file_auth_service,
    document_auth_service,
    storage_location_auth_service,
    custody_auth_service,
)
from app.services.location_service import get_location_path
from app.services.audit import audit_service

logger = logging.getLogger("edrms.physical_files")

router = APIRouter(prefix="/api/v1/physical-files", tags=["Physical Files"])


@router.post(
    "",
    response_model=PhysicalFileDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a physical file",
    description="Registers a new physical record with metadata, unique PHY reference, optional link to an authorized digital document, and optional storage location.",
)
def register_physical_file(
    payload: PhysicalFileRegisterRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Register physical file:
    1. Authenticates caller & verifies active status.
    2. Validates department authorization:
       - admin / records_officer: any department.
       - department_user: strictly own department.
       - other roles: 403 Forbidden.
    3. Validates digital_document_id if provided (must exist and user must have metadata visibility).
    4. Validates storage_location_id if provided (must be active and capacity respected).
    5. Generates unique reference e.g. PHY-2026-XXXXXXXX.
    6. Commits record and logs mandatory audit event.
    """
    clean_dept = payload.department.strip()
    if not clean_dept:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Department cannot be empty.",
        )

    # 1. Authorization check
    auth_decision = physical_file_auth_service.can_register(current_user, clean_dept)
    if not auth_decision.allowed:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="physical_file.register",
            resource_type="physical_file",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            details={"reason": auth_decision.reason, "department": clean_dept},
            raise_on_failure=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {auth_decision.reason}",
        )

    # 2. Validate digital document relationship if provided
    linked_doc = None
    if payload.digital_document_id:
        linked_doc = db.query(DigitalDocument).filter(
            DigitalDocument.id == payload.digital_document_id
        ).first()
        if not linked_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Linked digital document not found.",
            )
        doc_view_decision = document_auth_service.can_view_metadata(current_user, linked_doc)
        if not doc_view_decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to link to this digital document.",
            )

    # 3. Validate storage location if provided
    storage_loc = None
    if payload.storage_location_id:
        storage_loc = db.query(StorageLocation).filter(
            StorageLocation.id == payload.storage_location_id
        ).first()
        if not storage_loc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Specified storage location not found.",
            )
        if not storage_loc.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign file to an inactive storage location.",
            )
        loc_view_decision = storage_location_auth_service.can_view(current_user, storage_loc)
        if not loc_view_decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to the specified storage location.",
            )
        # Check capacity
        if storage_loc.max_capacity is not None:
            curr_files = db.query(func.count(PhysicalFile.id)).filter(
                PhysicalFile.storage_location_id == storage_loc.id
            ).scalar() or 0
            if curr_files >= storage_loc.max_capacity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Storage location '{storage_loc.location_code}' is at full capacity ({storage_loc.max_capacity} items).",
                )

    # 4. Generate unique reference safely
    file_ref = generate_physical_file_reference(db, prefix="PHY")

    received_date = payload.date_received or utc_now()

    # 5. Instantiate physical file record
    physical_file = PhysicalFile(
        file_reference=file_ref,
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        record_type=payload.record_type,
        department=clean_dept,
        classification=payload.classification.strip() if payload.classification else None,
        digital_document_id=payload.digital_document_id,
        storage_location_id=payload.storage_location_id,
        external_reference=payload.external_reference.strip() if payload.external_reference else None,
        date_received=received_date,
        status=PhysicalFileStatus.ACTIVE,
        created_by_id=current_user.id,
    )
    db.add(physical_file)
    db.flush()

    # 6. Mandatory Audit Logging
    audit_service.log_from_request(
        db=db,
        request=request,
        action="physical_file.register",
        resource_type="physical_file",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=physical_file.id,
        details={
            "file_reference": physical_file.file_reference,
            "title": physical_file.title,
            "record_type": physical_file.record_type.value,
            "department": physical_file.department,
            "classification": physical_file.classification,
            "digital_document_id": str(physical_file.digital_document_id) if physical_file.digital_document_id else None,
            "storage_location_id": str(physical_file.storage_location_id) if physical_file.storage_location_id else None,
            "external_reference": physical_file.external_reference,
        },
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(physical_file)

    # 7. Build response
    linked_doc_info = None
    if physical_file.digital_document:
        linked_doc_info = LinkedDigitalDocumentInfo(
            id=physical_file.digital_document.id,
            document_reference=physical_file.digital_document.document_reference,
            title=physical_file.digital_document.title,
            department=physical_file.digital_document.department,
            classification=physical_file.digital_document.classification,
        )

    loc_path = None
    loc_name = None
    loc_code = None
    if physical_file.storage_location:
        loc_path = get_location_path(db, physical_file.storage_location)
        loc_name = physical_file.storage_location.name
        loc_code = physical_file.storage_location.location_code

    return PhysicalFileDetailResponse(
        id=physical_file.id,
        file_reference=physical_file.file_reference,
        title=physical_file.title,
        description=physical_file.description,
        record_type=physical_file.record_type,
        department=physical_file.department,
        classification=physical_file.classification,
        status=physical_file.status,
        digital_document_id=physical_file.digital_document_id,
        digital_document=linked_doc_info,
        storage_location_id=physical_file.storage_location_id,
        storage_location_name=loc_name,
        storage_location_code=loc_code,
        location_path=loc_path,
        external_reference=physical_file.external_reference,
        date_received=physical_file.date_received,
        created_by_id=physical_file.created_by_id,
        created_by=UserShortInfo(
            id=current_user.id,
            email=current_user.email,
            full_name=current_user.full_name,
            department=current_user.department,
        ),
        updated_by_id=None,
        updated_by=None,
        created_at=physical_file.created_at,
        updated_at=physical_file.updated_at,
    )


@router.get(
    "",
    response_model=PaginatedPhysicalFilesResponse,
    status_code=status.HTTP_200_OK,
    summary="List and search physical files",
    description="Returns authorized physical files matching search, department, record type, storage location, and status filters.",
)
def list_physical_files(
    request: Request,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    search: Annotated[str | None, Query(max_length=100, description="Search across reference, title, and external reference")] = None,
    department: Annotated[str | None, Query(max_length=100, description="Department filter")] = None,
    record_type: Annotated[PhysicalRecordType | None, Query(description="Record type filter")] = None,
    storage_location_id: Annotated[uuid.UUID | None, Query(description="Filter by storage location UUID")] = None,
    status_filter: Annotated[PhysicalFileStatus | None, Query(alias="status", description="Lifecycle status filter")] = None,
    classification: Annotated[str | None, Query(max_length=100, description="Classification filter")] = None,
    custody_state: Annotated[Literal["stored", "checked_out", "overdue"] | None, Query(description="Circulation / custody state filter")] = None,
    sort_by: Annotated[Literal["created_at", "updated_at", "title", "file_reference"], Query(description="Sort field")] = "created_at",
    sort_order: Annotated[Literal["asc", "desc"], Query(description="Sort direction")] = "desc",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List physical files with SQL-level pagination and scoping:
    - Automatically enforces department-level isolation via physical_file_auth_service.build_physical_file_scope_filter
    - Restricts search and counts strictly to authorized records
    """
    auth_scope = physical_file_auth_service.build_physical_file_scope_filter(current_user)
    query = db.query(PhysicalFile).filter(auth_scope)

    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                PhysicalFile.file_reference.ilike(search_term),
                PhysicalFile.title.ilike(search_term),
                PhysicalFile.external_reference.ilike(search_term),
            )
        )

    if department:
        query = query.filter(func.lower(PhysicalFile.department) == department.strip().lower())

    if record_type:
        query = query.filter(PhysicalFile.record_type == record_type)

    if classification and classification.strip():
        query = query.filter(func.lower(PhysicalFile.classification) == classification.strip().lower())

    if storage_location_id:
        query = query.filter(PhysicalFile.storage_location_id == storage_location_id)

    if status_filter:
        query = query.filter(PhysicalFile.status == status_filter)

    now = utc_now()
    if custody_state == "stored":
        query = query.filter(PhysicalFile.is_checked_out.is_(False))
    elif custody_state == "checked_out":
        query = query.filter(PhysicalFile.is_checked_out.is_(True))
    elif custody_state == "overdue":
        query = (
            query.join(FileCustodyRecord, PhysicalFile.id == FileCustodyRecord.physical_file_id)
            .filter(
                PhysicalFile.is_checked_out.is_(True),
                FileCustodyRecord.status == CustodyStatus.ACTIVE,
                FileCustodyRecord.expected_return_at.isnot(None),
                FileCustodyRecord.expected_return_at < now,
            )
        )

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    sort_column = getattr(PhysicalFile, sort_by, PhysicalFile.created_at)
    order_func = desc if sort_order == "desc" else asc
    query = query.order_by(order_func(sort_column), desc(PhysicalFile.id))

    records = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for r in records:
        loc_path = None
        loc_name = None
        loc_code = None
        if r.storage_location:
            loc_path = get_location_path(db, r.storage_location)
            loc_name = r.storage_location.name
            loc_code = r.storage_location.location_code

        # Check active custody info if checked out
        custodian_name = None
        is_overdue = False
        if r.is_checked_out:
            active_c = (
                db.query(FileCustodyRecord)
                .filter(
                    FileCustodyRecord.physical_file_id == r.id,
                    FileCustodyRecord.status == CustodyStatus.ACTIVE,
                )
                .first()
            )
            if active_c:
                custodian_name = active_c.custodian_name
                is_overdue = bool(active_c.expected_return_at and active_c.expected_return_at < now)

        items.append(
            PhysicalFileSummaryResponse(
                id=r.id,
                file_reference=r.file_reference,
                title=r.title,
                record_type=r.record_type,
                department=r.department,
                classification=r.classification,
                status=r.status,
                has_digital_document=r.digital_document_id is not None,
                is_checked_out=r.is_checked_out,
                current_custodian_name=custodian_name,
                is_overdue=is_overdue,
                storage_location_id=r.storage_location_id,
                storage_location_name=loc_name,
                storage_location_code=loc_code,
                location_path=loc_path,
                external_reference=r.external_reference,
                date_received=r.date_received,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )

    return PaginatedPhysicalFilesResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.get(
    "/lookup",
    response_model=PhysicalFileDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Secure Barcode/QR and Reference Lookup",
    description="Resolves a scanned QR code, barcode, or entered reference to an authorized PhysicalFile record. Returns non-disclosing 404 on access denial or invalid reference.",
)
def lookup_physical_file(
    request: Request,
    code: Annotated[str, Query(min_length=1, max_length=200, description="Scanned barcode, QR payload, reference, or UUID")],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Task 6.4 Secure Lookup:
    1. Normalizes input code (strips whitespace, removes URL prefixes if scanned as deep-link).
    2. Matches by file_reference, external_reference, or UUID id.
    3. Enforces object-level and department-level can_view authorization.
    4. Non-disclosing 404 on nonexistent record OR access denial (prevents enumeration).
    5. Logs audit event on success and denial.
    """
    raw_code = code.strip()
    if "\x00" in raw_code or "\0" in raw_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    # If code is a URL (e.g. from scanned QR deep-link https://.../physical-files?ref=PHY-...), extract identifier
    extracted_code = raw_code
    if "ref=" in raw_code:
        extracted_code = raw_code.split("ref=")[-1].split("&")[0].strip()
    elif "/" in raw_code:
        # e.g. path format /physical-files/PHY-2026-XXXX or /physical-files/<uuid>
        extracted_code = raw_code.rstrip("/").split("/")[-1].strip()

    # 1. Search record by exact file_reference (case-insensitive) or external_reference or UUID
    query = db.query(PhysicalFile)

    # Check if UUID
    file_record = None
    try:
        parsed_uuid = uuid.UUID(extracted_code)
        file_record = query.filter(PhysicalFile.id == parsed_uuid).first()
    except (ValueError, AttributeError):
        pass

    if not file_record:
        file_record = (
            query.filter(
                or_(
                    func.lower(PhysicalFile.file_reference) == extracted_code.lower(),
                    func.lower(PhysicalFile.external_reference) == extracted_code.lower(),
                )
            ).first()
        )

    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    # 2. Enforce object-level can_view authorization
    auth_decision = physical_file_auth_service.can_view(current_user, file_record)
    if not auth_decision.allowed:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="physical_file.lookup",
            resource_type="physical_file",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=file_record.id,
            details={
                "searched_code": raw_code,
                "reason": auth_decision.reason,
                "file_dept": file_record.department,
            },
            raise_on_failure=True,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    # 3. Audit log successful lookup
    audit_service.log_from_request(
        db=db,
        request=request,
        action="physical_file.lookup",
        resource_type="physical_file",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=file_record.id,
        details={
            "searched_code": raw_code,
            "resolved_reference": file_record.file_reference,
            "file_dept": file_record.department,
        },
        raise_on_failure=True,
    )

    # 4. Construct detail response
    linked_doc_info = None
    if file_record.digital_document:
        doc_view_decision = document_auth_service.can_view_metadata(current_user, file_record.digital_document)
        if doc_view_decision.allowed:
            linked_doc_info = LinkedDigitalDocumentInfo(
                id=file_record.digital_document.id,
                document_reference=file_record.digital_document.document_reference,
                title=file_record.digital_document.title,
                department=file_record.digital_document.department,
                classification=file_record.digital_document.classification,
            )

    loc_path = None
    loc_name = None
    loc_code = None
    if file_record.storage_location:
        loc_path = get_location_path(db, file_record.storage_location)
        loc_name = file_record.storage_location.name
        loc_code = file_record.storage_location.location_code

    creator_info = None
    if file_record.created_by:
        creator_info = UserShortInfo(
            id=file_record.created_by.id,
            email=file_record.created_by.email,
            full_name=file_record.created_by.full_name,
            department=file_record.created_by.department,
        )

    updater_info = None
    if file_record.updated_by:
        updater_info = UserShortInfo(
            id=file_record.updated_by.id,
            email=file_record.updated_by.email,
            full_name=file_record.updated_by.full_name,
            department=file_record.updated_by.department,
        )

    # Active custody info
    current_custodian_name = None
    is_overdue = False
    current_custody_id = None
    checked_out_at = None
    expected_return_at = None
    if file_record.is_checked_out:
        active_rec = (
            db.query(FileCustodyRecord)
            .filter(
                FileCustodyRecord.physical_file_id == file_record.id,
                FileCustodyRecord.status == CustodyStatus.ACTIVE,
            )
            .first()
        )
        if active_rec:
            current_custody_id = active_rec.id
            current_custodian_name = active_rec.custodian_name
            checked_out_at = active_rec.checked_out_at
            expected_return_at = active_rec.expected_return_at
            now = utc_now()
            is_overdue = bool(active_rec.expected_return_at and active_rec.expected_return_at < now)

    return PhysicalFileDetailResponse(
        id=file_record.id,
        file_reference=file_record.file_reference,
        title=file_record.title,
        description=file_record.description,
        record_type=file_record.record_type,
        department=file_record.department,
        classification=file_record.classification,
        status=file_record.status,
        is_checked_out=file_record.is_checked_out,
        current_custodian_name=current_custodian_name,
        is_overdue=is_overdue,
        current_custody_id=current_custody_id,
        checked_out_at=checked_out_at,
        expected_return_at=expected_return_at,
        digital_document_id=file_record.digital_document_id if linked_doc_info else None,
        digital_document=linked_doc_info,
        storage_location_id=file_record.storage_location_id,
        storage_location_name=loc_name,
        storage_location_code=loc_code,
        location_path=loc_path,
        external_reference=file_record.external_reference,
        date_received=file_record.date_received,
        created_by_id=file_record.created_by_id,
        created_by=creator_info,
        updated_by_id=file_record.updated_by_id,
        updated_by=updater_info,
        created_at=file_record.created_at,
        updated_at=file_record.updated_at,
    )


@router.post(
    "/print-label",
    status_code=status.HTTP_200_OK,
    summary="Record Label Printing Audit Log",
    description="Records an audit trail event when authorized labels are generated or printed.",
)
def record_label_print(
    payload: LabelPrintAuditRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Audit logging for physical label printing:
    - Verifies user has access to view the files being printed.
    - Records tamper-evident audit event.
    """
    for file_id in payload.file_ids:
        rec = db.query(PhysicalFile).filter(PhysicalFile.id == file_id).first()
        if rec:
            decision = physical_file_auth_service.can_view(current_user, rec)
            if decision.allowed:
                audit_service.log_from_request(
                    db=db,
                    request=request,
                    action="physical_file.print_label",
                    resource_type="physical_file",
                    outcome=AuditOutcome.SUCCESS,
                    actor_id=current_user.id,
                    resource_id=rec.id,
                    details={
                        "file_reference": rec.file_reference,
                        "label_format": payload.label_format,
                        "department": rec.department,
                    },
                    raise_on_failure=True,
                )

    return {"status": "success", "printed_count": len(payload.file_ids)}


@router.get(
    "/custody-integrity",
    response_model=CustodyIntegrityReport,
    status_code=status.HTTP_200_OK,
    summary="Verify Chain-of-Custody Integrity",
    description="Read-only diagnostic audit identifying inconsistencies between physical file state, active custody records, completed records, movement events, and storage locations.",
)
def verify_custody_integrity(
    department: str | None = Query(None, description="Filter by department"),
    issue_type: str | None = Query(None, description="Filter by specific issue type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Task 6.5: Custody Integrity Verification
    Scans physical files within the caller's authorized scope and identifies:
    1. MISSING_ACTIVE_CUSTODY: is_checked_out=True but no ACTIVE custody record.
    2. UNEXPECTED_ACTIVE_CUSTODY: is_checked_out=False but an ACTIVE custody record exists.
    3. MULTIPLE_ACTIVE_CUSTODY: More than one ACTIVE custody record for the same file.
    4. LOCATION_MISMATCH_WITH_RETURN: File is marked stored, but current storage_location_id conflicts with latest check-in.
    5. LOCATION_MISMATCH_WITH_TRANSFER: File has completed transfers, but current storage_location_id conflicts with latest transfer destination.
    6. CHECKOUT_WITHOUT_MOVEMENT: An ACTIVE custody record exists with no corresponding CHECKOUT movement event.
    """
    auth_decision = custody_auth_service.can_view_custody_integrity(current_user)
    if not auth_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {auth_decision.reason}",
        )

    now = utc_now()

    # Base query for physical files scoped by caller permissions
    query = db.query(PhysicalFile)
    if current_user.role in (UserRole.DEPARTMENT_USER, UserRole.AUDITOR):
        user_dept = (current_user.department or "").strip().lower()
        query = query.filter(func.lower(PhysicalFile.department) == user_dept)
    elif department and department.strip():
        query = query.filter(func.lower(PhysicalFile.department) == department.strip().lower())

    files_list = query.order_by(PhysicalFile.created_at.desc()).all()
    total_files_scanned = len(files_list)

    all_issues: list[CustodyIntegrityIssue] = []

    for pf in files_list:
        # Fetch custody records
        custody_recs = (
            db.query(FileCustodyRecord)
            .filter(FileCustodyRecord.physical_file_id == pf.id)
            .order_by(FileCustodyRecord.checked_out_at.desc())
            .all()
        )
        active_custodies = [c for c in custody_recs if c.status == CustodyStatus.ACTIVE]

        # Fetch latest movement events
        movements = (
            db.query(FileMovementHistory)
            .filter(FileMovementHistory.physical_file_id == pf.id)
            .order_by(FileMovementHistory.event_at.desc())
            .all()
        )
        latest_movement = movements[0] if movements else None

        # Check Invariant 1: Marked checked out but no active custody record
        if pf.is_checked_out and len(active_custodies) == 0:
            all_issues.append(
                CustodyIntegrityIssue(
                    issue_type="MISSING_ACTIVE_CUSTODY",
                    severity="error",
                    physical_file_id=pf.id,
                    file_reference=pf.file_reference,
                    title=pf.title,
                    department=pf.department,
                    description="Physical file is marked as checked out, but has no active custody record.",
                    diagnostic_details={
                        "is_checked_out": True,
                        "active_custody_count": 0,
                    },
                    detected_at=now,
                )
            )

        # Check Invariant 2: Marked stored but active custody record exists
        if not pf.is_checked_out and len(active_custodies) > 0:
            all_issues.append(
                CustodyIntegrityIssue(
                    issue_type="UNEXPECTED_ACTIVE_CUSTODY",
                    severity="error",
                    physical_file_id=pf.id,
                    file_reference=pf.file_reference,
                    title=pf.title,
                    department=pf.department,
                    description=f"Physical file is marked stored, but holds {len(active_custodies)} active custody record(s).",
                    diagnostic_details={
                        "is_checked_out": False,
                        "active_custody_ids": [str(c.id) for c in active_custodies],
                    },
                    detected_at=now,
                )
            )

        # Check Invariant 3: Multiple active custody records
        if len(active_custodies) > 1:
            all_issues.append(
                CustodyIntegrityIssue(
                    issue_type="MULTIPLE_ACTIVE_CUSTODY",
                    severity="error",
                    physical_file_id=pf.id,
                    file_reference=pf.file_reference,
                    title=pf.title,
                    department=pf.department,
                    description=f"Physical file has {len(active_custodies)} conflicting active custody records.",
                    diagnostic_details={
                        "active_custody_ids": [str(c.id) for c in active_custodies],
                    },
                    detected_at=now,
                )
            )

        # Check Invariant 4 & 5: Location agreement with latest movement event
        if latest_movement:
            if latest_movement.movement_type == PhysicalMovementType.CHECKIN and not pf.is_checked_out:
                if latest_movement.destination_location_id != pf.storage_location_id:
                    all_issues.append(
                        CustodyIntegrityIssue(
                            issue_type="LOCATION_MISMATCH_WITH_RETURN",
                            severity="warning",
                            physical_file_id=pf.id,
                            file_reference=pf.file_reference,
                            title=pf.title,
                            department=pf.department,
                            description="Current storage location does not match the destination recorded during latest check-in.",
                            diagnostic_details={
                                "current_storage_location_id": str(pf.storage_location_id) if pf.storage_location_id else None,
                                "latest_checkin_dest_id": str(latest_movement.destination_location_id) if latest_movement.destination_location_id else None,
                            },
                            detected_at=now,
                        )
                    )
            elif latest_movement.movement_type == PhysicalMovementType.TRANSFER and not pf.is_checked_out:
                if latest_movement.destination_location_id != pf.storage_location_id:
                    all_issues.append(
                        CustodyIntegrityIssue(
                            issue_type="LOCATION_MISMATCH_WITH_TRANSFER",
                            severity="warning",
                            physical_file_id=pf.id,
                            file_reference=pf.file_reference,
                            title=pf.title,
                            department=pf.department,
                            description="Current storage location does not match the destination recorded in latest transfer.",
                            diagnostic_details={
                                "current_storage_location_id": str(pf.storage_location_id) if pf.storage_location_id else None,
                                "latest_transfer_dest_id": str(latest_movement.destination_location_id) if latest_movement.destination_location_id else None,
                            },
                            detected_at=now,
                        )
                    )

        # Check Invariant 6: Active custody record without corresponding checkout movement event
        for ac in active_custodies:
            has_matching_checkout = any(
                m.movement_type == PhysicalMovementType.CHECKOUT and m.custody_record_id == ac.id
                for m in movements
            )
            if not has_matching_checkout:
                all_issues.append(
                    CustodyIntegrityIssue(
                        issue_type="CHECKOUT_WITHOUT_MOVEMENT",
                        severity="warning",
                        physical_file_id=pf.id,
                        file_reference=pf.file_reference,
                        title=pf.title,
                        department=pf.department,
                        description="Active custody record has no corresponding checkout movement event.",
                        diagnostic_details={
                            "custody_record_id": str(ac.id),
                            "custodian_name": ac.custodian_name,
                        },
                        detected_at=now,
                    )
                )

    # Optional issue_type filter
    if issue_type and issue_type.strip():
        target_it = issue_type.strip().upper()
        all_issues = [issue for issue in all_issues if issue.issue_type == target_it]

    # Aggregate counts by issue type
    issues_by_type: dict[str, int] = {}
    for issue in all_issues:
        issues_by_type[issue.issue_type] = issues_by_type.get(issue.issue_type, 0) + 1

    total_issues = len(all_issues)
    total_pages = math.ceil(total_issues / page_size) if total_issues > 0 else 1
    paginated_items = all_issues[(page - 1) * page_size : page * page_size]

    return CustodyIntegrityReport(
        total_files_scanned=total_files_scanned,
        total_issues_found=total_issues,
        issues_by_type=issues_by_type,
        items=paginated_items,
        page=page,
        page_size=page_size,
        total=total_issues,
        total_pages=total_pages,
    )


@router.get(
    "/transfers",
    response_model=PaginatedLocationTransfersResponse,
    status_code=status.HTTP_200_OK,
    summary="Storage Location Transfers Governance Report",
    description="Returns transfers between storage locations over an optional date range, scoped to user permissions.",
)
def get_location_transfers_report(
    department: str | None = Query(None, description="Filter by file department"),
    from_date: datetime | None = Query(None, description="Start date (UTC)"),
    to_date: datetime | None = Query(None, description="End date (UTC)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Task 6.5: Location Transfers Governance Report
    Chronological reporting of transfers across physical locations.
    """
    auth_decision = custody_auth_service.can_view_overdue_report(current_user)
    if not auth_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {auth_decision.reason}",
        )

    query = (
        db.query(FileMovementHistory, PhysicalFile)
        .join(PhysicalFile, FileMovementHistory.physical_file_id == PhysicalFile.id)
        .filter(FileMovementHistory.movement_type == PhysicalMovementType.TRANSFER)
    )

    if current_user.role in (UserRole.DEPARTMENT_USER, UserRole.AUDITOR):
        user_dept = (current_user.department or "").strip().lower()
        query = query.filter(func.lower(PhysicalFile.department) == user_dept)
    elif department and department.strip():
        query = query.filter(func.lower(PhysicalFile.department) == department.strip().lower())

    if from_date:
        query = query.filter(FileMovementHistory.event_at >= from_date)
    if to_date:
        query = query.filter(FileMovementHistory.event_at <= to_date)

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    records = (
        query.order_by(desc(FileMovementHistory.event_at), desc(FileMovementHistory.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for mov, pf in records:
        actor_info = None
        if mov.actor:
            actor_info = UserShortInfo(
                id=mov.actor.id,
                email=mov.actor.email,
                full_name=mov.actor.full_name,
                department=mov.actor.department,
            )

        src_code = mov.source_location.location_code if mov.source_location else None
        src_name = mov.source_location.name if mov.source_location else None
        dest_code = mov.destination_location.location_code if mov.destination_location else None
        dest_name = mov.destination_location.name if mov.destination_location else None

        items.append(
            LocationTransferEventItem(
                movement_id=mov.id,
                physical_file_id=pf.id,
                file_reference=pf.file_reference,
                title=pf.title,
                department=pf.department,
                source_location_code=src_code,
                source_location_name=src_name,
                destination_location_code=dest_code,
                destination_location_name=dest_name,
                transferred_at=mov.event_at,
                reason=mov.reason,
                transferred_by=actor_info,
            )
        )

    return PaginatedLocationTransfersResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


def escape_csv_cell(val: str | None) -> str:
    """Safely escapes CSV cells against CSV formula injection attacks (=, +, -, @, \\t, \\r)."""
    if val is None:
        return ""
    text_val = str(val).strip()
    if text_val and text_val[0] in ("=", "+", "-", "@", "\t", "\r"):
        text_val = "'" + text_val
    if '"' in text_val or ',' in text_val or '\n' in text_val:
        text_val = '"' + text_val.replace('"', '""') + '"'
    return text_val


@router.get(
    "/export-csv",
    status_code=status.HTTP_200_OK,
    summary="Export Custody & Circulation Reports to CSV",
    description="Generates an authorized CSV export for overdue files, checked-out inventory, or transfers with formula-injection escaping.",
)
def export_custody_report_csv(
    report_type: Literal["overdue", "checked_out", "transfers"] = Query("overdue", description="Type of circulation report"),
    department: str | None = Query(None, description="Filter by department"),
    request: Request = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Task 6.5: Governed CSV Export
    - Strictly authorized and department-scoped
    - Escapes formula-injection characters (=, +, -, @)
    - Omits sensitive personal phone/email unless caller has administrative role
    - Audits export operation
    """
    auth_decision = custody_auth_service.can_export_reports(current_user)
    if not auth_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {auth_decision.reason}",
        )

    now = utc_now()
    csv_rows = []

    if report_type == "overdue":
        query = (
            db.query(FileCustodyRecord, PhysicalFile)
            .join(PhysicalFile, FileCustodyRecord.physical_file_id == PhysicalFile.id)
            .filter(
                FileCustodyRecord.status == CustodyStatus.ACTIVE,
                FileCustodyRecord.expected_return_at.isnot(None),
                FileCustodyRecord.expected_return_at < now,
                PhysicalFile.is_checked_out.is_(True),
            )
        )
        if current_user.role in (UserRole.DEPARTMENT_USER, UserRole.AUDITOR):
            user_dept = (current_user.department or "").strip().lower()
            query = query.filter(func.lower(PhysicalFile.department) == user_dept)
        elif department and department.strip():
            query = query.filter(func.lower(PhysicalFile.department) == department.strip().lower())

        records = query.order_by(asc(FileCustodyRecord.expected_return_at)).limit(2000).all()

        headers = [
            "File Reference", "Title", "Department", "Classification",
            "Custodian", "Custodian Department", "Checked Out Date",
            "Expected Return Date", "Days Overdue", "Storage Location Code", "Purpose"
        ]
        csv_rows.append(",".join(headers))

        for c_rec, pf in records:
            days_over = max(0, (now - c_rec.expected_return_at).days) if c_rec.expected_return_at else 0
            loc_code = pf.storage_location.location_code if pf.storage_location else ""
            row = [
                escape_csv_cell(pf.file_reference),
                escape_csv_cell(pf.title),
                escape_csv_cell(pf.department),
                escape_csv_cell(pf.classification or "UNCLASSIFIED"),
                escape_csv_cell(c_rec.custodian_name),
                escape_csv_cell(c_rec.custodian_department or ""),
                escape_csv_cell(c_rec.checked_out_at.strftime("%Y-%m-%d %H:%M:%S")),
                escape_csv_cell(c_rec.expected_return_at.strftime("%Y-%m-%d %H:%M:%S") if c_rec.expected_return_at else ""),
                escape_csv_cell(str(days_over)),
                escape_csv_cell(loc_code),
                escape_csv_cell(c_rec.purpose),
            ]
            csv_rows.append(",".join(row))

    elif report_type == "checked_out":
        query = (
            db.query(FileCustodyRecord, PhysicalFile)
            .join(PhysicalFile, FileCustodyRecord.physical_file_id == PhysicalFile.id)
            .filter(
                FileCustodyRecord.status == CustodyStatus.ACTIVE,
                PhysicalFile.is_checked_out.is_(True),
            )
        )
        if current_user.role in (UserRole.DEPARTMENT_USER, UserRole.AUDITOR):
            user_dept = (current_user.department or "").strip().lower()
            query = query.filter(func.lower(PhysicalFile.department) == user_dept)
        elif department and department.strip():
            query = query.filter(func.lower(PhysicalFile.department) == department.strip().lower())

        records = query.order_by(desc(FileCustodyRecord.checked_out_at)).limit(2000).all()

        headers = [
            "File Reference", "Title", "Department", "Classification",
            "Custodian", "Custodian Department", "Checked Out Date",
            "Expected Return Date", "Is Overdue", "Storage Location Code", "Purpose"
        ]
        csv_rows.append(",".join(headers))

        for c_rec, pf in records:
            is_over = bool(c_rec.expected_return_at and c_rec.expected_return_at < now)
            loc_code = pf.storage_location.location_code if pf.storage_location else ""
            row = [
                escape_csv_cell(pf.file_reference),
                escape_csv_cell(pf.title),
                escape_csv_cell(pf.department),
                escape_csv_cell(pf.classification or "UNCLASSIFIED"),
                escape_csv_cell(c_rec.custodian_name),
                escape_csv_cell(c_rec.custodian_department or ""),
                escape_csv_cell(c_rec.checked_out_at.strftime("%Y-%m-%d %H:%M:%S")),
                escape_csv_cell(c_rec.expected_return_at.strftime("%Y-%m-%d %H:%M:%S") if c_rec.expected_return_at else ""),
                escape_csv_cell("YES" if is_over else "NO"),
                escape_csv_cell(loc_code),
                escape_csv_cell(c_rec.purpose),
            ]
            csv_rows.append(",".join(row))

    elif report_type == "transfers":
        query = (
            db.query(FileMovementHistory, PhysicalFile)
            .join(PhysicalFile, FileMovementHistory.physical_file_id == PhysicalFile.id)
            .filter(FileMovementHistory.movement_type == PhysicalMovementType.TRANSFER)
        )
        if current_user.role in (UserRole.DEPARTMENT_USER, UserRole.AUDITOR):
            user_dept = (current_user.department or "").strip().lower()
            query = query.filter(func.lower(PhysicalFile.department) == user_dept)
        elif department and department.strip():
            query = query.filter(func.lower(PhysicalFile.department) == department.strip().lower())

        records = query.order_by(desc(FileMovementHistory.event_at)).limit(2000).all()

        headers = [
            "File Reference", "Title", "Department",
            "Source Location", "Destination Location", "Transfer Date",
            "Transferred By", "Reason"
        ]
        csv_rows.append(",".join(headers))

        for mov, pf in records:
            src_code = mov.source_location.location_code if mov.source_location else "Unassigned"
            dest_code = mov.destination_location.location_code if mov.destination_location else ""
            row = [
                escape_csv_cell(pf.file_reference),
                escape_csv_cell(pf.title),
                escape_csv_cell(pf.department),
                escape_csv_cell(src_code),
                escape_csv_cell(dest_code),
                escape_csv_cell(mov.event_at.strftime("%Y-%m-%d %H:%M:%S")),
                escape_csv_cell(mov.actor.full_name if mov.actor else str(mov.actor_id)),
                escape_csv_cell(mov.reason),
            ]
            csv_rows.append(",".join(row))

    # Audit export event
    if request:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="physical_file.export_csv",
            resource_type="physical_file",
            outcome=AuditOutcome.SUCCESS,
            actor_id=current_user.id,
            details={
                "report_type": report_type,
                "department_filter": department,
                "exported_rows": len(csv_rows) - 1,
            },
            raise_on_failure=True,
        )

    content = "\r\n".join(csv_rows)
    filename = f"custody_{report_type}_{now.strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@router.get(
    "/overdue",
    response_model=PaginatedOverdueFilesResponse,
    status_code=status.HTTP_200_OK,
    summary="List overdue physical files",
    description="Returns checked-out physical files whose expected return timestamp has passed, scoped by user permissions.",
)
def get_overdue_physical_files(
    department: str | None = Query(None, description="Filter by department"),
    custodian: str | None = Query(None, description="Filter by custodian name or department"),
    min_days_overdue: int | None = Query(None, ge=0, description="Minimum days overdue"),
    max_expected_date: datetime | None = Query(None, description="Filter by maximum expected return date"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Overdue physical records governance reporting:
    - Verifies user role authorization (Admin, Records Officer, Auditor, Department User).
    - Enforces department scoping (Department User strictly sees own department).
    - Identifies ACTIVE custody records with expected_return_at in the past.
    - Excludes returned records and respects timezone-aware boundary checks.
    """
    auth_decision = custody_auth_service.can_view_overdue_report(current_user)
    if not auth_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {auth_decision.reason}",
        )

    now = utc_now()

    # Query active custody records where expected_return_at < now
    query = (
        db.query(FileCustodyRecord, PhysicalFile)
        .join(PhysicalFile, FileCustodyRecord.physical_file_id == PhysicalFile.id)
        .filter(
            FileCustodyRecord.status == CustodyStatus.ACTIVE,
            FileCustodyRecord.expected_return_at.isnot(None),
            FileCustodyRecord.expected_return_at < now,
            PhysicalFile.is_checked_out.is_(True),
        )
    )

    # Scoping by user role
    if current_user.role == UserRole.DEPARTMENT_USER or current_user.role == UserRole.AUDITOR:
        user_dept = (current_user.department or "").strip().lower()
        query = query.filter(func.lower(PhysicalFile.department) == user_dept)
    elif department and department.strip():
        query = query.filter(func.lower(PhysicalFile.department) == department.strip().lower())

    # Optional Custodian filter
    if custodian and custodian.strip():
        term = f"%{custodian.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(FileCustodyRecord.custodian_name).like(term),
                func.lower(FileCustodyRecord.custodian_department).like(term),
            )
        )

    # Optional Max Expected Return Date
    if max_expected_date:
        query = query.filter(FileCustodyRecord.expected_return_at <= max_expected_date)

    # Optional Min Days Overdue filter
    if min_days_overdue is not None and min_days_overdue > 0:
        cutoff = now - timedelta(days=min_days_overdue)
        query = query.filter(FileCustodyRecord.expected_return_at <= cutoff)

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    records = (
        query.order_by(asc(FileCustodyRecord.expected_return_at), desc(FileCustodyRecord.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for custody_rec, file_rec in records:
        days_over = 0
        if custody_rec.expected_return_at:
            delta = now - custody_rec.expected_return_at
            days_over = max(0, delta.days)

        issuer_info = None
        if custody_rec.issued_by:
            issuer_info = UserShortInfo(
                id=custody_rec.issued_by.id,
                email=custody_rec.issued_by.email,
                full_name=custody_rec.issued_by.full_name,
                department=custody_rec.issued_by.department,
            )

        loc_name = file_rec.storage_location.name if file_rec.storage_location else None
        loc_code = file_rec.storage_location.location_code if file_rec.storage_location else None

        items.append(
            OverdueFileSummary(
                physical_file_id=file_rec.id,
                file_reference=file_rec.file_reference,
                title=file_rec.title,
                department=file_rec.department,
                classification=file_rec.classification,
                custody_record_id=custody_rec.id,
                custodian_name=custody_rec.custodian_name,
                custodian_department=custody_rec.custodian_department,
                custodian_contact=custody_rec.custodian_contact,
                checked_out_at=custody_rec.checked_out_at,
                expected_return_at=custody_rec.expected_return_at,
                days_overdue=days_over,
                purpose=custody_rec.purpose,
                storage_location_name=loc_name,
                storage_location_code=loc_code,
                issued_by=issuer_info,
            )
        )

    return PaginatedOverdueFilesResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


def _build_physical_file_detail_response(
    db: Session,
    file_record: PhysicalFile,
    current_user: User,
) -> PhysicalFileDetailResponse:
    linked_doc_info = None
    if file_record.digital_document:
        doc_view_decision = document_auth_service.can_view_metadata(current_user, file_record.digital_document)
        if doc_view_decision.allowed:
            linked_doc_info = LinkedDigitalDocumentInfo(
                id=file_record.digital_document.id,
                document_reference=file_record.digital_document.document_reference,
                title=file_record.digital_document.title,
                department=file_record.digital_document.department,
                classification=file_record.digital_document.classification,
            )

    loc_path = None
    loc_name = None
    loc_code = None
    if file_record.storage_location:
        loc_path = get_location_path(db, file_record.storage_location)
        loc_name = file_record.storage_location.name
        loc_code = file_record.storage_location.location_code

    creator_info = None
    if file_record.created_by:
        creator_info = UserShortInfo(
            id=file_record.created_by.id,
            email=file_record.created_by.email,
            full_name=file_record.created_by.full_name,
            department=file_record.created_by.department,
        )

    updater_info = None
    if file_record.updated_by:
        updater_info = UserShortInfo(
            id=file_record.updated_by.id,
            email=file_record.updated_by.email,
            full_name=file_record.updated_by.full_name,
            department=file_record.updated_by.department,
        )

    # Active custody info
    current_custodian_name = None
    is_overdue = False
    current_custody_id = None
    checked_out_at = None
    expected_return_at = None
    if file_record.is_checked_out:
        active_rec = (
            db.query(FileCustodyRecord)
            .filter(
                FileCustodyRecord.physical_file_id == file_record.id,
                FileCustodyRecord.status == CustodyStatus.ACTIVE,
            )
            .first()
        )
        if active_rec:
            current_custody_id = active_rec.id
            current_custodian_name = active_rec.custodian_name
            checked_out_at = active_rec.checked_out_at
            expected_return_at = active_rec.expected_return_at
            now = utc_now()
            is_overdue = bool(active_rec.expected_return_at and active_rec.expected_return_at < now)

    return PhysicalFileDetailResponse(
        id=file_record.id,
        file_reference=file_record.file_reference,
        title=file_record.title,
        description=file_record.description,
        record_type=file_record.record_type,
        department=file_record.department,
        classification=file_record.classification,
        status=file_record.status,
        is_checked_out=file_record.is_checked_out,
        current_custodian_name=current_custodian_name,
        is_overdue=is_overdue,
        current_custody_id=current_custody_id,
        checked_out_at=checked_out_at,
        expected_return_at=expected_return_at,
        digital_document_id=file_record.digital_document_id if linked_doc_info else None,
        digital_document=linked_doc_info,
        storage_location_id=file_record.storage_location_id,
        storage_location_name=loc_name,
        storage_location_code=loc_code,
        location_path=loc_path,
        external_reference=file_record.external_reference,
        date_received=file_record.date_received,
        created_by_id=file_record.created_by_id,
        created_by=creator_info,
        updated_by_id=file_record.updated_by_id,
        updated_by=updater_info,
        created_at=file_record.created_at,
        updated_at=file_record.updated_at,
    )


@router.get(
    "/{physical_file_id}",
    response_model=PhysicalFileDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve physical file metadata",
    description="Returns detailed metadata of an authorized physical file. Unauthorized attempts receive non-disclosing 404.",
)
def get_physical_file(
    physical_file_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve single physical file:
    1. Looks up record by UUID.
    2. Evaluates can_view permission.
    3. Returns non-disclosing 404 on access denial to prevent enumeration.
    """
    file_record = db.query(PhysicalFile).filter(PhysicalFile.id == physical_file_id).first()
    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    auth_decision = physical_file_auth_service.can_view(current_user, file_record)
    if not auth_decision.allowed:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="physical_file.view",
            resource_type="physical_file",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=physical_file_id,
            details={
                "reason": auth_decision.reason,
                "user_role": current_user.role.value,
                "file_dept": file_record.department,
            },
            raise_on_failure=True,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    return _build_physical_file_detail_response(db, file_record, current_user)


@router.patch(
    "/{physical_file_id}",
    response_model=PhysicalFileDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Update physical file metadata",
    description="Updates permitted metadata fields, digital document linkage, or storage location assignment.",
)
def update_physical_file(
    physical_file_id: uuid.UUID,
    payload: PhysicalFileUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update physical file metadata:
    1. Looks up record and verifies authorization via can_update.
    2. Enforces department reassignment policy (admin & records officer only).
    3. Validates digital document and storage location changes.
    4. Audits updates and commits transaction.
    """
    file_record = db.query(PhysicalFile).filter(PhysicalFile.id == physical_file_id).first()
    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    new_dept = payload.department.strip() if payload.department is not None else None
    auth_decision = physical_file_auth_service.can_update(current_user, file_record, new_department=new_dept)
    if not auth_decision.allowed:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="physical_file.update",
            resource_type="physical_file",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=physical_file_id,
            details={"reason": auth_decision.reason},
            raise_on_failure=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {auth_decision.reason}",
        )

    changes: dict = {}

    if payload.title is not None:
        clean_title = payload.title.strip()
        if clean_title != file_record.title:
            changes["title"] = {"old": file_record.title, "new": clean_title}
            file_record.title = clean_title

    if payload.description is not None:
        clean_desc = payload.description.strip() if payload.description else None
        if clean_desc != file_record.description:
            changes["description"] = "updated"
            file_record.description = clean_desc

    if payload.record_type is not None and payload.record_type != file_record.record_type:
        changes["record_type"] = {"old": file_record.record_type.value, "new": payload.record_type.value}
        file_record.record_type = payload.record_type

    if new_dept is not None and new_dept != file_record.department:
        changes["department"] = {"old": file_record.department, "new": new_dept}
        file_record.department = new_dept

    if payload.classification is not None:
        clean_cls = payload.classification.strip() if payload.classification else None
        if clean_cls != file_record.classification:
            changes["classification"] = {"old": file_record.classification, "new": clean_cls}
            file_record.classification = clean_cls

    if payload.external_reference is not None:
        clean_ext = payload.external_reference.strip() if payload.external_reference else None
        if clean_ext != file_record.external_reference:
            changes["external_reference"] = {"old": file_record.external_reference, "new": clean_ext}
            file_record.external_reference = clean_ext

    if payload.date_received is not None and payload.date_received != file_record.date_received:
        changes["date_received"] = {"old": file_record.date_received.isoformat(), "new": payload.date_received.isoformat()}
        file_record.date_received = payload.date_received

    # Digital document relationship
    if payload.unlink_digital_document:
        if file_record.digital_document_id is not None:
            changes["digital_document_id"] = {"old": str(file_record.digital_document_id), "new": None}
            file_record.digital_document_id = None
    elif payload.digital_document_id is not None and payload.digital_document_id != file_record.digital_document_id:
        linked_doc = db.query(DigitalDocument).filter(
            DigitalDocument.id == payload.digital_document_id
        ).first()
        if not linked_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Linked digital document not found.",
            )
        doc_view_decision = document_auth_service.can_view_metadata(current_user, linked_doc)
        if not doc_view_decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to link to this digital document.",
            )
        changes["digital_document_id"] = {
            "old": str(file_record.digital_document_id) if file_record.digital_document_id else None,
            "new": str(payload.digital_document_id),
        }
        file_record.digital_document_id = payload.digital_document_id

    # Storage location relationship
    if payload.unlink_storage_location or (payload.storage_location_id is not None and payload.storage_location_id != file_record.storage_location_id):
        if file_record.is_checked_out:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change storage location while physical file is checked out. File must be checked in first.",
            )

    if payload.unlink_storage_location:
        if file_record.storage_location_id is not None:
            changes["storage_location_id"] = {"old": str(file_record.storage_location_id), "new": None}
            file_record.storage_location_id = None
    elif payload.storage_location_id is not None and payload.storage_location_id != file_record.storage_location_id:
        dest_loc = db.query(StorageLocation).filter(
            StorageLocation.id == payload.storage_location_id
        ).first()
        if not dest_loc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Destination storage location not found.",
            )
        loc_assign_decision = storage_location_auth_service.can_assign_file(current_user, file_record, dest_loc)
        if not loc_assign_decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: {loc_assign_decision.reason}",
            )
        if dest_loc.max_capacity is not None:
            curr_count = db.query(func.count(PhysicalFile.id)).filter(
                PhysicalFile.storage_location_id == dest_loc.id
            ).scalar() or 0
            if curr_count >= dest_loc.max_capacity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Storage location '{dest_loc.location_code}' is at full capacity ({dest_loc.max_capacity} items).",
                )
        changes["storage_location_id"] = {
            "old": str(file_record.storage_location_id) if file_record.storage_location_id else None,
            "new": str(dest_loc.id),
        }
        file_record.storage_location_id = dest_loc.id

    file_record.updated_by_id = current_user.id
    file_record.updated_at = utc_now()

    audit_service.log_from_request(
        db=db,
        request=request,
        action="physical_file.update",
        resource_type="physical_file",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=file_record.id,
        details={
            "file_reference": file_record.file_reference,
            "changes": changes,
        },
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(file_record)

    return _build_physical_file_detail_response(db, file_record, current_user)


@router.post(
    "/{physical_file_id}/assign-location",
    response_model=PhysicalFileDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign storage location to physical file",
    description="Explicitly assigns or clears the current storage location of a physical file.",
)
def assign_storage_location(
    physical_file_id: uuid.UUID,
    payload: AssignFileLocationRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Direct location assignment operation:
    - Validates file and location permissions
    - Prevents assignment to inactive locations
    - Checks location capacity
    - Enforces department boundaries
    - Audits assignment
    """
    file_record = db.query(PhysicalFile).filter(PhysicalFile.id == physical_file_id).first()
    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    # Verify user can update this file
    file_auth = physical_file_auth_service.can_update(current_user, file_record)
    if not file_auth.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {file_auth.reason}",
        )

    if file_record.is_checked_out:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign storage location while physical file is checked out. File must be checked in first.",
        )

    old_loc_id = file_record.storage_location_id

    if payload.storage_location_id is None:
        # Unassign location
        file_record.storage_location_id = None
        new_loc_code = None
    else:
        dest_loc = db.query(StorageLocation).filter(
            StorageLocation.id == payload.storage_location_id
        ).first()
        if not dest_loc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Storage location not found.",
            )
        assign_decision = storage_location_auth_service.can_assign_file(current_user, file_record, dest_loc)
        if not assign_decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: {assign_decision.reason}",
            )
        if dest_loc.max_capacity is not None:
            curr_count = db.query(func.count(PhysicalFile.id)).filter(
                PhysicalFile.storage_location_id == dest_loc.id
            ).scalar() or 0
            if curr_count >= dest_loc.max_capacity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Storage location '{dest_loc.location_code}' is at full capacity ({dest_loc.max_capacity} items).",
                )
        file_record.storage_location_id = dest_loc.id
        new_loc_code = dest_loc.location_code

    file_record.updated_by_id = current_user.id
    file_record.updated_at = utc_now()

    audit_service.log_from_request(
        db=db,
        request=request,
        action="physical_file.assign_location",
        resource_type="physical_file",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=file_record.id,
        details={
            "file_reference": file_record.file_reference,
            "old_storage_location_id": str(old_loc_id) if old_loc_id else None,
            "new_storage_location_id": str(payload.storage_location_id) if payload.storage_location_id else None,
            "new_location_code": new_loc_code,
            "notes": payload.notes,
        },
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(file_record)

    linked_doc_info = None
    if file_record.digital_document:
        doc_view_decision = document_auth_service.can_view_metadata(current_user, file_record.digital_document)
        if doc_view_decision.allowed:
            linked_doc_info = LinkedDigitalDocumentInfo(
                id=file_record.digital_document.id,
                document_reference=file_record.digital_document.document_reference,
                title=file_record.digital_document.title,
                department=file_record.digital_document.department,
                classification=file_record.digital_document.classification,
            )

    loc_path = None
    loc_name = None
    loc_code = None
    if file_record.storage_location:
        loc_path = get_location_path(db, file_record.storage_location)
        loc_name = file_record.storage_location.name
        loc_code = file_record.storage_location.location_code

    creator_info = None
    if file_record.created_by:
        creator_info = UserShortInfo(
            id=file_record.created_by.id,
            email=file_record.created_by.email,
            full_name=file_record.created_by.full_name,
            department=file_record.created_by.department,
        )

    updater_info = UserShortInfo(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        department=current_user.department,
    )

    return PhysicalFileDetailResponse(
        id=file_record.id,
        file_reference=file_record.file_reference,
        title=file_record.title,
        description=file_record.description,
        record_type=file_record.record_type,
        department=file_record.department,
        classification=file_record.classification,
        status=file_record.status,
        digital_document_id=file_record.digital_document_id if linked_doc_info else None,
        digital_document=linked_doc_info,
        storage_location_id=file_record.storage_location_id,
        storage_location_name=loc_name,
        storage_location_code=loc_code,
        location_path=loc_path,
        external_reference=file_record.external_reference,
        date_received=file_record.date_received,
        created_by_id=file_record.created_by_id,
        created_by=creator_info,
        updated_by_id=file_record.updated_by_id,
        updated_by=updater_info,
        created_at=file_record.created_at,
        updated_at=file_record.updated_at,
    )


@router.patch(
    "/{physical_file_id}/status",
    response_model=PhysicalFileDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Change physical file lifecycle status",
    description="Transitions physical file status across permitted state paths (active, archived, inactive).",
)
def change_physical_file_status(
    physical_file_id: uuid.UUID,
    payload: PhysicalFileStatusChangeRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Change lifecycle status:
    1. Looks up record and checks can_change_status authorization.
    2. Validates state transition against VALID_STATUS_TRANSITIONS.
    3. Updates status, records mandatory audit log event, and commits.
    """
    file_record = db.query(PhysicalFile).filter(PhysicalFile.id == physical_file_id).first()
    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    auth_decision = physical_file_auth_service.can_change_status(current_user, file_record)
    if not auth_decision.allowed:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="physical_file.status_change",
            resource_type="physical_file",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=physical_file_id,
            details={"reason": auth_decision.reason},
            raise_on_failure=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {auth_decision.reason}",
        )

    current_status = file_record.status
    target_status = payload.status

    if current_status != target_status and file_record.is_checked_out:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change lifecycle status while physical file is checked out. File must be returned to storage first.",
        )

    if current_status == target_status:
        pass
    else:
        allowed_targets = VALID_STATUS_TRANSITIONS.get(current_status, set())
        if target_status not in allowed_targets:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status transition from '{current_status.value}' to '{target_status.value}'.",
            )

        file_record.status = target_status
        file_record.updated_by_id = current_user.id
        file_record.updated_at = utc_now()

    audit_service.log_from_request(
        db=db,
        request=request,
        action="physical_file.status_change",
        resource_type="physical_file",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=file_record.id,
        details={
            "file_reference": file_record.file_reference,
            "old_status": current_status.value,
            "new_status": target_status.value,
            "reason": payload.reason,
        },
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(file_record)

    linked_doc_info = None
    if file_record.digital_document:
        doc_view_decision = document_auth_service.can_view_metadata(current_user, file_record.digital_document)
        if doc_view_decision.allowed:
            linked_doc_info = LinkedDigitalDocumentInfo(
                id=file_record.digital_document.id,
                document_reference=file_record.digital_document.document_reference,
                title=file_record.digital_document.title,
                department=file_record.digital_document.department,
                classification=file_record.digital_document.classification,
            )

    loc_path = None
    loc_name = None
    loc_code = None
    if file_record.storage_location:
        loc_path = get_location_path(db, file_record.storage_location)
        loc_name = file_record.storage_location.name
        loc_code = file_record.storage_location.location_code

    creator_info = None
    if file_record.created_by:
        creator_info = UserShortInfo(
            id=file_record.created_by.id,
            email=file_record.created_by.email,
            full_name=file_record.created_by.full_name,
            department=file_record.created_by.department,
        )

    updater_info = UserShortInfo(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        department=current_user.department,
    )

    return PhysicalFileDetailResponse(
        id=file_record.id,
        file_reference=file_record.file_reference,
        title=file_record.title,
        description=file_record.description,
        record_type=file_record.record_type,
        department=file_record.department,
        classification=file_record.classification,
        status=file_record.status,
        is_checked_out=file_record.is_checked_out,
        digital_document_id=file_record.digital_document_id if linked_doc_info else None,
        digital_document=linked_doc_info,
        storage_location_id=file_record.storage_location_id,
        storage_location_name=loc_name,
        storage_location_code=loc_code,
        location_path=loc_path,
        external_reference=file_record.external_reference,
        date_received=file_record.date_received,
        created_by_id=file_record.created_by_id,
        created_by=creator_info,
        updated_by_id=file_record.updated_by_id,
        updated_by=updater_info,
        created_at=file_record.created_at,
        updated_at=file_record.updated_at,
    )


# =========================================================================
# Task 6.3: Circulation, Custody Tracking, Transfers & Overdue Reporting
# =========================================================================



@router.post(
    "/{physical_file_id}/checkout",
    response_model=CustodyRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Check out a physical file",
    description="Dispatches a physical file to an eligible custodian with durable custody tracking and movement history.",
)
def checkout_physical_file(
    physical_file_id: uuid.UUID,
    payload: CustodyCheckoutRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Check-out workflow:
    1. Lock file row with with_for_update() to prevent race conditions.
    2. Validates user permission via custody_auth_service.
    3. Validates file is eligible (ACTIVE status).
    4. Validates file is not already checked out.
    5. Validates file has an existing storage location.
    6. Validates expected return date if provided (must be in the future).
    7. Creates FileCustodyRecord and FileMovementHistory.
    8. Updates PhysicalFile (is_checked_out=True).
    9. Logs audit event atomically.
    """
    # 1. Lock file row for concurrent safety
    file_record = (
        db.query(PhysicalFile)
        .filter(PhysicalFile.id == physical_file_id)
        .with_for_update()
        .first()
    )
    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    # 2. Authorization check
    auth_decision = custody_auth_service.can_checkout(current_user, file_record)
    if not auth_decision.allowed:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="physical_file.checkout",
            resource_type="physical_file",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=file_record.id,
            details={"reason": auth_decision.reason},
            raise_on_failure=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {auth_decision.reason}",
        )

    # 3. Lifecycle eligibility
    if file_record.status != PhysicalFileStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot check out physical file in '{file_record.status.value}' status. Record must be active.",
        )

    # 4. Check already checked out
    if file_record.is_checked_out:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Physical file is already checked out to a custodian.",
        )

    # Verify no dangling active custody record
    active_custody = (
        db.query(FileCustodyRecord)
        .filter(
            FileCustodyRecord.physical_file_id == file_record.id,
            FileCustodyRecord.status == CustodyStatus.ACTIVE,
        )
        .first()
    )
    if active_custody:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Physical file already has an active custody record.",
        )

    # 5. Must have storage location
    if not file_record.storage_location_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot check out physical file: no current storage location is recorded. Assign a storage location first.",
        )

    # 6. Validate expected return date
    now = utc_now()
    if payload.expected_return_at and payload.expected_return_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expected return date must be in the future.",
        )

    # 7. Custodian validation if registered user
    if payload.custodian_user_id:
        custodian_user = db.query(User).filter(User.id == payload.custodian_user_id).first()
        if not custodian_user or not custodian_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected custodian user does not exist or is inactive.",
            )

    source_location = file_record.storage_location
    src_loc_name = source_location.name if source_location else "Storage"
    src_loc_code = source_location.location_code if source_location else None

    # Create Custody Record
    custody_record = FileCustodyRecord(
        physical_file_id=file_record.id,
        custodian_user_id=payload.custodian_user_id,
        custodian_name=payload.custodian_name.strip(),
        custodian_department=payload.custodian_department.strip() if payload.custodian_department else None,
        custodian_contact=payload.custodian_contact.strip() if payload.custodian_contact else None,
        status=CustodyStatus.ACTIVE,
        checked_out_at=now,
        expected_return_at=payload.expected_return_at,
        purpose=payload.purpose.strip(),
        issued_by_id=current_user.id,
    )
    db.add(custody_record)
    db.flush()

    # Create Movement History Event
    movement_event = FileMovementHistory(
        physical_file_id=file_record.id,
        movement_type=PhysicalMovementType.CHECKOUT,
        source_location_id=file_record.storage_location_id,
        destination_location_id=None,
        from_custody_state=f"Stored in {src_loc_code or src_loc_name}",
        to_custody_state=f"Checked out to {custody_record.custodian_name}",
        actor_id=current_user.id,
        event_at=now,
        reason=payload.purpose.strip(),
        custody_record_id=custody_record.id,
    )
    db.add(movement_event)

    # Update file state
    file_record.is_checked_out = True
    file_record.updated_by_id = current_user.id
    file_record.updated_at = now

    # Audit logging
    audit_service.log_from_request(
        db=db,
        request=request,
        action="physical_file.checkout",
        resource_type="physical_file",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=file_record.id,
        details={
            "file_reference": file_record.file_reference,
            "custody_record_id": str(custody_record.id),
            "custodian_name": custody_record.custodian_name,
            "custodian_department": custody_record.custodian_department,
            "expected_return_at": custody_record.expected_return_at.isoformat() if custody_record.expected_return_at else None,
            "source_location_code": src_loc_code,
            "purpose": custody_record.purpose,
        },
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(custody_record)

    issuer_info = UserShortInfo(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        department=current_user.department,
    )

    return CustodyRecordResponse(
        id=custody_record.id,
        physical_file_id=custody_record.physical_file_id,
        file_reference=file_record.file_reference,
        file_title=file_record.title,
        custodian_user_id=custody_record.custodian_user_id,
        custodian_name=custody_record.custodian_name,
        custodian_department=custody_record.custodian_department,
        custodian_contact=custody_record.custodian_contact,
        status=custody_record.status,
        checked_out_at=custody_record.checked_out_at,
        expected_return_at=custody_record.expected_return_at,
        checked_in_at=custody_record.checked_in_at,
        purpose=custody_record.purpose,
        checkin_notes=custody_record.checkin_notes,
        issued_by_id=custody_record.issued_by_id,
        issued_by=issuer_info,
        received_by_id=None,
        received_by=None,
        is_overdue=False,
        created_at=custody_record.created_at,
        updated_at=custody_record.updated_at,
    )


@router.post(
    "/{physical_file_id}/checkin",
    response_model=CustodyRecordResponse,
    status_code=status.HTTP_200_OK,
    summary="Check in a physical file",
    description="Records the return of a checked-out physical file, closes active custody, updates storage location, and logs movement.",
)
def checkin_physical_file(
    physical_file_id: uuid.UUID,
    payload: CustodyCheckinRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Check-in workflow:
    1. Lock file row with with_for_update() to prevent concurrent returns.
    2. Validates caller authorization via custody_auth_service.can_checkin.
    3. Confirms file is currently checked out.
    4. Finds and locks active custody record.
    5. Validates destination storage location (if specified):
       - Must exist and be active.
       - Caller must have permission to assign to destination.
       - Enforces destination capacity.
    6. Closes custody record (status=RETURNED, checked_in_at=now, received_by_id=current_user.id).
    7. Updates PhysicalFile (is_checked_out=False, storage_location_id=dest if changed).
    8. Creates immutable FileMovementHistory record.
    9. Logs audit event atomically.
    """
    # 1. Lock file row
    file_record = (
        db.query(PhysicalFile)
        .filter(PhysicalFile.id == physical_file_id)
        .with_for_update()
        .first()
    )
    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    # 2. Authorization
    auth_decision = custody_auth_service.can_checkin(current_user, file_record)
    if not auth_decision.allowed:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="physical_file.checkin",
            resource_type="physical_file",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=file_record.id,
            details={"reason": auth_decision.reason},
            raise_on_failure=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {auth_decision.reason}",
        )

    # 3. Confirm currently checked out
    if not file_record.is_checked_out:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Physical file is not currently checked out.",
        )

    # 4. Find active custody record
    custody_record = (
        db.query(FileCustodyRecord)
        .filter(
            FileCustodyRecord.physical_file_id == file_record.id,
            FileCustodyRecord.status == CustodyStatus.ACTIVE,
        )
        .with_for_update()
        .first()
    )
    if not custody_record:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active custody record found for this checked-out file.",
        )

    now = utc_now()

    # 5. Destination location determination & validation
    dest_location_id = payload.destination_location_id or file_record.storage_location_id
    dest_location = None
    if dest_location_id:
        dest_location = (
            db.query(StorageLocation)
            .filter(StorageLocation.id == dest_location_id)
            .with_for_update()
            .first()
        )
        if not dest_location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Destination storage location not found.",
            )
        if not dest_location.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Destination storage location '{dest_location.location_code}' is inactive.",
            )

        assign_decision = storage_location_auth_service.can_assign_file(current_user, file_record, dest_location)
        if not assign_decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cannot check in to destination location: {assign_decision.reason}",
            )

        # Capacity check if returning to a new/different location or enforcing capacity limit
        if dest_location.max_capacity is not None and dest_location_id != file_record.storage_location_id:
            curr_count = db.query(func.count(PhysicalFile.id)).filter(
                PhysicalFile.storage_location_id == dest_location.id
            ).scalar() or 0
            if curr_count >= dest_location.max_capacity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Destination storage location '{dest_location.location_code}' is at full capacity ({dest_location.max_capacity} items).",
                )

    dest_loc_code = dest_location.location_code if dest_location else None
    dest_loc_name = dest_location.name if dest_location else "Storage"

    # 6. Close custody record
    custody_record.status = CustodyStatus.RETURNED
    custody_record.checked_in_at = now
    custody_record.received_by_id = current_user.id
    if payload.checkin_notes:
        custody_record.checkin_notes = payload.checkin_notes.strip()

    # 7. Update physical file
    file_record.is_checked_out = False
    if dest_location_id:
        file_record.storage_location_id = dest_location_id
    file_record.updated_by_id = current_user.id
    file_record.updated_at = now

    # 8. Create Movement History Event
    movement_event = FileMovementHistory(
        physical_file_id=file_record.id,
        movement_type=PhysicalMovementType.CHECKIN,
        source_location_id=None,
        destination_location_id=dest_location_id,
        from_custody_state=f"Checked out to {custody_record.custodian_name}",
        to_custody_state=f"Stored in {dest_loc_code or dest_loc_name}",
        actor_id=current_user.id,
        event_at=now,
        reason=payload.checkin_notes.strip() if payload.checkin_notes else f"Returned by {custody_record.custodian_name}",
        custody_record_id=custody_record.id,
    )
    db.add(movement_event)

    # 9. Audit logging
    audit_service.log_from_request(
        db=db,
        request=request,
        action="physical_file.checkin",
        resource_type="physical_file",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=file_record.id,
        details={
            "file_reference": file_record.file_reference,
            "custody_record_id": str(custody_record.id),
            "custodian_name": custody_record.custodian_name,
            "destination_location_code": dest_loc_code,
            "notes": custody_record.checkin_notes,
        },
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(custody_record)

    issuer_info = None
    if custody_record.issued_by:
        issuer_info = UserShortInfo(
            id=custody_record.issued_by.id,
            email=custody_record.issued_by.email,
            full_name=custody_record.issued_by.full_name,
            department=custody_record.issued_by.department,
        )

    receiver_info = UserShortInfo(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        department=current_user.department,
    )

    return CustodyRecordResponse(
        id=custody_record.id,
        physical_file_id=custody_record.physical_file_id,
        file_reference=file_record.file_reference,
        file_title=file_record.title,
        custodian_user_id=custody_record.custodian_user_id,
        custodian_name=custody_record.custodian_name,
        custodian_department=custody_record.custodian_department,
        custodian_contact=custody_record.custodian_contact,
        status=custody_record.status,
        checked_out_at=custody_record.checked_out_at,
        expected_return_at=custody_record.expected_return_at,
        checked_in_at=custody_record.checked_in_at,
        purpose=custody_record.purpose,
        checkin_notes=custody_record.checkin_notes,
        issued_by_id=custody_record.issued_by_id,
        issued_by=issuer_info,
        received_by_id=custody_record.received_by_id,
        received_by=receiver_info,
        is_overdue=False,
        created_at=custody_record.created_at,
        updated_at=custody_record.updated_at,
    )


@router.post(
    "/{physical_file_id}/transfer",
    response_model=MovementHistoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Transfer physical file between locations",
    description="Transfers a physical file to an authorized destination storage location while preserving chronological movement history.",
)
def transfer_physical_file(
    physical_file_id: uuid.UUID,
    payload: FileTransferRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Physical transfer workflow:
    1. Lock file row with with_for_update().
    2. Reject transfer if file is currently checked out.
    3. Validate destination storage location:
       - Must exist and be active.
       - Enforce destination capacity with row-lock.
       - Check user permissions for source and destination locations.
    4. Enforce department boundaries.
    5. Update PhysicalFile.storage_location_id.
    6. Record immutable FileMovementHistory.
    7. Write mandatory audit event atomically.
    """
    file_record = (
        db.query(PhysicalFile)
        .filter(PhysicalFile.id == physical_file_id)
        .with_for_update()
        .first()
    )
    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    # 2. Check out policy: reject transfer if currently checked out
    if file_record.is_checked_out:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot transfer a physical file that is currently checked out. Check the file in first.",
        )

    if file_record.status != PhysicalFileStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transfer physical file in '{file_record.status.value}' status. Record must be active.",
        )

    source_location = file_record.storage_location

    # Lock destination location
    dest_location = (
        db.query(StorageLocation)
        .filter(StorageLocation.id == payload.destination_location_id)
        .with_for_update()
        .first()
    )
    if not dest_location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Destination storage location not found.",
        )

    if not dest_location.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Destination storage location '{dest_location.location_code}' is inactive.",
        )

    if source_location and source_location.id == dest_location.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and destination storage locations are the same.",
        )

    # 3. Validate transfer authorization
    transfer_decision = custody_auth_service.can_transfer(
        current_user, file_record, source_location, dest_location
    )
    if not transfer_decision.allowed:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="physical_file.transfer",
            resource_type="physical_file",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=file_record.id,
            details={"reason": transfer_decision.reason},
            raise_on_failure=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {transfer_decision.reason}",
        )

    # 4. Check destination capacity
    if dest_location.max_capacity is not None:
        curr_count = db.query(func.count(PhysicalFile.id)).filter(
            PhysicalFile.storage_location_id == dest_location.id
        ).scalar() or 0
        if curr_count >= dest_location.max_capacity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Destination storage location '{dest_location.location_code}' is at full capacity ({dest_location.max_capacity} items).",
            )

    now = utc_now()
    src_loc_code = source_location.location_code if source_location else "Unassigned"
    dest_loc_code = dest_location.location_code

    # 5. Create Movement History Event
    movement_event = FileMovementHistory(
        physical_file_id=file_record.id,
        movement_type=PhysicalMovementType.TRANSFER,
        source_location_id=file_record.storage_location_id,
        destination_location_id=dest_location.id,
        from_custody_state=f"Stored in {src_loc_code}",
        to_custody_state=f"Stored in {dest_loc_code}",
        actor_id=current_user.id,
        event_at=now,
        reason=payload.reason.strip(),
        custody_record_id=None,
    )
    db.add(movement_event)

    # 6. Update physical file location
    file_record.storage_location_id = dest_location.id
    file_record.updated_by_id = current_user.id
    file_record.updated_at = now

    # 7. Audit logging
    audit_service.log_from_request(
        db=db,
        request=request,
        action="physical_file.transfer",
        resource_type="physical_file",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=file_record.id,
        details={
            "file_reference": file_record.file_reference,
            "source_location_code": src_loc_code,
            "destination_location_code": dest_loc_code,
            "reason": payload.reason.strip(),
        },
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(movement_event)

    actor_info = UserShortInfo(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        department=current_user.department,
    )

    return MovementHistoryResponse(
        id=movement_event.id,
        physical_file_id=movement_event.physical_file_id,
        movement_type=movement_event.movement_type,
        source_location_id=movement_event.source_location_id,
        source_location_code=src_loc_code if source_location else None,
        source_location_name=source_location.name if source_location else None,
        destination_location_id=movement_event.destination_location_id,
        destination_location_code=dest_loc_code,
        destination_location_name=dest_location.name,
        from_custody_state=movement_event.from_custody_state,
        to_custody_state=movement_event.to_custody_state,
        actor_id=movement_event.actor_id,
        actor=actor_info,
        event_at=movement_event.event_at,
        reason=movement_event.reason,
        custody_record_id=None,
        created_at=movement_event.created_at,
    )


@router.get(
    "/{physical_file_id}/custody",
    response_model=CustodyRecordResponse | None,
    status_code=status.HTTP_200_OK,
    summary="Get current active custody record",
    description="Returns current active custody details for a physical file if checked out, or null if stored.",
)
def get_current_custody(
    physical_file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns current active custody record:
    - Verifies user authorization to view the physical file.
    - If checked out, calculates overdue indicator and returns detail.
    """
    file_record = db.query(PhysicalFile).filter(PhysicalFile.id == physical_file_id).first()
    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    auth_decision = custody_auth_service.can_view_history(current_user, file_record)
    if not auth_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    active_rec = (
        db.query(FileCustodyRecord)
        .filter(
            FileCustodyRecord.physical_file_id == file_record.id,
            FileCustodyRecord.status == CustodyStatus.ACTIVE,
        )
        .first()
    )
    if not active_rec:
        return None

    now = utc_now()
    is_overdue = bool(active_rec.expected_return_at and active_rec.expected_return_at < now)

    issuer_info = None
    if active_rec.issued_by:
        issuer_info = UserShortInfo(
            id=active_rec.issued_by.id,
            email=active_rec.issued_by.email,
            full_name=active_rec.issued_by.full_name,
            department=active_rec.issued_by.department,
        )

    return CustodyRecordResponse(
        id=active_rec.id,
        physical_file_id=active_rec.physical_file_id,
        file_reference=file_record.file_reference,
        file_title=file_record.title,
        custodian_user_id=active_rec.custodian_user_id,
        custodian_name=active_rec.custodian_name,
        custodian_department=active_rec.custodian_department,
        custodian_contact=active_rec.custodian_contact,
        status=active_rec.status,
        checked_out_at=active_rec.checked_out_at,
        expected_return_at=active_rec.expected_return_at,
        checked_in_at=active_rec.checked_in_at,
        purpose=active_rec.purpose,
        checkin_notes=active_rec.checkin_notes,
        issued_by_id=active_rec.issued_by_id,
        issued_by=issuer_info,
        received_by_id=None,
        received_by=None,
        is_overdue=is_overdue,
        created_at=active_rec.created_at,
        updated_at=active_rec.updated_at,
    )


@router.get(
    "/{physical_file_id}/custody-history",
    response_model=PaginatedCustodyRecordsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get custody records history",
    description="Returns chronological historical custody checkout and return records for a physical file.",
)
def get_custody_history(
    physical_file_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file_record = db.query(PhysicalFile).filter(PhysicalFile.id == physical_file_id).first()
    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    auth_decision = custody_auth_service.can_view_history(current_user, file_record)
    if not auth_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    query = db.query(FileCustodyRecord).filter(
        FileCustodyRecord.physical_file_id == file_record.id
    )

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    records = (
        query.order_by(desc(FileCustodyRecord.checked_out_at), desc(FileCustodyRecord.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    now = utc_now()
    items = []
    for r in records:
        issuer_info = None
        if r.issued_by:
            issuer_info = UserShortInfo(
                id=r.issued_by.id,
                email=r.issued_by.email,
                full_name=r.issued_by.full_name,
                department=r.issued_by.department,
            )
        receiver_info = None
        if r.received_by:
            receiver_info = UserShortInfo(
                id=r.received_by.id,
                email=r.received_by.email,
                full_name=r.received_by.full_name,
                department=r.received_by.department,
            )

        is_overdue = bool(r.status == CustodyStatus.ACTIVE and r.expected_return_at and r.expected_return_at < now)

        items.append(
            CustodyRecordResponse(
                id=r.id,
                physical_file_id=r.physical_file_id,
                file_reference=file_record.file_reference,
                file_title=file_record.title,
                custodian_user_id=r.custodian_user_id,
                custodian_name=r.custodian_name,
                custodian_department=r.custodian_department,
                custodian_contact=r.custodian_contact,
                status=r.status,
                checked_out_at=r.checked_out_at,
                expected_return_at=r.expected_return_at,
                checked_in_at=r.checked_in_at,
                purpose=r.purpose,
                checkin_notes=r.checkin_notes,
                issued_by_id=r.issued_by_id,
                issued_by=issuer_info,
                received_by_id=r.received_by_id,
                received_by=receiver_info,
                is_overdue=is_overdue,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )

    return PaginatedCustodyRecordsResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.get(
    "/{physical_file_id}/movement-history",
    response_model=PaginatedMovementHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get movement history",
    description="Returns chronological record of physical checkouts, returns, and transfers.",
)
def get_movement_history(
    physical_file_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file_record = db.query(PhysicalFile).filter(PhysicalFile.id == physical_file_id).first()
    if not file_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    auth_decision = custody_auth_service.can_view_history(current_user, file_record)
    if not auth_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Physical file not found.",
        )

    query = db.query(FileMovementHistory).filter(
        FileMovementHistory.physical_file_id == file_record.id
    )

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    records = (
        query.order_by(desc(FileMovementHistory.event_at), desc(FileMovementHistory.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for m in records:
        actor_info = None
        if m.actor:
            actor_info = UserShortInfo(
                id=m.actor.id,
                email=m.actor.email,
                full_name=m.actor.full_name,
                department=m.actor.department,
            )

        items.append(
            MovementHistoryResponse(
                id=m.id,
                physical_file_id=m.physical_file_id,
                movement_type=m.movement_type,
                source_location_id=m.source_location_id,
                source_location_code=m.source_location.location_code if m.source_location else None,
                source_location_name=m.source_location.name if m.source_location else None,
                destination_location_id=m.destination_location_id,
                destination_location_code=m.destination_location.location_code if m.destination_location else None,
                destination_location_name=m.destination_location.name if m.destination_location else None,
                from_custody_state=m.from_custody_state,
                to_custody_state=m.to_custody_state,
                actor_id=m.actor_id,
                actor=actor_info,
                event_at=m.event_at,
                reason=m.reason,
                custody_record_id=m.custody_record_id,
                created_at=m.created_at,
            )
        )

    return PaginatedMovementHistoryResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )

