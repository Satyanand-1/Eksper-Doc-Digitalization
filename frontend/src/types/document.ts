import { DocumentStatus, ExtractionStatus, WorkflowState, ReviewAssignmentResponse } from "./workflow";

export interface CreatorInfo {
  id: string;
  email: string;
  full_name: string;
  department: string | null;
}

export interface DocumentSummaryResponse {
  id: string;
  document_reference: string;
  title: string;
  subject: string | null;
  department: string;
  classification: string;
  mime_type: string;
  status: DocumentStatus;
  created_at: string;
  updated_at: string;
  version_count: number;
}

export interface DocumentDetailResponse {
  id: string;
  document_reference: string;
  title: string;
  subject: string | null;
  department: string;
  classification: string;
  mime_type: string;
  status: DocumentStatus;
  created_by_id: string;
  creator: CreatorInfo | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  available_versions: number[];
  version_count: number;
}

export interface DocumentVersionResponse {
  id: string;
  document_id: string;
  version_number: number;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number;
  file_hash_sha256: string;
  extraction_status: ExtractionStatus;
  extraction_completed_at: string | null;
  extraction_error: string | null;
  extracted_text?: string | null;
  created_by_id: string;
  creator: CreatorInfo | null;
  created_at: string;
}

export interface PaginatedDocumentResponse {
  items: DocumentSummaryResponse[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface SubmitForReviewRequest {
  approver_id: string;
  comments?: string | null;
}

export interface WorkflowSubmissionResponse {
  workflow_id: string;
  document_id: string;
  document_reference: string;
  document_status: DocumentStatus;
  workflow_state: WorkflowState;
  submitter_id: string;
  submitted_at: string;
  comments: string | null;
  assignment: ReviewAssignmentResponse;
}
