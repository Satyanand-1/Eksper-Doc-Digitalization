export type WorkflowState = "pending" | "approved" | "rejected" | "cancelled";

export type ReviewDecision = "approved" | "rejected";

export type DocumentStatus = "draft" | "under_review" | "active" | "archived";

export type ExtractionStatus = "pending" | "processing" | "completed" | "failed";

export interface UserDisplayInfo {
  id: string;
  email: string;
  full_name: string;
  department: string | null;
}

export interface WorkflowDocumentSummary {
  id: string;
  document_reference: string;
  title: string;
  department: string;
  classification: string;
  status: DocumentStatus;
  created_at: string;
}

export interface ReviewAssignmentItem {
  assignment_id: string;
  workflow_id: string;
  workflow_state: WorkflowState;
  submitted_at: string;
  submission_comments: string | null;
  submitter: UserDisplayInfo;
  document: WorkflowDocumentSummary;
}

export interface PaginatedAssignmentsResponse {
  items: ReviewAssignmentItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface WorkflowVersionSummary {
  id: string;
  version_number: number;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number;
  extraction_status: ExtractionStatus;
  extracted_text?: string | null;
  created_at: string;
}

export interface WorkflowDocumentDetail {
  id: string;
  document_reference: string;
  title: string;
  subject: string | null;
  department: string;
  classification: string;
  status: DocumentStatus;
  current_version: WorkflowVersionSummary | null;
}

export interface ReviewAssignmentResponse {
  id: string;
  workflow_id: string;
  assigned_approver_id: string;
  assigned_at: string;
  decision: ReviewDecision | null;
  decided_at: string | null;
  decision_comments: string | null;
}

export interface WorkflowDetailResponse {
  id: string;
  document_id: string;
  state: WorkflowState;
  submitted_at: string;
  submission_comments: string | null;
  submitter: UserDisplayInfo;
  document: WorkflowDocumentDetail;
  assignments: ReviewAssignmentResponse[];
}

export interface WorkflowDecisionRequest {
  decision: ReviewDecision;
  comments?: string | null;
}

export interface WorkflowDecisionResponse {
  workflow_id: string;
  document_id: string;
  document_reference: string;
  document_status: DocumentStatus;
  workflow_state: WorkflowState;
  decision: ReviewDecision;
  decided_by_id: string;
  decided_at: string;
  comments: string | null;
}

export interface WorkflowHistoryAssignment {
  id: string;
  workflow_id: string;
  assigned_approver: UserDisplayInfo;
  assigned_at: string;
  decision: ReviewDecision | null;
  decided_at: string | null;
  decision_comments: string | null;
}

export interface WorkflowHistoryAttempt {
  workflow_id: string;
  state: WorkflowState;
  submitted_at: string;
  submission_comments: string | null;
  submitter: UserDisplayInfo;
  cancelled_by: UserDisplayInfo | null;
  cancelled_at: string | null;
  cancellation_comments: string | null;
  assignments: WorkflowHistoryAssignment[];
}

export interface DocumentWorkflowHistoryResponse {
  document_id: string;
  document_reference: string;
  document_status: DocumentStatus;
  total_attempts: number;
  attempts: WorkflowHistoryAttempt[];
}
