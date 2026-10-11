import uuid
from datetime import datetime, timezone
import math
import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy import func, or_, desc, asc
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.document import DigitalDocument, DocumentStatus
from app.models.retention import (
    RetentionRule,
    LegalHold,
    RetentionPeriodUnit,
    RetentionTriggerEvent,
    LegalHoldStatus,
    DisposalEligibilityStatus,
)
from app.models.audit import AuditOutcome
from app.schemas.retention import (
    RetentionRuleCreate,
    RetentionRuleUpdate,
    RetentionRuleStatusUpdate,
    RetentionRuleResponse,
    PaginatedRetentionRulesResponse,
    AssignRetentionRuleRequest,
    DocumentRetentionInfoResponse,
    CreateLegalHoldRequest,
    ReleaseLegalHoldRequest,
    LegalHoldResponse,
    DisposalEligibilityItemResponse,
    PaginatedDisposalEligibilityResponse,
)
from app.services.authorization import document_auth_service
from app.services.retention import retention_calc_service
from app.services.audit import audit_service, AuditWriteError

logger = logging.getLogger("edrms.retention")

router = APIRouter(prefix="/api/v1/retention", tags=["Retention"])


def require_retention_rule_manager(current_user: User = Depends(get_current_user)) -> User:
    """Restricts access strictly to administrators and records officers."""
    decision = document_auth_service.can_manage_retention_rules(current_user)
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=decision.reason,
        )
    return current_user


# -------------------------------------------------------------------
# 1. Retention Rule Management Endpoints
# -------------------------------------------------------------------

@router.get(
    "/rules",
    response_model=PaginatedRetentionRulesResponse,
    status_code=status.HTTP_200_OK,
    summary="List retention rules",
)
def list_retention_rules(
    request: Request,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 25,
    q: Annotated[str | None, Query(description="Search in name or description")] = None,
    classification: Annotated[str | None, Query(description="Filter by classification")] = None,
    is_active: Annotated[bool | None, Query(description="Filter by active status")] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lists retention rules with optional search, classification filter, and active status filter.
    Available to all authenticated users (read-only for non-admins).
    """
    query = db.query(RetentionRule)

    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(RetentionRule.name).like(term),
                func.lower(RetentionRule.description).like(term),
            )
        )

    if classification and classification.strip():
        query = query.filter(func.lower(RetentionRule.classification) == classification.strip().lower())

    if is_active is not None:
        query = query.filter(RetentionRule.is_active == is_active)

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    rules = (
        query.order_by(RetentionRule.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaginatedRetentionRulesResponse(
        items=[RetentionRuleResponse.model_validate(r) for r in rules],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post(
    "/rules",
    response_model=RetentionRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new retention rule",
)
def create_retention_rule(
    payload: RetentionRuleCreate,
    request: Request,
    current_user: User = Depends(require_retention_rule_manager),
    db: Session = Depends(get_db),
):
    """
    Creates a new retention schedule policy.
    Enforces uniqueness of rule name.
    """
    existing = db.query(RetentionRule).filter(func.lower(RetentionRule.name) == payload.name.strip().lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Retention rule with name '{payload.name.strip()}' already exists.",
        )

    rule = RetentionRule(
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        classification=payload.classification.strip() if payload.classification else None,
        retention_period_unit=payload.retention_period_unit,
        retention_period_value=payload.retention_period_value,
        trigger_event=payload.trigger_event,
        is_active=True,
        created_by_id=current_user.id,
    )
    db.add(rule)
    db.flush()

    # Mandatory Audit Logging
    audit_service.log_from_request(
        db=db,
        request=request,
        action="retention_rule.create",
        resource_type="retention_rule",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=rule.id,
        details={
            "rule_name": rule.name,
            "period_unit": rule.retention_period_unit.value,
            "period_value": rule.retention_period_value,
            "trigger_event": rule.trigger_event.value,
            "classification": rule.classification,
        },
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(rule)
    return RetentionRuleResponse.model_validate(rule)


@router.get(
    "/rules/{rule_id}",
    response_model=RetentionRuleResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single retention rule",
)
def get_retention_rule(
    rule_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rule = db.query(RetentionRule).filter(RetentionRule.id == rule_id).first()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Retention rule not found.",
        )
    return RetentionRuleResponse.model_validate(rule)


@router.patch(
    "/rules/{rule_id}",
    response_model=RetentionRuleResponse,
    status_code=status.HTTP_200_OK,
    summary="Update retention rule",
)
def update_retention_rule(
    rule_id: uuid.UUID,
    payload: RetentionRuleUpdate,
    request: Request,
    current_user: User = Depends(require_retention_rule_manager),
    db: Session = Depends(get_db),
):
    rule = db.query(RetentionRule).filter(RetentionRule.id == rule_id).with_for_update().first()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Retention rule not found.",
        )

    changes = {}

    if payload.name is not None and payload.name.strip() != rule.name:
        existing = db.query(RetentionRule).filter(
            func.lower(RetentionRule.name) == payload.name.strip().lower(),
            RetentionRule.id != rule.id,
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Retention rule with name '{payload.name.strip()}' already exists.",
            )
        changes["name"] = payload.name.strip()
        rule.name = payload.name.strip()

    if payload.description is not None:
        rule.description = payload.description.strip() if payload.description else None
        changes["description"] = rule.description

    if payload.classification is not None:
        rule.classification = payload.classification.strip() if payload.classification else None
        changes["classification"] = rule.classification

    if payload.retention_period_unit is not None:
        changes["retention_period_unit"] = payload.retention_period_unit.value
        rule.retention_period_unit = payload.retention_period_unit

    if payload.retention_period_value is not None:
        changes["retention_period_value"] = payload.retention_period_value
        rule.retention_period_value = payload.retention_period_value

    if payload.trigger_event is not None:
        changes["trigger_event"] = payload.trigger_event.value
        rule.trigger_event = payload.trigger_event

    if payload.is_active is not None:
        changes["is_active"] = payload.is_active
        rule.is_active = payload.is_active

    rule.updated_by_id = current_user.id
    rule.updated_at = datetime.now(timezone.utc)
    db.flush()

    # Mandatory Audit Logging
    audit_service.log_from_request(
        db=db,
        request=request,
        action="retention_rule.update",
        resource_type="retention_rule",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=rule.id,
        details={"changes": changes},
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(rule)
    return RetentionRuleResponse.model_validate(rule)


@router.patch(
    "/rules/{rule_id}/status",
    response_model=RetentionRuleResponse,
    status_code=status.HTTP_200_OK,
    summary="Activate or deactivate a retention rule",
)
def set_retention_rule_status(
    rule_id: uuid.UUID,
    payload: RetentionRuleStatusUpdate,
    request: Request,
    current_user: User = Depends(require_retention_rule_manager),
    db: Session = Depends(get_db),
):
    rule = db.query(RetentionRule).filter(RetentionRule.id == rule_id).with_for_update().first()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Retention rule not found.",
        )

    rule.is_active = payload.is_active
    rule.updated_by_id = current_user.id
    rule.updated_at = datetime.now(timezone.utc)
    db.flush()

    action = "retention_rule.activate" if payload.is_active else "retention_rule.deactivate"
    audit_service.log_from_request(
        db=db,
        request=request,
        action=action,
        resource_type="retention_rule",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=rule.id,
        details={"is_active": payload.is_active},
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(rule)
    return RetentionRuleResponse.model_validate(rule)


# -------------------------------------------------------------------
# 2. Document Retention Assignment & Status Endpoints
# -------------------------------------------------------------------

@router.get(
    "/documents/{document_id}",
    response_model=DocumentRetentionInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Get document retention status and history",
)
def get_document_retention_info(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns retention status, assigned rule, dates, and active hold count for a document.
    Enforces document read authorization.
    """
    doc = db.query(DigitalDocument).filter(DigitalDocument.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    read_dec = document_auth_service.can_view_metadata(current_user, doc)
    if not read_dec.allowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    active_hold_count = (
        db.query(func.count(LegalHold.id))
        .filter(
            LegalHold.document_id == doc.id,
            LegalHold.status == LegalHoldStatus.ACTIVE,
        )
        .scalar()
        or 0
    )

    eligibility_status, explanation = retention_calc_service.assess_document_eligibility(db, doc)

    rule_resp = None
    if doc.retention_rule:
        rule_resp = RetentionRuleResponse.model_validate(doc.retention_rule)

    return DocumentRetentionInfoResponse(
        document_id=doc.id,
        retention_rule=rule_resp,
        retention_trigger_date=doc.retention_trigger_date,
        retention_start_date=doc.retention_start_date,
        retention_end_date=doc.retention_end_date,
        retention_assigned_at=doc.retention_assigned_at,
        retention_assigned_by_id=doc.retention_assigned_by_id,
        active_legal_hold_count=active_hold_count,
        eligibility_status=eligibility_status,
        eligibility_explanation=explanation,
    )


@router.post(
    "/documents/{document_id}/assign-rule",
    response_model=DocumentRetentionInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign a retention rule to a document",
)
def assign_retention_rule_to_document(
    document_id: uuid.UUID,
    payload: AssignRetentionRuleRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Assigns a retention schedule rule to a document.
    Enforces department scoping and retention assignment authorization.
    Prevents silent shortening of an existing retention end date.
    """
    doc = db.query(DigitalDocument).filter(DigitalDocument.id == document_id).with_for_update().first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    auth_dec = document_auth_service.can_assign_retention_rule(current_user, doc)
    if not auth_dec.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=auth_dec.reason,
        )

    rule = db.query(RetentionRule).filter(RetentionRule.id == payload.retention_rule_id).first()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Retention rule not found.",
        )

    if not rule.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Retention rule '{rule.name}' is inactive and cannot be assigned to documents.",
        )

    # If the retention rule specifies a target classification, verify it matches document classification
    if rule.classification and rule.classification.strip():
        rule_cls = rule.classification.strip().lower()
        doc_cls = (doc.classification or "").strip().lower()
        financial_family = {"financial", "invoice", "receipt", "billing"}
        is_match = (rule_cls == doc_cls) or (rule_cls in financial_family and doc_cls in financial_family)
        if not is_match:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Retention rule '{rule.name}' is restricted to '{rule.classification}' records, "
                    f"which does not match document classification '{doc.classification}'."
                ),
            )

    # Resolve trigger date
    now = datetime.now(timezone.utc)
    trigger_date = payload.override_start_date or retention_calc_service.resolve_trigger_date(db, doc, rule.trigger_event)

    start_date = trigger_date
    new_end_date = None
    if start_date:
        new_end_date = retention_calc_service.calculate_end_date(
            start_date=start_date,
            unit=rule.retention_period_unit,
            value=rule.retention_period_value,
        )

    # Safeguard against silent shortening:
    # If the document already had a retention_end_date, and the new rule calculates a strictly earlier end date,
    # prevent silently reducing custody without explicit governance.
    if doc.retention_end_date and new_end_date:
        existing_end = doc.retention_end_date.replace(tzinfo=timezone.utc) if doc.retention_end_date.tzinfo is None else doc.retention_end_date
        calc_end = new_end_date.replace(tzinfo=timezone.utc) if new_end_date.tzinfo is None else new_end_date
        if calc_end < existing_end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Retention rule '{rule.name}' results in an earlier retention end date "
                    f"({calc_end.strftime('%Y-%m-%d')}) than the currently established retention end date "
                    f"({existing_end.strftime('%Y-%m-%d')}). Silent shortening of retention periods is prohibited."
                ),
            )

    doc.retention_rule_id = rule.id
    doc.retention_trigger_date = trigger_date
    doc.retention_start_date = start_date
    doc.retention_end_date = new_end_date
    doc.retention_assigned_at = now
    doc.retention_assigned_by_id = current_user.id
    db.flush()

    audit_service.log_from_request(
        db=db,
        request=request,
        action="retention.assign_rule",
        resource_type="document",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=doc.id,
        details={
            "document_reference": doc.document_reference,
            "rule_id": str(rule.id),
            "rule_name": rule.name,
            "retention_start_date": start_date.isoformat() if start_date else None,
            "retention_end_date": new_end_date.isoformat() if new_end_date else None,
        },
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(doc)

    active_hold_count = (
        db.query(func.count(LegalHold.id))
        .filter(
            LegalHold.document_id == doc.id,
            LegalHold.status == LegalHoldStatus.ACTIVE,
        )
        .scalar()
        or 0
    )
    eligibility_status, explanation = retention_calc_service.assess_document_eligibility(db, doc)

    return DocumentRetentionInfoResponse(
        document_id=doc.id,
        retention_rule=RetentionRuleResponse.model_validate(rule),
        retention_trigger_date=doc.retention_trigger_date,
        retention_start_date=doc.retention_start_date,
        retention_end_date=doc.retention_end_date,
        retention_assigned_at=doc.retention_assigned_at,
        retention_assigned_by_id=doc.retention_assigned_by_id,
        active_legal_hold_count=active_hold_count,
        eligibility_status=eligibility_status,
        eligibility_explanation=explanation,
    )


# -------------------------------------------------------------------
# 3. Legal Hold Management Endpoints
# -------------------------------------------------------------------

@router.get(
    "/documents/{document_id}/legal-holds",
    response_model=list[LegalHoldResponse],
    status_code=status.HTTP_200_OK,
    summary="List legal holds for a document",
)
def list_document_legal_holds(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lists all legal holds (both active and released) for a document.
    Enforces document read authorization.
    """
    doc = db.query(DigitalDocument).filter(DigitalDocument.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    read_dec = document_auth_service.can_view_metadata(current_user, doc)
    if not read_dec.allowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    holds = (
        db.query(LegalHold)
        .filter(LegalHold.document_id == doc.id)
        .order_by(desc(LegalHold.placed_at))
        .all()
    )
    return [LegalHoldResponse.model_validate(h) for h in holds]


@router.post(
    "/documents/{document_id}/legal-holds",
    response_model=LegalHoldResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Place a legal hold on a document",
)
def place_legal_hold(
    document_id: uuid.UUID,
    payload: CreateLegalHoldRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Places an active legal hold on a document.
    Restricted to Administrator and Records Officer.
    """
    doc = db.query(DigitalDocument).filter(DigitalDocument.id == document_id).with_for_update().first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    auth_dec = document_auth_service.can_manage_legal_holds(current_user, doc)
    if not auth_dec.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=auth_dec.reason,
        )

    hold = LegalHold(
        document_id=doc.id,
        hold_reason=payload.hold_reason.strip(),
        status=LegalHoldStatus.ACTIVE,
        placed_by_id=current_user.id,
    )
    db.add(hold)
    db.flush()

    audit_service.log_from_request(
        db=db,
        request=request,
        action="legal_hold.place",
        resource_type="document",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=doc.id,
        details={
            "document_reference": doc.document_reference,
            "legal_hold_id": str(hold.id),
            "hold_reason": hold.hold_reason,
        },
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(hold)
    return LegalHoldResponse.model_validate(hold)


@router.post(
    "/legal-holds/{hold_id}/release",
    response_model=LegalHoldResponse,
    status_code=status.HTTP_200_OK,
    summary="Release an active legal hold",
)
def release_legal_hold(
    hold_id: uuid.UUID,
    payload: ReleaseLegalHoldRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Releases an active legal hold. Requires release reason comment.
    Restricted to Administrator and Records Officer.
    """
    hold = db.query(LegalHold).filter(LegalHold.id == hold_id).with_for_update().first()
    if not hold:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Legal hold not found.",
        )

    doc = db.query(DigitalDocument).filter(DigitalDocument.id == hold.document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document associated with legal hold not found.",
        )

    auth_dec = document_auth_service.can_manage_legal_holds(current_user, doc)
    if not auth_dec.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=auth_dec.reason,
        )

    if hold.status == LegalHoldStatus.RELEASED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Legal hold has already been released.",
        )

    now = datetime.now(timezone.utc)
    hold.status = LegalHoldStatus.RELEASED
    hold.released_by_id = current_user.id
    hold.released_at = now
    hold.release_reason = payload.release_reason.strip()
    db.flush()

    audit_service.log_from_request(
        db=db,
        request=request,
        action="legal_hold.release",
        resource_type="document",
        outcome=AuditOutcome.SUCCESS,
        actor_id=current_user.id,
        resource_id=doc.id,
        details={
            "document_reference": doc.document_reference,
            "legal_hold_id": str(hold.id),
            "release_reason": hold.release_reason,
        },
        raise_on_failure=True,
    )

    db.commit()
    db.refresh(hold)
    return LegalHoldResponse.model_validate(hold)


# -------------------------------------------------------------------
# 4. Disposal Eligibility Assessment Endpoint
# -------------------------------------------------------------------

@router.get(
    "/disposal-eligibility",
    response_model=PaginatedDisposalEligibilityResponse,
    status_code=status.HTTP_200_OK,
    summary="List disposal eligibility assessments",
)
def get_disposal_eligibility(
    request: Request,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 25,
    department: Annotated[str | None, Query(description="Filter by department")] = None,
    rule_id: Annotated[uuid.UUID | None, Query(description="Filter by retention rule ID")] = None,
    eligibility_status: Annotated[DisposalEligibilityStatus | None, Query(description="Filter by eligibility status")] = None,
    q: Annotated[str | None, Query(description="Search in reference or title")] = None,
    start_date: Annotated[datetime | None, Query(description="Filter records with retention end date >= start_date")] = None,
    end_date: Annotated[datetime | None, Query(description="Filter records with retention end date <= end_date")] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Read-only disposal eligibility assessment query.
    Applies role-based document scoping (e.g. department users restricted to own department).
    Calculates explicit eligibility statuses:
    - retained: retention end date in the future
    - eligible_for_review: retention expired and no active legal hold
    - on_hold: active legal hold placed on document
    - needs_attention: missing rule or dates
    """
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be before or equal to end_date.",
        )

    auth_dec = document_auth_service.can_view_disposal_eligibility(current_user)
    if not auth_dec.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=auth_dec.reason,
        )

    scope_filter = document_auth_service.build_document_scope_filter(current_user)
    query = db.query(DigitalDocument).filter(scope_filter)

    if department and department.strip():
        query = query.filter(func.lower(DigitalDocument.department) == department.strip().lower())

    if rule_id:
        query = query.filter(DigitalDocument.retention_rule_id == rule_id)

    if start_date:
        query = query.filter(DigitalDocument.retention_end_date >= start_date)

    if end_date:
        query = query.filter(DigitalDocument.retention_end_date <= end_date)

    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(DigitalDocument.document_reference).like(term),
                func.lower(DigitalDocument.title).like(term),
            )
        )

    # Order newest-first deterministically
    docs = query.order_by(desc(DigitalDocument.created_at), desc(DigitalDocument.id)).all()

    now = datetime.now(timezone.utc)
    items = []

    for doc in docs:
        st, expl = retention_calc_service.assess_document_eligibility(db, doc, now=now)

        if eligibility_status and st != eligibility_status:
            continue

        active_hold_count = (
            db.query(func.count(LegalHold.id))
            .filter(
                LegalHold.document_id == doc.id,
                LegalHold.status == LegalHoldStatus.ACTIVE,
            )
            .scalar()
            or 0
        )

        is_expired = False
        if doc.retention_end_date:
            end_tz = doc.retention_end_date.replace(tzinfo=timezone.utc) if doc.retention_end_date.tzinfo is None else doc.retention_end_date
            is_expired = now >= end_tz

        items.append(
            DisposalEligibilityItemResponse(
                document_id=doc.id,
                document_reference=doc.document_reference,
                title=doc.title,
                department=doc.department,
                classification=doc.classification,
                status=doc.status.value,
                created_at=doc.created_at,
                retention_rule_id=doc.retention_rule_id,
                retention_rule_name=doc.retention_rule.name if doc.retention_rule else None,
                retention_start_date=doc.retention_start_date,
                retention_end_date=doc.retention_end_date,
                is_expired=is_expired,
                has_active_hold=(active_hold_count > 0),
                active_hold_count=active_hold_count,
                eligibility_status=st,
                eligibility_explanation=expl,
            )
        )

    total = len(items)
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    start_idx = (page - 1) * page_size
    paged_items = items[start_idx : start_idx + page_size]

    return PaginatedDisposalEligibilityResponse(
        items=paged_items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )
