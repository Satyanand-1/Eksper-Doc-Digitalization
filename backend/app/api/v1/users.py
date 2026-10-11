"""
Users API router for EDRMS.
Task 5.9: Secure Approver Directory and Selection.
Task 5.10: User Administration and Role Management.
"""
import uuid
import math
import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.document import DigitalDocument
from app.models.audit import AuditOutcome
from app.services.audit import AuditService, AuditWriteError
from app.security import hash_password
from app.schemas.user import (
    EligibleApproverResponse,
    AdminUserResponse,
    PaginatedUsersResponse,
    UserCreateRequest,
    UserUpdateRequest,
    UserStatusUpdateRequest,
)
from app.services.authorization import document_auth_service

logger = logging.getLogger("edrms.users")

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


@router.get(
    "/eligible-approvers",
    response_model=list[EligibleApproverResponse],
    status_code=status.HTTP_200_OK,
    summary="List eligible approvers for document review",
    description="Returns active approvers scoped to the authenticated user's department or specified document context.",
)
def get_eligible_approvers(
    request: Request,
    document_id: Annotated[uuid.UUID | None, Query(description="Optional target document UUID to scope approvers to document department")] = None,
    department: Annotated[str | None, Query(max_length=100, description="Optional department filter (Admin / Records Officer only)")] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=50, description="Optional search term across approver name and email")] = None,
    limit: Annotated[int, Query(ge=1, le=50, description="Maximum results to return (1-50)")] = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Secure Approver Directory Endpoint:
    - Requires active authenticated user.
    - Department Users: Strictly scoped to active approvers in their own department (or document's department if document_id given).
    - Admins & Records Officers: Scoped to document department if document_id given, or optional department filter, or across departments.
    - Auditors, Read-Only users, and Approvers: Access denied (default-deny).
    - Excludes inactive users, non-approvers, and the submitter themselves.
    - Strictly returns safe display attributes (UUID, email, full_name, department).
    - Filters in SQL with deterministic ordering and bounded limits.
    """
    # 1. Role-based access control (default-deny)
    allowed_roles = {UserRole.DEPARTMENT_USER, UserRole.ADMIN, UserRole.RECORDS_OFFICER}
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{current_user.role.value}' is not permitted to query the approver directory.",
        )

    target_department: str | None = None

    # 2. Document-aware evaluation
    if document_id is not None:
        doc = db.query(DigitalDocument).filter(DigitalDocument.id == document_id).first()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID {document_id} not found.",
            )

        # Check document-level access to prevent document enumeration
        view_decision = document_auth_service.can_view_metadata(current_user, doc)
        if not view_decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID {document_id} not found.",
            )

        # Department User scope check: must belong to document department
        if current_user.role == UserRole.DEPARTMENT_USER:
            user_dept = (current_user.department or "").strip().lower()
            doc_dept = (doc.department or "").strip().lower()
            if not user_dept or user_dept != doc_dept:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Department user in '{current_user.department}' cannot query approvers for '{doc.department}' documents.",
                )

        target_department = doc.department
    else:
        # No document_id supplied: scope by user role and department
        if current_user.role == UserRole.DEPARTMENT_USER:
            user_dept = (current_user.department or "").strip()
            if not user_dept:
                # Missing department fails safely
                return []
            target_department = user_dept
        elif current_user.role in {UserRole.ADMIN, UserRole.RECORDS_OFFICER}:
            if department and department.strip():
                target_department = department.strip()

    # 3. Build SQL query with strict filters
    query = db.query(User).filter(
        User.is_active == True,
        User.role == UserRole.APPROVER,
        User.id != current_user.id,  # Submitter cannot be assigned as approver
    )

    if target_department:
        dept_approvers_count = db.query(User).filter(
            User.is_active == True,
            User.role == UserRole.APPROVER,
            func.lower(User.department) == target_department.strip().lower(),
            User.id != current_user.id
        ).count()
        if dept_approvers_count > 0:
            query = query.filter(func.lower(User.department) == target_department.strip().lower())
        else:
            central_depts = ["records & compliance", "system administration"]
            query = query.filter(
                or_(
                    func.lower(User.department) == target_department.strip().lower(),
                    func.lower(User.department).in_(central_depts)
                )
            )
    else:
        # If no department resolved (e.g. admin without filter), ensure user has a non-null department
        query = query.filter(User.department.isnot(None), User.department != "")

    # 4. Search filtering
    if q and q.strip():
        search_pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                User.full_name.ilike(search_pattern),
                User.email.ilike(search_pattern),
            )
        )

    # 5. Deterministic ordering and bounded limit
    approvers = (
        query.order_by(User.full_name.asc(), User.email.asc(), User.id.asc())
        .limit(limit)
        .all()
    )

    return [
        EligibleApproverResponse(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            department=u.department or "",
        )
        for u in approvers
    ]


# ---------------------------------------------------------------------------
# Task 5.10: User Administration Endpoints (Admin Only)
# ---------------------------------------------------------------------------

DEPARTMENT_REQUIRED_ROLES = {
    UserRole.DEPARTMENT_USER,
    UserRole.APPROVER,
    UserRole.AUDITOR,
    UserRole.READ_ONLY,
}


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency enforcing that only active administrators can access admin endpoints."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required to perform this action.",
        )
    return current_user


@router.get(
    "",
    response_model=PaginatedUsersResponse,
    status_code=status.HTTP_200_OK,
    summary="List users (Admin only)",
    description="Administrator-only endpoint with SQL-level pagination, search, and filtering.",
)
def list_users(
    request: Request,
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size limit (1-100)")] = 20,
    search: Annotated[str | None, Query(max_length=100, description="Search term matching full name or email")] = None,
    role: Annotated[UserRole | None, Query(description="Filter by role")] = None,
    department: Annotated[str | None, Query(max_length=100, description="Filter by department")] = None,
    is_active: Annotated[bool | None, Query(description="Filter by active status")] = None,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    List users with SQL-level pagination and filtering.
    Restricted strictly to administrators.
    """
    query = db.query(User)

    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    if role is not None:
        query = query.filter(User.role == role)

    if department is not None and department.strip():
        query = query.filter(func.lower(User.department) == department.strip().lower())

    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                User.full_name.ilike(pattern),
                User.email.ilike(pattern),
            )
        )

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    users = (
        query.order_by(User.full_name.asc(), User.email.asc(), User.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaginatedUsersResponse(
        items=[AdminUserResponse.model_validate(u) for u in users],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post(
    "",
    response_model=AdminUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (Admin only)",
    description="Creates a new user account with Argon2id-hashed initial credentials.",
)
def create_user(
    request: Request,
    payload: UserCreateRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Create a user account:
    - Normalizes and verifies unique email.
    - Requires department for roles where departmental scope is mandatory.
    - Hashes initial password with Argon2id.
    - Logs mandatory audit event.
    - Never returns password or password hash.
    """
    normalized_email = payload.email.strip().lower()

    # Check for duplicate email
    existing = db.query(User).filter(User.email == normalized_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email '{normalized_email}' already exists.",
        )

    # Department validation based on role
    dept_val = payload.department.strip() if payload.department else None
    if payload.role in DEPARTMENT_REQUIRED_ROLES and not dept_val:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Department is required for users with role '{payload.role.value}'.",
        )

    # Hash password safely
    try:
        hashed = hash_password(payload.password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    new_user = User(
        email=normalized_email,
        full_name=payload.full_name.strip(),
        hashed_password=hashed,
        department=dept_val,
        role=payload.role,
        is_active=True,
    )

    try:
        db.add(new_user)
        db.flush()  # Generate new_user.id

        # Mandatory audit logging
        AuditService.log_from_request(
            db=db,
            request=request,
            action="user.create",
            resource_type="user",
            outcome=AuditOutcome.SUCCESS,
            actor_id=admin_user.id,
            resource_id=new_user.id,
            details={
                "email": new_user.email,
                "role": new_user.role.value,
                "department": new_user.department,
            },
            raise_on_failure=True,
        )

        db.commit()
        db.refresh(new_user)
        logger.info(f"User created: {new_user.id} ({new_user.email}) by admin {admin_user.id}")
        return AdminUserResponse.model_validate(new_user)
    except AuditWriteError as e:
        db.rollback()
        logger.error(f"Failed to record mandatory audit log on user creation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record mandatory audit log for user creation.",
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating user account.",
        )


@router.patch(
    "/{user_id}",
    response_model=AdminUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update user details (Admin only)",
    description="Updates approved profile fields (full name, department, role).",
)
def update_user(
    request: Request,
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Update user profile details:
    - Validates target user existence.
    - Validates role and department compatibility.
    - Prevents demoting the last active administrator with row-level locks.
    - Records mandatory audit log.
    """
    # Use row-level lock to prevent concurrent modifications
    target_user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found.",
        )

    # Determine final role and department
    new_role = payload.role if payload.role is not None else target_user.role
    new_dept = (
        payload.department.strip() if payload.department is not None else target_user.department
    )
    if new_dept == "":
        new_dept = None

    # Check department requirement for the target role
    if new_role in DEPARTMENT_REQUIRED_ROLES and not new_dept:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Department is required for users with role '{new_role.value}'.",
        )

    # Last active administrator safeguard:
    # If target user was ADMIN and is being demoted to another role:
    if target_user.role == UserRole.ADMIN and new_role != UserRole.ADMIN:
        if target_user.is_active:
            # Lock and count other active admins
            other_active_admins = (
                db.query(User)
                .filter(
                    User.role == UserRole.ADMIN,
                    User.is_active == True,
                    User.id != target_user.id,
                )
                .with_for_update()
                .all()
            )
            if len(other_active_admins) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot change role of the last active administrator.",
                )

    # Record what changes occurred for audit log
    changes: dict[str, dict[str, str | None]] = {}

    if payload.full_name is not None and payload.full_name.strip() != target_user.full_name:
        changes["full_name"] = {
            "old": target_user.full_name,
            "new": payload.full_name.strip(),
        }
        target_user.full_name = payload.full_name.strip()

    if payload.department is not None and new_dept != target_user.department:
        changes["department"] = {
            "old": target_user.department,
            "new": new_dept,
        }
        target_user.department = new_dept

    if payload.role is not None and payload.role != target_user.role:
        changes["role"] = {
            "old": target_user.role.value,
            "new": payload.role.value,
        }
        target_user.role = payload.role

    if not changes:
        return AdminUserResponse.model_validate(target_user)

    try:
        db.flush()

        AuditService.log_from_request(
            db=db,
            request=request,
            action="user.update",
            resource_type="user",
            outcome=AuditOutcome.SUCCESS,
            actor_id=admin_user.id,
            resource_id=target_user.id,
            details={"changes": changes},
            raise_on_failure=True,
        )

        db.commit()
        db.refresh(target_user)
        logger.info(f"User {target_user.id} updated by admin {admin_user.id}: {changes}")
        return AdminUserResponse.model_validate(target_user)
    except AuditWriteError as e:
        db.rollback()
        logger.error(f"Failed to record mandatory audit log on user update: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record mandatory audit log for user update.",
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating user account.",
        )


@router.patch(
    "/{user_id}/status",
    response_model=AdminUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Activate or deactivate a user (Admin only)",
    description="Updates the is_active status flag with last-administrator and self-lockout safeguards.",
)
def update_user_status(
    request: Request,
    user_id: uuid.UUID,
    payload: UserStatusUpdateRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Activate or deactivate a user account:
    - Self-deactivation prevention: An admin cannot deactivate their own account.
    - Last-administrator safeguard: The last active administrator cannot be deactivated.
    - Records mandatory audit log with transaction integrity.
    """
    # 1. Self-deactivation prevention
    if user_id == admin_user.id and not payload.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot deactivate their own account.",
        )

    # 2. Lock target user row
    target_user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found.",
        )

    # If status is not changing, return idempotently
    if target_user.is_active == payload.is_active:
        return AdminUserResponse.model_validate(target_user)

    # 3. Last-administrator safeguard on deactivation
    if not payload.is_active and target_user.role == UserRole.ADMIN:
        other_active_admins = (
            db.query(User)
            .filter(
                User.role == UserRole.ADMIN,
                User.is_active == True,
                User.id != target_user.id,
            )
            .with_for_update()
            .all()
        )
        if len(other_active_admins) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last active administrator.",
            )

    old_status = target_user.is_active
    target_user.is_active = payload.is_active
    action_name = "user.activate" if payload.is_active else "user.deactivate"

    try:
        db.flush()

        AuditService.log_from_request(
            db=db,
            request=request,
            action=action_name,
            resource_type="user",
            outcome=AuditOutcome.SUCCESS,
            actor_id=admin_user.id,
            resource_id=target_user.id,
            details={
                "email": target_user.email,
                "old_status": old_status,
                "new_status": payload.is_active,
            },
            raise_on_failure=True,
        )

        db.commit()
        db.refresh(target_user)
        logger.info(f"User {target_user.id} status changed to {payload.is_active} by admin {admin_user.id}")
        return AdminUserResponse.model_validate(target_user)
    except AuditWriteError as e:
        db.rollback()
        logger.error(f"Failed to record mandatory audit log on user status update: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record mandatory audit log for {action_name}.",
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating user status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating user status.",
        )
