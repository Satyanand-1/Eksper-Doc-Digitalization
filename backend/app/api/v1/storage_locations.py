"""
Storage Locations API Router.
Endpoints for creating, listing, viewing, updating, activating/deactivating
hierarchical storage locations and viewing their direct contents.
"""
import uuid
import math
import logging
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy import desc, asc, func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.physical_file import PhysicalFile
from app.models.storage_location import StorageLocation, LocationType, utc_now
from app.models.audit import AuditOutcome
from app.schemas.storage_location import (
    StorageLocationCreateRequest,
    StorageLocationUpdateRequest,
    StorageLocationStatusRequest,
    StorageLocationSummaryResponse,
    StorageLocationDetailResponse,
    PaginatedStorageLocationsResponse,
    StorageLocationBreadcrumb,
    LocationUserShortInfo,
)
from app.schemas.physical_file import PhysicalFileSummaryResponse, PaginatedPhysicalFilesResponse
from app.services.authorization import (
    storage_location_auth_service,
    physical_file_auth_service,
)
from app.services.location_service import (
    get_location_path,
    get_location_breadcrumbs,
    validate_parent_child_hierarchy,
)
from app.services.audit import audit_service

logger = logging.getLogger("edrms.storage_locations")

router = APIRouter(prefix="/api/v1/storage-locations", tags=["Storage Locations"])


@router.post(
    "",
    response_model=StorageLocationDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a storage location",
    description="Creates a new storage location in the organizational hierarchy.",
)
def create_storage_location(
    payload: StorageLocationCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create storage location:
    1. Authenticate user and check can_manage permissions for payload.department.
    2. Check uniqueness of location_code.
    3. Validate parent existence and parent-child hierarchy rules if parent_id provided.
    4. Save location, write mandatory audit event, and return detail response.
    """
    clean_dept = payload.department.strip()
    clean_code = payload.location_code.strip().upper()
    clean_name = payload.name.strip()

    # 1. Authorization check
    auth_decision = storage_location_auth_service.can_manage(current_user, clean_dept)
    if not auth_decision.allowed:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="storage_location.create",
            resource_type="storage_location",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            details={"reason": auth_decision.reason, "department": clean_dept},
            raise_on_failure=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {auth_decision.reason}",
        )

    # 2. Check code uniqueness
    existing_code = db.query(StorageLocation.id).filter(
        StorageLocation.location_code == clean_code
    ).first()
    if existing_code:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A storage location with code '{clean_code}' already exists.",
        )

    # 3. Validate parent if provided
    parent = None
    if payload.parent_id:
        parent = db.query(StorageLocation).filter(StorageLocation.id == payload.parent_id).first()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Specified parent storage location does not exist.",
            )
        if not parent.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create child locations under an inactive parent location.",
            )
        # Check parent visibility/manage authorization
        parent_view_decision = storage_location_auth_service.can_view(current_user, parent)
        if not parent_view_decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to the specified parent storage location.",
            )

        try:
            validate_parent_child_hierarchy(db, payload.location_type, parent, current_location_id=None)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(err),
            )

    # 4. Instantiate and commit location
    location = StorageLocation(
        location_code=clean_code,
        name=clean_name,
        location_type=payload.location_type,
        description=payload.description.strip() if payload.description else None,
        department=clean_dept,
        parent_id=payload.parent_id,
        max_capacity=payload.max_capacity,
        is_active=True,
        created_by_id=current_user.id,
    )
    db.add(location)
    db.flush()

    loc_path = get_location_path(db, location)

    # Mandatory Audit Logging
    audit_service.log_from_request(
        db=db,
        request=request,
        action="storage_location.create",
        resource_type="storage_location",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=location.id,
        details={
            "location_code": location.location_code,
            "name": location.name,
            "location_type": location.location_type.value,
            "department": location.department,
            "parent_id": str(location.parent_id) if location.parent_id else None,
            "location_path": loc_path,
        },
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(location)

    breadcrumbs = [StorageLocationBreadcrumb(**b) for b in get_location_breadcrumbs(db, location)]

    return StorageLocationDetailResponse(
        id=location.id,
        location_code=location.location_code,
        name=location.name,
        location_type=location.location_type,
        description=location.description,
        department=location.department,
        parent_id=location.parent_id,
        parent=None,
        is_active=location.is_active,
        max_capacity=location.max_capacity,
        direct_file_count=0,
        child_count=0,
        location_path=loc_path,
        breadcrumbs=breadcrumbs,
        created_by_id=location.created_by_id,
        created_by=LocationUserShortInfo(
            id=current_user.id,
            email=current_user.email,
            full_name=current_user.full_name,
            department=current_user.department,
        ),
        updated_by_id=None,
        updated_by=None,
        created_at=location.created_at,
        updated_at=location.updated_at,
    )


@router.get(
    "",
    response_model=PaginatedStorageLocationsResponse,
    status_code=status.HTTP_200_OK,
    summary="List storage locations",
    description="Returns authorized storage locations with search and filtering.",
)
def list_storage_locations(
    request: Request,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 50,
    search: Annotated[str | None, Query(max_length=100, description="Search by code or name")] = None,
    department: Annotated[str | None, Query(max_length=100, description="Department filter")] = None,
    location_type: Annotated[LocationType | None, Query(description="Location type filter")] = None,
    parent_id: Annotated[uuid.UUID | None, Query(description="Filter by parent location (pass 'null' string isn't allowed, use top_level=true)")] = None,
    top_level: Annotated[bool | None, Query(description="Filter top-level locations only (parent_id is null)")] = None,
    is_active: Annotated[bool | None, Query(description="Active/inactive filter")] = None,
    sort_by: Annotated[Literal["name", "location_code", "created_at"], Query(description="Sort field")] = "name",
    sort_order: Annotated[Literal["asc", "desc"], Query(description="Sort direction")] = "asc",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List storage locations with SQL-level scoping and pagination.
    """
    auth_scope = storage_location_auth_service.build_storage_location_scope_filter(current_user)
    query = db.query(StorageLocation).filter(auth_scope)

    if search:
        search_term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                StorageLocation.location_code.ilike(search_term),
                StorageLocation.name.ilike(search_term),
            )
        )

    if department:
        query = query.filter(func.lower(StorageLocation.department) == department.strip().lower())

    if location_type:
        query = query.filter(StorageLocation.location_type == location_type)

    if top_level is True:
        query = query.filter(StorageLocation.parent_id.is_(None))
    elif parent_id:
        query = query.filter(StorageLocation.parent_id == parent_id)

    if is_active is not None:
        query = query.filter(StorageLocation.is_active == is_active)

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    sort_col = getattr(StorageLocation, sort_by, StorageLocation.name)
    order_func = desc if sort_order == "desc" else asc
    query = query.order_by(order_func(sort_col), asc(StorageLocation.id))

    records = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for r in records:
        direct_files = db.query(func.count(PhysicalFile.id)).filter(
            PhysicalFile.storage_location_id == r.id
        ).scalar() or 0
        children = db.query(func.count(StorageLocation.id)).filter(
            StorageLocation.parent_id == r.id
        ).scalar() or 0
        path = get_location_path(db, r)

        items.append(
            StorageLocationSummaryResponse(
                id=r.id,
                location_code=r.location_code,
                name=r.name,
                location_type=r.location_type,
                department=r.department,
                parent_id=r.parent_id,
                is_active=r.is_active,
                max_capacity=r.max_capacity,
                direct_file_count=direct_files,
                child_count=children,
                location_path=path,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )

    return PaginatedStorageLocationsResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.get(
    "/{location_id}",
    response_model=StorageLocationDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get storage location details",
    description="Returns detailed metadata and hierarchy path of an authorized storage location.",
)
def get_storage_location(
    location_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get storage location details:
    Returns non-disclosing 404 if not found or unauthorized.
    """
    loc = db.query(StorageLocation).filter(StorageLocation.id == location_id).first()
    if not loc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage location not found.",
        )

    auth_decision = storage_location_auth_service.can_view(current_user, loc)
    if not auth_decision.allowed:
        audit_service.log_from_request(
            db=db,
            request=request,
            action="storage_location.view",
            resource_type="storage_location",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=location_id,
            details={"reason": auth_decision.reason},
            raise_on_failure=True,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage location not found.",
        )

    direct_files = db.query(func.count(PhysicalFile.id)).filter(
        PhysicalFile.storage_location_id == loc.id
    ).scalar() or 0
    children = db.query(func.count(StorageLocation.id)).filter(
        StorageLocation.parent_id == loc.id
    ).scalar() or 0
    path = get_location_path(db, loc)
    breadcrumbs = [StorageLocationBreadcrumb(**b) for b in get_location_breadcrumbs(db, loc)]

    parent_summary = None
    if loc.parent:
        parent_summary = StorageLocationSummaryResponse(
            id=loc.parent.id,
            location_code=loc.parent.location_code,
            name=loc.parent.name,
            location_type=loc.parent.location_type,
            department=loc.parent.department,
            parent_id=loc.parent.parent_id,
            is_active=loc.parent.is_active,
            max_capacity=loc.parent.max_capacity,
            direct_file_count=0,
            child_count=0,
            location_path="",
            created_at=loc.parent.created_at,
            updated_at=loc.parent.updated_at,
        )

    creator_info = None
    if loc.created_by:
        creator_info = LocationUserShortInfo(
            id=loc.created_by.id,
            email=loc.created_by.email,
            full_name=loc.created_by.full_name,
            department=loc.created_by.department,
        )

    updater_info = None
    if loc.updated_by:
        updater_info = LocationUserShortInfo(
            id=loc.updated_by.id,
            email=loc.updated_by.email,
            full_name=loc.updated_by.full_name,
            department=loc.updated_by.department,
        )

    return StorageLocationDetailResponse(
        id=loc.id,
        location_code=loc.location_code,
        name=loc.name,
        location_type=loc.location_type,
        description=loc.description,
        department=loc.department,
        parent_id=loc.parent_id,
        parent=parent_summary,
        is_active=loc.is_active,
        max_capacity=loc.max_capacity,
        direct_file_count=direct_files,
        child_count=children,
        location_path=path,
        breadcrumbs=breadcrumbs,
        created_by_id=loc.created_by_id,
        created_by=creator_info,
        updated_by_id=loc.updated_by_id,
        updated_by=updater_info,
        created_at=loc.created_at,
        updated_at=loc.updated_at,
    )


@router.patch(
    "/{location_id}",
    response_model=StorageLocationDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Update storage location",
    description="Updates permitted metadata, maximum capacity, or parent hierarchy node.",
)
def update_storage_location(
    location_id: uuid.UUID,
    payload: StorageLocationUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update storage location:
    1. Authenticate user and verify can_manage for location.
    2. Check department reassignment rules (Admin/Records Officer only).
    3. Validate parent relationship changes:
       - Prevent self-parenting
       - Prevent cycle / descendant parenting
       - Check permitted parent-child location types
    4. Enforce capacity consistency if capacity is updated.
    5. Save, audit, and return detail response.
    """
    loc = db.query(StorageLocation).filter(StorageLocation.id == location_id).first()
    if not loc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage location not found.",
        )

    new_dept = payload.department.strip() if payload.department is not None else loc.department
    auth_decision = storage_location_auth_service.can_manage(current_user, new_dept)
    if not auth_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {auth_decision.reason}",
        )

    changes: dict = {}

    if payload.name is not None and payload.name.strip() != loc.name:
        clean_name = payload.name.strip()
        changes["name"] = {"old": loc.name, "new": clean_name}
        loc.name = clean_name

    if payload.description is not None:
        clean_desc = payload.description.strip() if payload.description else None
        if clean_desc != loc.description:
            changes["description"] = "updated"
            loc.description = clean_desc

    if payload.location_type is not None and payload.location_type != loc.location_type:
        # Check hierarchy type with current parent
        if loc.parent:
            try:
                validate_parent_child_hierarchy(db, payload.location_type, loc.parent, current_location_id=loc.id)
            except ValueError as err:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(err),
                )
        changes["location_type"] = {"old": loc.location_type.value, "new": payload.location_type.value}
        loc.location_type = payload.location_type

    if payload.clear_max_capacity:
        if loc.max_capacity is not None:
            changes["max_capacity"] = {"old": loc.max_capacity, "new": None}
            loc.max_capacity = None
    elif payload.max_capacity is not None and payload.max_capacity != loc.max_capacity:
        # Check if new capacity is smaller than existing file count
        existing_count = db.query(func.count(PhysicalFile.id)).filter(
            PhysicalFile.storage_location_id == loc.id
        ).scalar() or 0
        if payload.max_capacity < existing_count:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot reduce capacity to {payload.max_capacity}; location already holds {existing_count} physical files.",
            )
        changes["max_capacity"] = {"old": loc.max_capacity, "new": payload.max_capacity}
        loc.max_capacity = payload.max_capacity

    # Parent relationship update
    if payload.clear_parent:
        if loc.parent_id is not None:
            changes["parent_id"] = {"old": str(loc.parent_id), "new": None}
            loc.parent_id = None
    elif payload.parent_id is not None and payload.parent_id != loc.parent_id:
        parent = db.query(StorageLocation).filter(StorageLocation.id == payload.parent_id).first()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target parent storage location does not exist.",
            )
        if not parent.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot move storage location under an inactive parent.",
            )

        try:
            validate_parent_child_hierarchy(db, loc.location_type, parent, current_location_id=loc.id)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(err),
            )

        changes["parent_id"] = {"old": str(loc.parent_id) if loc.parent_id else None, "new": str(payload.parent_id)}
        loc.parent_id = payload.parent_id

    # Department update (Admin/Records Officer only)
    if payload.department is not None and payload.department.strip() != loc.department:
        if current_user.role not in (UserRole.ADMIN, UserRole.RECORDS_OFFICER):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators and records officers can reassign storage location department ownership.",
            )
        changes["department"] = {"old": loc.department, "new": new_dept}
        loc.department = new_dept

    loc.updated_by_id = current_user.id
    loc.updated_at = utc_now()

    audit_service.log_from_request(
        db=db,
        request=request,
        action="storage_location.update",
        resource_type="storage_location",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=loc.id,
        details={
            "location_code": loc.location_code,
            "changes": changes,
        },
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(loc)

    direct_files = db.query(func.count(PhysicalFile.id)).filter(
        PhysicalFile.storage_location_id == loc.id
    ).scalar() or 0
    children = db.query(func.count(StorageLocation.id)).filter(
        StorageLocation.parent_id == loc.id
    ).scalar() or 0
    path = get_location_path(db, loc)
    breadcrumbs = [StorageLocationBreadcrumb(**b) for b in get_location_breadcrumbs(db, loc)]

    return StorageLocationDetailResponse(
        id=loc.id,
        location_code=loc.location_code,
        name=loc.name,
        location_type=loc.location_type,
        description=loc.description,
        department=loc.department,
        parent_id=loc.parent_id,
        parent=None,
        is_active=loc.is_active,
        max_capacity=loc.max_capacity,
        direct_file_count=direct_files,
        child_count=children,
        location_path=path,
        breadcrumbs=breadcrumbs,
        created_by_id=loc.created_by_id,
        created_by=None,
        updated_by_id=loc.updated_by_id,
        updated_by=LocationUserShortInfo(
            id=current_user.id,
            email=current_user.email,
            full_name=current_user.full_name,
            department=current_user.department,
        ),
        created_at=loc.created_at,
        updated_at=loc.updated_at,
    )


@router.patch(
    "/{location_id}/status",
    response_model=StorageLocationDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Activate or deactivate storage location",
    description="Changes storage location status with safety checks against deactivating locations holding files or active children.",
)
def change_storage_location_status(
    location_id: uuid.UUID,
    payload: StorageLocationStatusRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Activate/Deactivate storage location:
    Safety checks:
    - If deactivating: cannot deactivate if location contains direct files or active child locations.
    """
    loc = db.query(StorageLocation).filter(StorageLocation.id == location_id).first()
    if not loc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage location not found.",
        )

    auth_decision = storage_location_auth_service.can_manage(current_user, loc.department)
    if not auth_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: {auth_decision.reason}",
        )

    if loc.is_active == payload.is_active:
        pass
    else:
        if payload.is_active is False:
            # Check for direct files
            direct_files_count = db.query(func.count(PhysicalFile.id)).filter(
                PhysicalFile.storage_location_id == loc.id
            ).scalar() or 0
            if direct_files_count > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot deactivate storage location: {direct_files_count} physical file(s) are currently stored here. Reassign or remove them first.",
                )

            # Check for active child locations
            active_children_count = db.query(func.count(StorageLocation.id)).filter(
                StorageLocation.parent_id == loc.id,
                StorageLocation.is_active.is_(True),
            ).scalar() or 0
            if active_children_count > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot deactivate storage location: {active_children_count} active child location(s) exist under it. Deactivate or reassign them first.",
                )

        loc.is_active = payload.is_active
        loc.updated_by_id = current_user.id
        loc.updated_at = utc_now()

    audit_service.log_from_request(
        db=db,
        request=request,
        action="storage_location.status_change",
        resource_type="storage_location",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=loc.id,
        details={
            "location_code": loc.location_code,
            "is_active": loc.is_active,
            "reason": payload.reason,
        },
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(loc)

    path = get_location_path(db, loc)
    breadcrumbs = [StorageLocationBreadcrumb(**b) for b in get_location_breadcrumbs(db, loc)]

    return StorageLocationDetailResponse(
        id=loc.id,
        location_code=loc.location_code,
        name=loc.name,
        location_type=loc.location_type,
        description=loc.description,
        department=loc.department,
        parent_id=loc.parent_id,
        parent=None,
        is_active=loc.is_active,
        max_capacity=loc.max_capacity,
        direct_file_count=0,
        child_count=0,
        location_path=path,
        breadcrumbs=breadcrumbs,
        created_by_id=loc.created_by_id,
        created_by=None,
        updated_by_id=loc.updated_by_id,
        updated_by=LocationUserShortInfo(
            id=current_user.id,
            email=current_user.email,
            full_name=current_user.full_name,
            department=current_user.department,
        ),
        created_at=loc.created_at,
        updated_at=loc.updated_at,
    )


@router.get(
    "/{location_id}/children",
    response_model=list[StorageLocationSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="Get child storage locations",
    description="Returns authorized immediate child locations.",
)
def get_child_locations(
    location_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get immediate child locations:
    Returns list of direct children scoped to user's permissions.
    """
    parent = db.query(StorageLocation).filter(StorageLocation.id == location_id).first()
    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage location not found.",
        )

    auth_decision = storage_location_auth_service.can_view(current_user, parent)
    if not auth_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage location not found.",
        )

    auth_scope = storage_location_auth_service.build_storage_location_scope_filter(current_user)
    children = db.query(StorageLocation).filter(
        StorageLocation.parent_id == location_id,
        auth_scope,
    ).order_by(asc(StorageLocation.name)).all()

    items = []
    for c in children:
        direct_files = db.query(func.count(PhysicalFile.id)).filter(
            PhysicalFile.storage_location_id == c.id
        ).scalar() or 0
        grand_children = db.query(func.count(StorageLocation.id)).filter(
            StorageLocation.parent_id == c.id
        ).scalar() or 0
        path = get_location_path(db, c)
        items.append(
            StorageLocationSummaryResponse(
                id=c.id,
                location_code=c.location_code,
                name=c.name,
                location_type=c.location_type,
                department=c.department,
                parent_id=c.parent_id,
                is_active=c.is_active,
                max_capacity=c.max_capacity,
                direct_file_count=direct_files,
                child_count=grand_children,
                location_path=path,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
        )
    return items


@router.get(
    "/{location_id}/contents",
    response_model=PaginatedPhysicalFilesResponse,
    status_code=status.HTTP_200_OK,
    summary="List physical files in location",
    description="Returns authorized physical files currently assigned directly to this storage location with SQL pagination.",
)
def get_location_contents(
    location_id: uuid.UUID,
    request: Request,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List physical files stored directly in this location.
    Enforces file-level authorization filter so unauthorized files are never leaked.
    """
    loc = db.query(StorageLocation).filter(StorageLocation.id == location_id).first()
    if not loc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage location not found.",
        )

    auth_decision = storage_location_auth_service.can_view(current_user, loc)
    if not auth_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage location not found.",
        )

    file_auth_scope = physical_file_auth_service.build_physical_file_scope_filter(current_user)
    query = db.query(PhysicalFile).filter(
        PhysicalFile.storage_location_id == location_id,
        file_auth_scope,
    )

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    records = query.order_by(desc(PhysicalFile.created_at)).offset((page - 1) * page_size).limit(page_size).all()

    loc_path = get_location_path(db, loc)

    items = [
        PhysicalFileSummaryResponse(
            id=r.id,
            file_reference=r.file_reference,
            title=r.title,
            record_type=r.record_type,
            department=r.department,
            classification=r.classification,
            status=r.status,
            has_digital_document=r.digital_document_id is not None,
            storage_location_id=loc.id,
            storage_location_name=loc.name,
            storage_location_code=loc.location_code,
            location_path=loc_path,
            external_reference=r.external_reference,
            date_received=r.date_received,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in records
    ]

    return PaginatedPhysicalFilesResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )
