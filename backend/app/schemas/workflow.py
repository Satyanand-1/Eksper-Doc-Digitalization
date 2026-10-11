import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, model_validator

from app.models.document import DocumentStatus, ExtractionStatus
from app.models.workflow import WorkflowState, ReviewDecision


class SubmitForReviewRequest(BaseModel):
    """
    Request payload to submit a draft document for review.
    """
    approver_id: uuid.UUID = Field(..., description="UUID of the explicitly assigned approver")
    comments: str | None = Field(None, max_length=1000, description="Optional submission comments or instructions")


class ReviewAssignmentResponse(BaseModel):
    """
    Representation of an approver assignment within a review workflow.
    """
    id: uuid.UUID = Field(..., description="Assignment unique identifier")
    workflow_id: uuid.UUID = Field(..., description="Associated workflow unique identifier")
    assigned_approver_id: uuid.UUID = Field(..., description="Assigned approver user ID")
    assigned_at: datetime = Field(..., description="Assignment timestamp in UTC")
    decision: ReviewDecision | None = Field(None, description="Decision outcome")
    decided_at: datetime | None = Field(None, description="Decision timestamp in UTC")
    decision_comments: str | None = Field(None, description="Decision comments")

    model_config = ConfigDict(from_attributes=True)


class WorkflowSubmissionResponse(BaseModel):
    """
    Operational response returned upon successful submission of a document for review.
    """
    workflow_id: uuid.UUID = Field(..., description="Workflow unique identifier")
    document_id: uuid.UUID = Field(..., description="Associated document unique identifier")
    document_reference: str = Field(..., description="Document human-readable reference code")
    document_status: DocumentStatus = Field(..., description="Updated document status (under_review)")
    workflow_state: WorkflowState = Field(..., description="Current workflow state (pending)")
    submitter_id: uuid.UUID = Field(..., description="Submitter user ID")
    submitted_at: datetime = Field(..., description="Submission timestamp in UTC")
    comments: str | None = Field(None, description="Submission comments")
    assignment: ReviewAssignmentResponse = Field(..., description="Active review assignment details")

    model_config = ConfigDict(from_attributes=True)


# --- Task 5.2 Schemas ---

class WorkflowDecisionRequest(BaseModel):
    """
    Request payload for an approver to submit an approval or rejection decision.
    """
    decision: ReviewDecision = Field(..., description="Decision outcome: 'approved' or 'rejected'")
    comments: str | None = Field(None, max_length=1000, description="Comments explaining the decision. Required for rejection.")

    @model_validator(mode="after")
    def validate_rejection_comments(self) -> "WorkflowDecisionRequest":
        if self.decision == ReviewDecision.REJECTED:
            if not self.comments or not self.comments.strip():
                raise ValueError("Comments are required when rejecting a document.")
        return self


class UserDisplayInfo(BaseModel):
    """
    Safe presentation info for users in workflow responses.
    """
    id: uuid.UUID = Field(..., description="User unique identifier")
    email: str = Field(..., description="User email address")
    full_name: str = Field(..., description="User full display name")
    department: str | None = Field(None, description="User department")

    model_config = ConfigDict(from_attributes=True)


class WorkflowDocumentSummary(BaseModel):
    """
    Safe document metadata for review assignment listing.
    """
    id: uuid.UUID = Field(..., description="Document unique identifier")
    document_reference: str = Field(..., description="Document reference code")
    title: str = Field(..., description="Document title")
    department: str = Field(..., description="Owning department")
    classification: str = Field(..., description="Classification category")
    status: DocumentStatus = Field(..., description="Document lifecycle status")
    created_at: datetime = Field(..., description="Document creation timestamp in UTC")

    model_config = ConfigDict(from_attributes=True)


class ReviewAssignmentItem(BaseModel):
    """
    Single review inbox assignment item for GET /api/v1/workflows/my-assignments.
    """
    assignment_id: uuid.UUID = Field(..., description="Assignment unique identifier")
    workflow_id: uuid.UUID = Field(..., description="Workflow unique identifier")
    workflow_state: WorkflowState = Field(..., description="Workflow state (pending)")
    submitted_at: datetime = Field(..., description="Submission timestamp in UTC")
    submission_comments: str | None = Field(None, description="Submitter comments")
    submitter: UserDisplayInfo = Field(..., description="Submitter display details")
    document: WorkflowDocumentSummary = Field(..., description="Associated document metadata")

    model_config = ConfigDict(from_attributes=True)


class PaginatedAssignmentsResponse(BaseModel):
    """
    Paginated list of review assignments.
    """
    items: list[ReviewAssignmentItem] = Field(..., description="Current page assignments")
    total: int = Field(..., description="Total matching assignments")
    page: int = Field(..., description="Current 1-indexed page number")
    page_size: int = Field(..., description="Page size limit")
    total_pages: int = Field(..., description="Total pages available")

    model_config = ConfigDict(from_attributes=True)


class WorkflowVersionSummary(BaseModel):
    """
    Safe version metadata included in workflow detail.
    """
    id: uuid.UUID = Field(..., description="Version unique identifier")
    version_number: int = Field(..., description="Version sequence number")
    original_filename: str = Field(..., description="Original filename")
    mime_type: str = Field(..., description="MIME type")
    file_size_bytes: int = Field(..., description="File size in bytes")
    extraction_status: ExtractionStatus = Field(..., description="OCR text extraction status")
    extracted_text: str | None = Field(None, description="OCR text extraction content")
    created_at: datetime = Field(..., description="Upload timestamp in UTC")

    model_config = ConfigDict(from_attributes=True)


class WorkflowDocumentDetail(BaseModel):
    """
    Safe document metadata included in workflow detail.
    """
    id: uuid.UUID = Field(..., description="Document unique identifier")
    document_reference: str = Field(..., description="Document reference code")
    title: str = Field(..., description="Document title")
    subject: str | None = Field(None, description="Document subject or summary")
    department: str = Field(..., description="Owning department")
    classification: str = Field(..., description="Classification category")
    status: DocumentStatus = Field(..., description="Document lifecycle status")
    current_version: WorkflowVersionSummary | None = Field(None, description="Active or latest document version")

    model_config = ConfigDict(from_attributes=True)


class WorkflowDetailResponse(BaseModel):
    """
    Comprehensive safe workflow detail for GET /api/v1/workflows/{workflow_id}.
    """
    id: uuid.UUID = Field(..., description="Workflow unique identifier")
    document_id: uuid.UUID = Field(..., description="Document unique identifier")
    state: WorkflowState = Field(..., description="Current workflow state")
    submitted_at: datetime = Field(..., description="Submission timestamp in UTC")
    submission_comments: str | None = Field(None, description="Submission comments")
    submitter: UserDisplayInfo = Field(..., description="Submitter details")
    document: WorkflowDocumentDetail = Field(..., description="Document metadata")
    assignments: list[ReviewAssignmentResponse] = Field(..., description="Review assignments")

    model_config = ConfigDict(from_attributes=True)


class WorkflowDecisionResponse(BaseModel):
    """
    Response returned after recording an approval or rejection decision.
    """
    workflow_id: uuid.UUID = Field(..., description="Workflow unique identifier")
    document_id: uuid.UUID = Field(..., description="Document unique identifier")
    document_reference: str = Field(..., description="Document reference code")
    document_status: DocumentStatus = Field(..., description="Updated document lifecycle status (active or draft)")
    workflow_state: WorkflowState = Field(..., description="Updated workflow state (approved or rejected)")
    decision: ReviewDecision = Field(..., description="Decision recorded (approved or rejected)")
    decided_by_id: uuid.UUID = Field(..., description="Approver user ID")
    decided_at: datetime = Field(..., description="Decision timestamp in UTC")
    comments: str | None = Field(None, description="Decision comments")

    model_config = ConfigDict(from_attributes=True)


# --- Task 5.3 Schemas: Workflow History ---

class WorkflowHistoryAssignment(BaseModel):
    """
    Safe assignment details within a historical workflow attempt.
    """
    id: uuid.UUID = Field(..., description="Assignment unique identifier")
    workflow_id: uuid.UUID = Field(..., description="Associated workflow unique identifier")
    assigned_approver: UserDisplayInfo = Field(..., description="Assigned approver display information")
    assigned_at: datetime = Field(..., description="Assignment timestamp in UTC")
    decision: ReviewDecision | None = Field(None, description="Decision outcome: 'approved', 'rejected', or null")
    decided_at: datetime | None = Field(None, description="Decision timestamp in UTC")
    decision_comments: str | None = Field(None, description="Decision comments or justification")

    model_config = ConfigDict(from_attributes=True)


class WorkflowHistoryAttempt(BaseModel):
    """
    Represents an individual historical or current workflow review attempt.
    """
    workflow_id: uuid.UUID = Field(..., description="Workflow unique identifier")
    state: WorkflowState = Field(..., description="Workflow lifecycle state ('pending', 'approved', 'rejected', 'cancelled')")
    submitted_at: datetime = Field(..., description="Submission timestamp in UTC")
    submission_comments: str | None = Field(None, description="Submitter submission comments")
    submitter: UserDisplayInfo = Field(..., description="Submitter display details")
    cancelled_by: UserDisplayInfo | None = Field(None, description="User who cancelled the workflow, if applicable")
    cancelled_at: datetime | None = Field(None, description="Cancellation timestamp in UTC, if applicable")
    cancellation_comments: str | None = Field(None, description="Cancellation reason or justification, if applicable")
    assignments: list[WorkflowHistoryAssignment] = Field(default_factory=list, description="Approver assignments and recorded decisions")

    model_config = ConfigDict(from_attributes=True)


class DocumentWorkflowHistoryResponse(BaseModel):
    """
    Response envelope for GET /api/v1/documents/{document_id}/workflow-history.
    """
    document_id: uuid.UUID = Field(..., description="Target document unique identifier")
    document_reference: str = Field(..., description="Human-readable document reference code")
    document_status: DocumentStatus = Field(..., description="Current document lifecycle status")
    total_attempts: int = Field(..., description="Total count of workflow review attempts returned")
    attempts: list[WorkflowHistoryAttempt] = Field(default_factory=list, description="Chronological review attempts (oldest first)")

    model_config = ConfigDict(from_attributes=True)


# --- Task 5.4 Schemas: Workflow Cancellation ---

class CancelWorkflowRequest(BaseModel):
    """
    Request payload to cancel a pending review workflow.
    Requires a non-empty, bounded cancellation reason.
    """
    comments: str = Field(..., min_length=1, max_length=1000, description="Mandatory reason explaining the cancellation or withdrawal.")

    @model_validator(mode="after")
    def validate_non_whitespace_comments(self) -> "CancelWorkflowRequest":
        if not self.comments or not self.comments.strip():
            raise ValueError("Cancellation reason cannot be empty or solely whitespace.")
        self.comments = self.comments.strip()
        return self


class CancelWorkflowResponse(BaseModel):
    """
    Operational response returned upon successfully cancelling a review workflow.
    """
    workflow_id: uuid.UUID = Field(..., description="Workflow unique identifier")
    document_id: uuid.UUID = Field(..., description="Associated document unique identifier")
    document_reference: str = Field(..., description="Document reference code")
    document_status: DocumentStatus = Field(..., description="Updated document lifecycle status ('draft')")
    workflow_state: WorkflowState = Field(..., description="Updated workflow state ('cancelled')")
    cancelled_by_id: uuid.UUID = Field(..., description="User ID who cancelled the workflow")
    cancelled_at: datetime = Field(..., description="Cancellation timestamp in UTC")
    comments: str = Field(..., description="Cancellation reason recorded")

    model_config = ConfigDict(from_attributes=True)

