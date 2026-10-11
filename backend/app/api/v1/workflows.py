"""
Workflow management API endpoints for EDRMS.
Task 5.2: Approver Review Inbox, Workflow Detail Retrieval, and Controlled Approval/Rejection Decision APIs.
"""
import uuid
import math
import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus
from app.models.workflow import ReviewWorkflow, ReviewAssignment, WorkflowState, ReviewDecision, utc_now
from app.models.audit import AuditOutcome
from app.services.authorization import document_auth_service
from app.services.audit import audit_service, AuditWriteError
from app.services.notification import notification_service
from app.schemas.workflow import (
    WorkflowDecisionRequest,
    WorkflowDecisionResponse,
    WorkflowDetailResponse,
    WorkflowDocumentDetail,
    WorkflowVersionSummary,
    UserDisplayInfo,
    ReviewAssignmentResponse,
    PaginatedAssignmentsResponse,
    ReviewAssignmentItem,
    WorkflowDocumentSummary,
    CancelWorkflowRequest,
    CancelWorkflowResponse,
)

logger = logging.getLogger("edrms.workflows")

router = APIRouter(prefix="/api/v1/workflows", tags=["Workflows"])


@router.get(
    "/my-assignments",
    response_model=PaginatedAssignmentsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get approver's pending review inbox assignments",
    description="Retrieves a paginated list of pending review assignments explicitly assigned to the authenticated approver.",
)
def get_my_assignments(
    request: Request,
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size limit (1-100)")] = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Approver Review Inbox:
    - Requires active user with 'approver' role.
    - Returns only pending assignments explicitly assigned to current_user.
    - Enforces document department alignment at SQL query level.
    - Excludes other approvers' assignments.
    - Safe metadata only: no file paths, secrets, or extracted text.
    """
    if current_user.role != UserRole.APPROVER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only users with the 'approver' role can access the review inbox.",
        )

    user_dept = (current_user.department or "").strip()
    if not user_dept:
        # Ambiguous department strictly returns empty result
        return PaginatedAssignmentsResponse(
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            total_pages=0,
        )

    # Base query: Join ReviewAssignment, ReviewWorkflow, DigitalDocument, User (submitter)
    # Filter: assignment assigned to current_user, workflow state = PENDING,
    # document status = UNDER_REVIEW, and document department matches approver department
    query = (
        db.query(ReviewAssignment, ReviewWorkflow, DigitalDocument, User)
        .join(ReviewWorkflow, ReviewAssignment.workflow_id == ReviewWorkflow.id)
        .join(DigitalDocument, ReviewWorkflow.document_id == DigitalDocument.id)
        .join(User, ReviewWorkflow.submitter_id == User.id)
        .filter(
            ReviewAssignment.assigned_approver_id == current_user.id,
            ReviewWorkflow.state == WorkflowState.PENDING,
            DigitalDocument.status == DocumentStatus.UNDER_REVIEW,
            func.lower(DigitalDocument.department) == user_dept.lower(),
        )
    )

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    offset = (page - 1) * page_size

    results = (
        query.order_by(desc(ReviewWorkflow.submitted_at))
        .offset(offset)
        .limit(page_size)
        .all()
    )

    items = []
    for assignment, workflow, doc, submitter in results:
        items.append(
            ReviewAssignmentItem(
                assignment_id=assignment.id,
                workflow_id=workflow.id,
                workflow_state=workflow.state,
                submitted_at=workflow.submitted_at,
                submission_comments=workflow.submission_comments,
                submitter=UserDisplayInfo(
                    id=submitter.id,
                    email=submitter.email,
                    full_name=submitter.full_name,
                    department=submitter.department,
                ),
                document=WorkflowDocumentSummary(
                    id=doc.id,
                    document_reference=doc.document_reference,
                    title=doc.title,
                    department=doc.department,
                    classification=doc.classification,
                    status=doc.status,
                    created_at=doc.created_at,
                ),
            )
        )

    return PaginatedAssignmentsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{workflow_id}",
    response_model=WorkflowDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get workflow details and safe document metadata",
    description="Retrieves workflow details, submitter information, document metadata, and review assignments. Access is restricted to the explicitly assigned approver or administrative roles.",
)
def get_workflow_detail(
    workflow_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Workflow Detail Retrieval:
    - Verifies workflow exists.
    - Validates authorization using document_auth_service.can_view_workflow.
    - Non-disclosing 404 response for unauthorized users or nonexistent records.
    - Returns safe document and latest version metadata.
    """
    workflow = db.query(ReviewWorkflow).filter(ReviewWorkflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found.",
        )

    # Check authorization
    auth_decision = document_auth_service.can_view_workflow(current_user, workflow)
    if not auth_decision.allowed:
        # Non-disclosing 404 response to prevent workflow enumeration
        audit_service.log_from_request(
            db=db,
            request=request,
            action="workflow.detail.denied",
            resource_type="workflow",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=workflow_id,
            details={"reason": auth_decision.reason, "user_role": current_user.role.value},
            raise_on_failure=False,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found.",
        )

    doc = workflow.document
    submitter = workflow.submitter

    # Retrieve current/latest version
    latest_version = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == doc.id)
        .order_by(desc(DocumentVersion.version_number))
        .first()
    )

    current_version_summary = None
    if latest_version:
        current_version_summary = WorkflowVersionSummary(
            id=latest_version.id,
            version_number=latest_version.version_number,
            original_filename=latest_version.original_filename,
            mime_type=latest_version.mime_type,
            file_size_bytes=latest_version.file_size_bytes,
            extraction_status=latest_version.extraction_status,
            extracted_text=latest_version.extracted_text,
            created_at=latest_version.created_at,
        )

    doc_detail = WorkflowDocumentDetail(
        id=doc.id,
        document_reference=doc.document_reference,
        title=doc.title,
        subject=doc.subject,
        department=doc.department,
        classification=doc.classification,
        status=doc.status,
        current_version=current_version_summary,
    )

    assignment_responses = [
        ReviewAssignmentResponse(
            id=a.id,
            workflow_id=a.workflow_id,
            assigned_approver_id=a.assigned_approver_id,
            assigned_at=a.assigned_at,
            decision=a.decision,
            decided_at=a.decided_at,
            decision_comments=a.decision_comments,
        )
        for a in workflow.assignments
    ]

    return WorkflowDetailResponse(
        id=workflow.id,
        document_id=workflow.document_id,
        state=workflow.state,
        submitted_at=workflow.submitted_at,
        submission_comments=workflow.submission_comments,
        submitter=UserDisplayInfo(
            id=submitter.id,
            email=submitter.email,
            full_name=submitter.full_name,
            department=submitter.department,
        ),
        document=doc_detail,
        assignments=assignment_responses,
    )


@router.post(
    "/{workflow_id}/decision",
    response_model=WorkflowDecisionResponse,
    status_code=status.HTTP_200_OK,
    summary="Record approver review decision (approve or reject)",
    description="Processes an approver's decision on a pending workflow. Approval activates the document; rejection returns it to draft status.",
)
def record_workflow_decision(
    workflow_id: uuid.UUID,
    payload: WorkflowDecisionRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Workflow Decision Endpoint:
    - Must be authenticated active user with 'approver' role.
    - Acquires row lock (SELECT FOR UPDATE) on ReviewWorkflow and DigitalDocument.
    - Verifies explicit assignment to current_user.
    - Verifies workflow is PENDING and document is UNDER_REVIEW.
    - Verifies document has a valid current version.
    - Verifies department and classification policies still permit approver access.
    - If APPROVED: workflow state -> approved, document status -> active.
    - If REJECTED: workflow state -> rejected, document status -> draft (requires non-empty comments).
    - Persists mandatory audit event (workflow.approved or workflow.rejected) with atomic rollback.
    """
    if current_user.role != UserRole.APPROVER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only assigned approvers can submit workflow decisions.",
        )

    # 1. Fetch workflow with row lock to prevent concurrent double-decisions
    workflow = (
        db.query(ReviewWorkflow)
        .filter(ReviewWorkflow.id == workflow_id)
        .with_for_update()
        .first()
    )
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found.",
        )

    # 2. Verify current user is explicitly assigned to this workflow
    assignment = (
        db.query(ReviewAssignment)
        .filter(
            ReviewAssignment.workflow_id == workflow.id,
            ReviewAssignment.assigned_approver_id == current_user.id,
        )
        .with_for_update()
        .first()
    )
    if not assignment:
        # Non-disclosing 404 to unassigned approvers
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found.",
        )

    # 3. Check workflow state
    if workflow.state != WorkflowState.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Workflow is in '{workflow.state.value}' state and cannot accept further decisions.",
        )

    # 4. Fetch associated document with row lock
    doc = (
        db.query(DigitalDocument)
        .filter(DigitalDocument.id == workflow.document_id)
        .with_for_update()
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated document not found.",
        )

    if doc.status != DocumentStatus.UNDER_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document is in '{doc.status.value}' status, not 'under_review'.",
        )

    # 5. Verify document has at least one valid version
    has_version = (
        db.query(DocumentVersion.id)
        .filter(DocumentVersion.document_id == doc.id)
        .first()
    )
    if not has_version:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document has no registered versions and cannot be approved or rejected.",
        )

    # 6. Verify approver department and classification alignment
    approver_decision = document_auth_service.validate_approver_eligibility(
        approver=current_user,
        document=doc,
    )
    if not approver_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=approver_decision.reason,
        )

    # 7. Apply Decision State Transitions
    now = utc_now()
    assignment.decision = payload.decision
    assignment.decided_at = now
    assignment.decision_comments = payload.comments

    if payload.decision == ReviewDecision.APPROVED:
        workflow.state = WorkflowState.APPROVED
        doc.status = DocumentStatus.ACTIVE
        audit_action = "workflow.approved"

        # If document has an assigned retention rule triggered on approval, calculate start and end dates
        if doc.retention_rule and doc.retention_rule.trigger_event.value == "approval":
            from app.services.retention import retention_calc_service
            doc.retention_trigger_date = now
            doc.retention_start_date = now
            doc.retention_end_date = retention_calc_service.calculate_end_date(
                start_date=now,
                unit=doc.retention_rule.retention_period_unit,
                value=doc.retention_rule.retention_period_value,
            )

        notification_service.notify_workflow_approved(
            db=db,
            workflow=workflow,
            document=doc,
        )
    elif payload.decision == ReviewDecision.REJECTED:
        workflow.state = WorkflowState.REJECTED
        doc.status = DocumentStatus.DRAFT
        audit_action = "workflow.rejected"
        notification_service.notify_workflow_rejected(
            db=db,
            workflow=workflow,
            document=doc,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported decision '{payload.decision}'.",
        )

    try:
        db.flush()

        # 8. Mandatory Audit Logging (raise_on_failure=True)
        audit_service.log_from_request(
            db=db,
            request=request,
            action=audit_action,
            resource_type="workflow",
            outcome=AuditOutcome.SUCCESS,
            actor_id=current_user.id,
            resource_id=workflow.id,
            details={
                "workflow_id": str(workflow.id),
                "assignment_id": str(assignment.id),
                "document_id": str(doc.id),
                "document_reference": doc.document_reference,
                "decision": payload.decision.value,
                "comments": payload.comments,
                "previous_document_status": DocumentStatus.UNDER_REVIEW.value,
                "new_document_status": doc.status.value,
                "workflow_state": workflow.state.value,
            },
            raise_on_failure=True,
        )

        db.commit()
        db.refresh(workflow)
        db.refresh(assignment)
        db.refresh(doc)

        logger.info(
            f"Workflow {workflow.id} for document {doc.document_reference} ({doc.id}) "
            f"decided as '{payload.decision.value}' by approver {current_user.email}."
        )

        return WorkflowDecisionResponse(
            workflow_id=workflow.id,
            document_id=doc.id,
            document_reference=doc.document_reference,
            document_status=doc.status,
            workflow_state=workflow.state,
            decision=payload.decision,
            decided_by_id=current_user.id,
            decided_at=assignment.decided_at,
            comments=assignment.decision_comments,
        )

    except IntegrityError as integ_err:
        db.rollback()
        logger.error(f"Integrity conflict during workflow {workflow.id} decision: {integ_err}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A workflow decision conflict occurred. Please refresh.",
        )
    except AuditWriteError as a_err:
        db.rollback()
        logger.error(f"Mandatory audit write failure on workflow {workflow.id} decision: {a_err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security audit recording failed.",
        )
    except Exception as exc:
        db.rollback()
        logger.error(f"Unexpected error deciding workflow {workflow.id}: {exc}")
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the workflow decision.",
        )


@router.post(
    "/{workflow_id}/cancel",
    response_model=CancelWorkflowResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel or withdraw a pending review workflow",
    description="Withdraws a pending review workflow. Transitions the workflow state to 'cancelled' and returns the document status to 'draft'. Restricted to the original submitter, Administrator, or Records Officer.",
)
def cancel_workflow(
    workflow_id: uuid.UUID,
    payload: CancelWorkflowRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Workflow Cancellation & Submission Withdrawal (Task 5.4):
    - Validates caller authentication and authorization.
    - Locks the workflow and associated document using SELECT FOR UPDATE.
    - Enforces workflow state is 'pending' and document status is 'under_review'.
    - Prevents cancellation of already approved, rejected, or cancelled workflows (409 Conflict).
    - Updates workflow state to 'cancelled' and documents status to 'draft'.
    - Stores cancelled_by_id, cancelled_at, and cancellation_comments.
    - Mandatory security audit logging (workflow.cancelled) with atomic rollback on failure.
    - Non-disclosing 404 for unauthorized users or nonexistent workflows.
    """
    # 1. Fetch workflow record with row lock
    workflow = (
        db.query(ReviewWorkflow)
        .filter(ReviewWorkflow.id == workflow_id)
        .with_for_update()
        .first()
    )
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found.",
        )

    # 2. Fetch associated document with row lock
    doc = (
        db.query(DigitalDocument)
        .filter(DigitalDocument.id == workflow.document_id)
        .with_for_update()
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated document not found.",
        )

    # 3. Check authorization using DocumentAuthorizationService
    # For department users or unauthorized callers, verify whether they have access
    # or return non-disclosing 404 / 403 according to standard security model.
    # If the user is unassigned or unauthorized, return non-disclosing 404 to avoid enumeration.
    auth_decision = document_auth_service.can_cancel_workflow(
        user=current_user,
        workflow=workflow,
        document=doc,
    )

    if not auth_decision.allowed:
        # Check if denial is because of workflow state or document status vs user permission
        if workflow.state != WorkflowState.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Workflow is in '{workflow.state.value}' state and cannot be cancelled.",
            )
        if doc.status != DocumentStatus.UNDER_REVIEW:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Document is in '{doc.status.value}' status, not 'under_review'.",
            )

        # Audit denied attempt
        audit_service.log_from_request(
            db=db,
            request=request,
            action="workflow.cancel.denied",
            resource_type="workflow",
            outcome=AuditOutcome.DENIED,
            actor_id=current_user.id,
            resource_id=workflow.id,
            details={
                "reason": auth_decision.reason,
                "user_role": current_user.role.value,
                "workflow_id": str(workflow.id),
                "document_id": str(doc.id),
            },
            raise_on_failure=False,
        )

        # Non-disclosing 404 for callers who have no cancellation or workflow oversight rights
        # to prevent leaking workflow existence
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with ID {workflow_id} not found.",
        )

    # 4. Check workflow state and document status explicitly (for concurrency safety)
    if workflow.state != WorkflowState.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Workflow is in '{workflow.state.value}' state and cannot be cancelled.",
        )

    if doc.status != DocumentStatus.UNDER_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document is in '{doc.status.value}' status, not 'under_review'.",
        )

    # 5. Apply State Transitions
    now = utc_now()
    workflow.state = WorkflowState.CANCELLED
    workflow.cancelled_by_id = current_user.id
    workflow.cancelled_at = now
    workflow.cancellation_comments = payload.comments

    previous_doc_status = doc.status.value
    doc.status = DocumentStatus.DRAFT

    # Notify assigned approvers that the workflow was withdrawn
    assigned_approvers = [
        a.assigned_approver_id
        for a in db.query(ReviewAssignment.assigned_approver_id)
        .filter(ReviewAssignment.workflow_id == workflow.id)
        .all()
    ]
    if assigned_approvers:
        notification_service.notify_workflow_cancelled(
            db=db,
            workflow=workflow,
            document=doc,
            assigned_approver_ids=assigned_approvers,
        )

    try:
        db.flush()

        # 6. Mandatory Audit Logging (raise_on_failure=True)
        audit_service.log_from_request(
            db=db,
            request=request,
            action="workflow.cancelled",
            resource_type="workflow",
            outcome=AuditOutcome.SUCCESS,
            actor_id=current_user.id,
            resource_id=workflow.id,
            details={
                "workflow_id": str(workflow.id),
                "document_id": str(doc.id),
                "document_reference": doc.document_reference,
                "comments": payload.comments,
                "previous_document_status": previous_doc_status,
                "new_document_status": doc.status.value,
                "previous_workflow_state": WorkflowState.PENDING.value,
                "new_workflow_state": workflow.state.value,
                "cancelled_by_id": str(current_user.id),
            },
            raise_on_failure=True,
        )

        db.commit()
        db.refresh(workflow)
        db.refresh(doc)

        logger.info(
            f"Workflow {workflow.id} for document {doc.document_reference} ({doc.id}) "
            f"cancelled by user {current_user.email} ({current_user.role.value}). Reason: {payload.comments}"
        )

        return CancelWorkflowResponse(
            workflow_id=workflow.id,
            document_id=doc.id,
            document_reference=doc.document_reference,
            document_status=doc.status,
            workflow_state=workflow.state,
            cancelled_by_id=workflow.cancelled_by_id,
            cancelled_at=workflow.cancelled_at,
            comments=workflow.cancellation_comments,
        )

    except IntegrityError as integ_err:
        db.rollback()
        logger.error(f"Integrity conflict during workflow {workflow.id} cancellation: {integ_err}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A workflow cancellation conflict occurred. Please refresh.",
        )
    except AuditWriteError as a_err:
        db.rollback()
        logger.error(f"Mandatory audit write failure on workflow {workflow.id} cancellation: {a_err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security audit recording failed.",
        )
    except Exception as exc:
        db.rollback()
        logger.error(f"Unexpected error cancelling workflow {workflow.id}: {exc}")
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the workflow cancellation.",
        )

