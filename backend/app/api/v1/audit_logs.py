"""
Audit Logs API router for EDRMS.
Task 5.11: Audit Log Viewer and Administrative Reports.
"""
import uuid
import math
import logging
from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.audit import AuditLog, AuditOutcome
from app.schemas.audit import (
    AuditLogSummaryResponse,
    AuditLogDetailResponse,
    PaginatedAuditLogsResponse,
    AuditReportSummaryResponse,
    AuditActorInfo,
)

logger = logging.getLogger("edrms.audit_logs")

router = APIRouter(prefix="/api/v1/audit-logs", tags=["Audit Logs"])


def require_audit_viewer_role(current_user: User = Depends(get_current_user)) -> User:
    """
    Authorization policy for Audit Log Viewer:
    - Administrator (`admin`): Full administrative audit access.
    - Records Officer (`records_officer`): Records governance audit access.
    - All other roles: Strictly DENIED with HTTP 403 Forbidden.
    """
    allowed_roles = {UserRole.ADMIN, UserRole.RECORDS_OFFICER}
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{current_user.role.value}' is not authorized to inspect audit logs.",
        )
    return current_user


def _build_safe_actor_info(actor: User | None) -> AuditActorInfo | None:
    if not actor:
        return None
    return AuditActorInfo(
        id=actor.id,
        email=actor.email,
        full_name=actor.full_name,
        department=actor.department,
        role=actor.role.value if hasattr(actor.role, "value") else str(actor.role),
    )


def _sanitize_details(details: dict | None) -> dict | None:
    """
    Field-level sanitization on detail payloads.
    Ensures passwords, hashes, secret tokens, and raw filesystem keys are excluded.
    """
    if not details or not isinstance(details, dict):
        return None
    sanitized = {}
    for k, v in details.items():
        key_lower = k.lower()
        if any(s in key_lower for s in ("password", "hash", "secret", "token", "auth", "bearer", "storage_key")):
            continue
        sanitized[k] = v
    return sanitized


@router.get(
    "",
    response_model=PaginatedAuditLogsResponse,
    status_code=status.HTTP_200_OK,
    summary="List and filter audit logs",
    description="Read-only, paginated, and filtered view of system audit logs. Admin and Records Officer only.",
)
def list_audit_logs(
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size limit (1-100)")] = 20,
    search: Annotated[str | None, Query(max_length=100, description="Search term across action, resource_type, or client_ip")] = None,
    action: Annotated[str | None, Query(max_length=100, description="Exact filter on action name (e.g. 'document.upload')")] = None,
    resource_type: Annotated[str | None, Query(max_length=50, description="Filter by resource type ('document', 'workflow', 'user', etc.)")] = None,
    resource_id: Annotated[uuid.UUID | None, Query(description="Filter by exact resource UUID")] = None,
    actor_id: Annotated[uuid.UUID | None, Query(description="Filter by actor UUID")] = None,
    outcome: Annotated[AuditOutcome | None, Query(description="Filter by outcome ('success', 'denied', 'failed')")] = None,
    start_date: Annotated[datetime | None, Query(description="Inclusive start timestamp in ISO format")] = None,
    end_date: Annotated[datetime | None, Query(description="Inclusive end timestamp in ISO format")] = None,
    current_user: User = Depends(require_audit_viewer_role),
    db: Session = Depends(get_db),
):
    """
    List audit logs with comprehensive SQL-level filtering and deterministic ordering:
    - Strictly authorized for admin and records_officer.
    - Validates date range (start_date <= end_date).
    - Sorts by created_at DESC, id DESC.
    """
    # 1. Date Range Validation
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be earlier than or equal to end_date.",
        )

    # 2. Build Query
    query = db.query(AuditLog).options(joinedload(AuditLog.actor))

    if action and action.strip():
        query = query.filter(AuditLog.action == action.strip())

    if resource_type and resource_type.strip():
        query = query.filter(func.lower(AuditLog.resource_type) == resource_type.strip().lower())

    if resource_id:
        query = query.filter(AuditLog.resource_id == resource_id)

    if actor_id:
        query = query.filter(AuditLog.actor_id == actor_id)

    if outcome:
        query = query.filter(AuditLog.outcome == outcome)

    if start_date:
        query = query.filter(AuditLog.created_at >= start_date)

    if end_date:
        query = query.filter(AuditLog.created_at <= end_date)

    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                AuditLog.action.ilike(pattern),
                AuditLog.resource_type.ilike(pattern),
                AuditLog.client_ip.ilike(pattern),
                AuditLog.correlation_id.ilike(pattern),
            )
        )

    # 3. Pagination & Count
    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    logs = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [
        AuditLogSummaryResponse(
            id=log.id,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            outcome=log.outcome,
            actor_id=log.actor_id,
            actor=_build_safe_actor_info(log.actor),
            client_ip=log.client_ip,
            correlation_id=log.correlation_id,
            created_at=log.created_at,
        )
        for log in logs
    ]

    return PaginatedAuditLogsResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.get(
    "/reports/summary",
    response_model=AuditReportSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get aggregate audit report summary",
    description="Returns aggregate counts by action, outcome, and recent security events. Admin and Records Officer only.",
)
def get_audit_report_summary(
    start_date: Annotated[datetime | None, Query(description="Optional start timestamp for report")] = None,
    end_date: Annotated[datetime | None, Query(description="Optional end timestamp for report")] = None,
    current_user: User = Depends(require_audit_viewer_role),
    db: Session = Depends(get_db),
):
    """
    Returns high-level administrative summaries:
    - Total events
    - Breakdown by action
    - Breakdown by outcome
    - Top 10 most recent security/administrative events
    """
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be earlier than or equal to end_date.",
        )

    base_query = db.query(AuditLog)
    if start_date:
        base_query = base_query.filter(AuditLog.created_at >= start_date)
    if end_date:
        base_query = base_query.filter(AuditLog.created_at <= end_date)

    total_events = base_query.count()

    # Group by action
    action_counts_raw = (
        db.query(AuditLog.action, func.count(AuditLog.id))
        .filter(*(base_query.whereclause._clauses if base_query.whereclause is not None else []))
        .group_by(AuditLog.action)
        .all()
    )
    events_by_action = {act: count for act, count in action_counts_raw}

    # Group by outcome
    outcome_counts_raw = (
        db.query(AuditLog.outcome, func.count(AuditLog.id))
        .filter(*(base_query.whereclause._clauses if base_query.whereclause is not None else []))
        .group_by(AuditLog.outcome)
        .all()
    )
    events_by_outcome = {
        (out.value if hasattr(out, "value") else str(out)): count for out, count in outcome_counts_raw
    }

    # Recent security-sensitive events (denials, user admin changes, cancellations)
    security_actions = [
        "user.create",
        "user.update",
        "user.activate",
        "user.deactivate",
        "workflow.cancelled",
        "workflow.cancel.denied",
        "workflow.submit_for_review.denied",
        "workflow.detail.denied",
    ]
    recent_security_logs = (
        db.query(AuditLog)
        .options(joinedload(AuditLog.actor))
        .filter(
            or_(
                AuditLog.action.in_(security_actions),
                AuditLog.outcome == AuditOutcome.DENIED,
            )
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(10)
        .all()
    )

    recent_security_events = [
        AuditLogSummaryResponse(
            id=log.id,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            outcome=log.outcome,
            actor_id=log.actor_id,
            actor=_build_safe_actor_info(log.actor),
            client_ip=log.client_ip,
            correlation_id=log.correlation_id,
            created_at=log.created_at,
        )
        for log in recent_security_logs
    ]

    return AuditReportSummaryResponse(
        total_events=total_events,
        events_by_action=events_by_action,
        events_by_outcome=events_by_outcome,
        recent_security_events=recent_security_events,
    )


@router.get(
    "/{audit_log_id}",
    response_model=AuditLogDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get audit log details",
    description="Inspect a single audit log event and its sanitized context metadata.",
)
def get_audit_log_detail(
    audit_log_id: uuid.UUID,
    current_user: User = Depends(require_audit_viewer_role),
    db: Session = Depends(get_db),
):
    """
    Retrieve single audit event:
    - Strictly read-only.
    - Sanitizes detail metadata to avoid leaking sensitive credentials or filesystem paths.
    """
    log = (
        db.query(AuditLog)
        .options(joinedload(AuditLog.actor))
        .filter(AuditLog.id == audit_log_id)
        .first()
    )
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit log entry with ID {audit_log_id} not found.",
        )

    return AuditLogDetailResponse(
        id=log.id,
        action=log.action,
        resource_type=log.resource_type,
        resource_id=log.resource_id,
        outcome=log.outcome,
        actor_id=log.actor_id,
        actor=_build_safe_actor_info(log.actor),
        client_ip=log.client_ip,
        correlation_id=log.correlation_id,
        created_at=log.created_at,
        details=_sanitize_details(log.details),
    )
