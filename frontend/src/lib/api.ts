/**
 * Authenticated API client for EDRMS frontend.
 * Interacts with backend API endpoints using Bearer JWT authentication stored in localStorage.
 */
import {
  PaginatedNotificationsResponse,
  UnreadCountResponse,
  MarkNotificationReadResponse,
  UserProfile,
} from "@/types/notification";
import {
  PaginatedAssignmentsResponse,
  WorkflowDetailResponse,
  WorkflowDecisionRequest,
  WorkflowDecisionResponse,
  DocumentWorkflowHistoryResponse,
} from "@/types/workflow";
import {
  PaginatedDocumentResponse,
  DocumentDetailResponse,
  DocumentVersionResponse,
  SubmitForReviewRequest,
  WorkflowSubmissionResponse,
} from "@/types/document";
import {
  EligibleApprover,
  AdminUser,
  PaginatedUsersResponse,
  CreateUserPayload,
  UpdateUserPayload,
  UpdateUserStatusPayload,
} from "@/types/user";
import {
  PaginatedAuditLogsResponse,
  AuditLogDetail,
  AuditReportSummary,
} from "@/types/audit";
import {
  RetentionRule,
  PaginatedRetentionRulesResponse,
  CreateRetentionRulePayload,
  UpdateRetentionRulePayload,
  LegalHold,
  CreateLegalHoldPayload,
  ReleaseLegalHoldPayload,
  DocumentRetentionInfo,
  AssignRetentionRulePayload,
  PaginatedDisposalEligibilityResponse,
} from "@/types/retention";
import {
  PhysicalFileSummary,
  PhysicalFileDetail,
  PaginatedPhysicalFilesResponse,
  RegisterPhysicalFilePayload,
  UpdatePhysicalFilePayload,
  ChangePhysicalFileStatusPayload,
  PhysicalRecordType,
  PhysicalFileStatus,
} from "@/types/physical_file";
import {
  StorageLocationSummary,
  StorageLocationDetail,
  PaginatedStorageLocationsResponse,
  CreateStorageLocationPayload,
  UpdateStorageLocationPayload,
  ChangeStorageLocationStatusPayload,
  AssignFileLocationPayload,
  LocationType,
} from "@/types/storage_location";
import {
  CustodyRecord,
  MovementHistoryItem,
  OverdueFileSummary,
  CustodyCheckoutPayload,
  CustodyCheckinPayload,
  FileTransferPayload,
  PaginatedCustodyRecordsResponse,
  PaginatedMovementHistoryResponse,
  PaginatedOverdueFilesResponse,
  CustodyIntegrityReport,
  CustodyIntegrityIssue,
  PaginatedLocationTransfersResponse,
} from "@/types/custody";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function getDocumentPreviewUrl(documentId: string, versionNumber: number): string {
  const token = getStoredToken();
  const tokenParam = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${API_BASE}/api/v1/documents/${documentId}/versions/${versionNumber}/preview${tokenParam}`;
}

export function getDocumentDownloadUrl(documentId: string, versionNumber: number): string {
  const token = getStoredToken();
  const tokenParam = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${API_BASE}/api/v1/documents/${documentId}/versions/${versionNumber}/download${tokenParam}`;
}

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("edrms_token");
}

export function setStoredToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem("edrms_token", token);
}

export function clearStoredToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("edrms_token");
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers = new Headers(options.headers || {});

  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    // Notify session expiration if needed
    throw new ApiError("Session expired or unauthorized", 401);
  }

  if (!response.ok) {
    let errorData: any = null;
    try {
      errorData = await response.json();
    } catch {
      // ignore json parse error
    }
    const message = errorData?.detail || `API Error: ${response.status} ${response.statusText}`;
    throw new ApiError(message, response.status, errorData);
  }

  return response.json();
}

export const api = {
  // Auth
  async loginWithCredentials(email: string, password: string): Promise<{ access_token: string; token_type: string; expires_in: number }> {
    return request<{ access_token: string; token_type: string; expires_in: number }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },

  async getCurrentUser(): Promise<UserProfile> {
    return request<UserProfile>("/api/v1/auth/me");
  },

  async uploadDocument(formData: FormData): Promise<any> {
    return request<any>("/api/v1/documents/upload", {
      method: "POST",
      body: formData,
    });
  },

  // Notifications
  async getNotifications(page = 1, pageSize = 20, unreadOnly = false): Promise<PaginatedNotificationsResponse> {
    const params = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
    });
    if (unreadOnly) {
      params.set("unread_only", "true");
    }
    return request<PaginatedNotificationsResponse>(`/api/v1/notifications?${params.toString()}`);
  },

  async getUnreadCount(): Promise<UnreadCountResponse> {
    return request<UnreadCountResponse>("/api/v1/notifications/unread-count");
  },

  async markNotificationAsRead(notificationId: string): Promise<MarkNotificationReadResponse> {
    return request<MarkNotificationReadResponse>(`/api/v1/notifications/${notificationId}/read`, {
      method: "POST",
    });
  },

  // Workflows (Task 5.7)
  async getMyAssignments(page = 1, pageSize = 20): Promise<PaginatedAssignmentsResponse> {
    const params = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
    });
    return request<PaginatedAssignmentsResponse>(`/api/v1/workflows/my-assignments?${params.toString()}`);
  },

  async getWorkflowDetail(workflowId: string): Promise<WorkflowDetailResponse> {
    return request<WorkflowDetailResponse>(`/api/v1/workflows/${workflowId}`);
  },

  async submitWorkflowDecision(
    workflowId: string,
    payload: WorkflowDecisionRequest
  ): Promise<WorkflowDecisionResponse> {
    return request<WorkflowDecisionResponse>(`/api/v1/workflows/${workflowId}/decision`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // Documents & Submission (Task 5.8)
  async getDocuments(
    page = 1,
    pageSize = 20,
    search?: string,
    status?: string
  ): Promise<PaginatedDocumentResponse> {
    const params = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
    });
    if (search && search.trim()) {
      params.set("search", search.trim());
    }
    if (status && status.trim()) {
      params.set("status", status.trim());
    }
    return request<PaginatedDocumentResponse>(`/api/v1/documents?${params.toString()}`);
  },

  async getDocument(documentId: string): Promise<DocumentDetailResponse> {
    return request<DocumentDetailResponse>(`/api/v1/documents/${documentId}`);
  },

  async getDocumentVersions(documentId: string): Promise<DocumentVersionResponse[]> {
    return request<DocumentVersionResponse[]>(`/api/v1/documents/${documentId}/versions`);
  },

  async submitForReview(
    documentId: string,
    payload: SubmitForReviewRequest
  ): Promise<WorkflowSubmissionResponse> {
    return request<WorkflowSubmissionResponse>(`/api/v1/documents/${documentId}/submit-for-review`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getDocumentWorkflowHistory(documentId: string): Promise<DocumentWorkflowHistoryResponse> {
    return request<DocumentWorkflowHistoryResponse>(`/api/v1/documents/${documentId}/workflow-history`);
  },

  async getEligibleApprovers(params?: {
    document_id?: string;
    department?: string;
    q?: string;
    limit?: number;
  }): Promise<EligibleApprover[]> {
    const searchParams = new URLSearchParams();
    if (params?.document_id) searchParams.set("document_id", params.document_id);
    if (params?.department) searchParams.set("department", params.department);
    if (params?.q) searchParams.set("q", params.q);
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    const qs = searchParams.toString();
    return request<EligibleApprover[]>(`/api/v1/users/eligible-approvers${qs ? `?${qs}` : ""}`);
  },

  // User Administration (Admin only)
  async getUsers(params?: {
    page?: number;
    page_size?: number;
    search?: string;
    role?: string;
    department?: string;
    is_active?: boolean;
  }): Promise<PaginatedUsersResponse> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set("page", params.page.toString());
    if (params?.page_size) searchParams.set("page_size", params.page_size.toString());
    if (params?.search && params.search.trim()) searchParams.set("search", params.search.trim());
    if (params?.role && params.role.trim()) searchParams.set("role", params.role.trim());
    if (params?.department && params.department.trim()) searchParams.set("department", params.department.trim());
    if (params?.is_active !== undefined) searchParams.set("is_active", params.is_active.toString());
    const qs = searchParams.toString();
    return request<PaginatedUsersResponse>(`/api/v1/users${qs ? `?${qs}` : ""}`);
  },

  async createUser(payload: CreateUserPayload): Promise<AdminUser> {
    return request<AdminUser>("/api/v1/users", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async updateUser(userId: string, payload: UpdateUserPayload): Promise<AdminUser> {
    return request<AdminUser>(`/api/v1/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  async updateUserStatus(userId: string, payload: UpdateUserStatusPayload): Promise<AdminUser> {
    return request<AdminUser>(`/api/v1/users/${userId}/status`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  // Audit Logs (Admin & Records Officer only)
  async getAuditLogs(params?: {
    page?: number;
    page_size?: number;
    search?: string;
    action?: string;
    resource_type?: string;
    resource_id?: string;
    actor_id?: string;
    outcome?: string;
    start_date?: string;
    end_date?: string;
  }): Promise<PaginatedAuditLogsResponse> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set("page", params.page.toString());
    if (params?.page_size) searchParams.set("page_size", params.page_size.toString());
    if (params?.search && params.search.trim()) searchParams.set("search", params.search.trim());
    if (params?.action && params.action.trim()) searchParams.set("action", params.action.trim());
    if (params?.resource_type && params.resource_type.trim()) searchParams.set("resource_type", params.resource_type.trim());
    if (params?.resource_id && params.resource_id.trim()) searchParams.set("resource_id", params.resource_id.trim());
    if (params?.actor_id && params.actor_id.trim()) searchParams.set("actor_id", params.actor_id.trim());
    if (params?.outcome && params.outcome.trim()) searchParams.set("outcome", params.outcome.trim());
    if (params?.start_date && params.start_date.trim()) searchParams.set("start_date", params.start_date.trim());
    if (params?.end_date && params.end_date.trim()) searchParams.set("end_date", params.end_date.trim());
    const qs = searchParams.toString();
    return request<PaginatedAuditLogsResponse>(`/api/v1/audit-logs${qs ? `?${qs}` : ""}`);
  },

  async getAuditLogDetail(auditLogId: string): Promise<AuditLogDetail> {
    return request<AuditLogDetail>(`/api/v1/audit-logs/${auditLogId}`);
  },

  async getAuditReportSummary(params?: {
    start_date?: string;
    end_date?: string;
  }): Promise<AuditReportSummary> {
    const searchParams = new URLSearchParams();
    if (params?.start_date && params.start_date.trim()) searchParams.set("start_date", params.start_date.trim());
    if (params?.end_date && params.end_date.trim()) searchParams.set("end_date", params.end_date.trim());
    const qs = searchParams.toString();
    return request<AuditReportSummary>(`/api/v1/audit-logs/reports/summary${qs ? `?${qs}` : ""}`);
  },

  // Retention Rules
  async listRetentionRules(params?: {
    page?: number;
    page_size?: number;
    q?: string;
    classification?: string;
    is_active?: boolean;
  }): Promise<PaginatedRetentionRulesResponse> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set("page", String(params.page));
    if (params?.page_size) searchParams.set("page_size", String(params.page_size));
    if (params?.q && params.q.trim()) searchParams.set("q", params.q.trim());
    if (params?.classification && params.classification.trim()) searchParams.set("classification", params.classification.trim());
    if (params?.is_active !== undefined) searchParams.set("is_active", String(params.is_active));
    const qs = searchParams.toString();
    return request<PaginatedRetentionRulesResponse>(`/api/v1/retention/rules${qs ? `?${qs}` : ""}`);
  },

  async createRetentionRule(payload: CreateRetentionRulePayload): Promise<RetentionRule> {
    return request<RetentionRule>("/api/v1/retention/rules", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async updateRetentionRule(ruleId: string, payload: UpdateRetentionRulePayload): Promise<RetentionRule> {
    return request<RetentionRule>(`/api/v1/retention/rules/${ruleId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  async setRetentionRuleStatus(ruleId: string, isActive: boolean): Promise<RetentionRule> {
    return request<RetentionRule>(`/api/v1/retention/rules/${ruleId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: isActive }),
    });
  },

  // Document Retention & Legal Holds
  async getDocumentRetentionInfo(documentId: string): Promise<DocumentRetentionInfo> {
    return request<DocumentRetentionInfo>(`/api/v1/retention/documents/${documentId}`);
  },

  async assignRetentionRule(documentId: string, payload: AssignRetentionRulePayload): Promise<DocumentRetentionInfo> {
    return request<DocumentRetentionInfo>(`/api/v1/retention/documents/${documentId}/assign-rule`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async listDocumentLegalHolds(documentId: string): Promise<LegalHold[]> {
    return request<LegalHold[]>(`/api/v1/retention/documents/${documentId}/legal-holds`);
  },

  async placeLegalHold(documentId: string, payload: CreateLegalHoldPayload): Promise<LegalHold> {
    return request<LegalHold>(`/api/v1/retention/documents/${documentId}/legal-holds`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async releaseLegalHold(holdId: string, payload: ReleaseLegalHoldPayload): Promise<LegalHold> {
    return request<LegalHold>(`/api/v1/retention/legal-holds/${holdId}/release`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // Disposal Eligibility
  async getDisposalEligibility(params?: {
    page?: number;
    page_size?: number;
    department?: string;
    rule_id?: string;
    eligibility_status?: string;
    q?: string;
  }): Promise<PaginatedDisposalEligibilityResponse> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set("page", String(params.page));
    if (params?.page_size) searchParams.set("page_size", String(params.page_size));
    if (params?.department && params.department.trim()) searchParams.set("department", params.department.trim());
    if (params?.rule_id) searchParams.set("rule_id", params.rule_id);
    if (params?.eligibility_status && params.eligibility_status.trim()) searchParams.set("eligibility_status", params.eligibility_status.trim());
    if (params?.q && params.q.trim()) searchParams.set("q", params.q.trim());
    const qs = searchParams.toString();
    return request<PaginatedDisposalEligibilityResponse>(`/api/v1/retention/disposal-eligibility${qs ? `?${qs}` : ""}`);
  },

  // Physical File Registry
  async getPhysicalFiles(params?: {
    page?: number;
    page_size?: number;
    search?: string;
    department?: string;
    record_type?: string;
    classification?: string;
    custody_state?: "stored" | "checked_out" | "overdue";
    status?: string;
    sort_by?: string;
    sort_order?: string;
  }): Promise<PaginatedPhysicalFilesResponse> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set("page", String(params.page));
    if (params?.page_size) searchParams.set("page_size", String(params.page_size));
    if (params?.search && params.search.trim()) searchParams.set("search", params.search.trim());
    if (params?.department && params.department.trim()) searchParams.set("department", params.department.trim());
    if (params?.record_type && params.record_type.trim()) searchParams.set("record_type", params.record_type.trim());
    if (params?.classification && params.classification.trim()) searchParams.set("classification", params.classification.trim());
    if (params?.custody_state) searchParams.set("custody_state", params.custody_state);
    if (params?.status && params.status.trim()) searchParams.set("status", params.status.trim());
    if (params?.sort_by) searchParams.set("sort_by", params.sort_by);
    if (params?.sort_order) searchParams.set("sort_order", params.sort_order);
    const qs = searchParams.toString();
    return request<PaginatedPhysicalFilesResponse>(`/api/v1/physical-files${qs ? `?${qs}` : ""}`);
  },

  async lookupPhysicalFile(code: string): Promise<PhysicalFileDetail> {
    const searchParams = new URLSearchParams({ code: code.trim() });
    return request<PhysicalFileDetail>(`/api/v1/physical-files/lookup?${searchParams.toString()}`);
  },

  async recordLabelPrint(payload: { file_ids: string[]; label_format?: string }): Promise<{ status: string; printed_count: number }> {
    return request<{ status: string; printed_count: number }>("/api/v1/physical-files/print-label", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getPhysicalFile(fileId: string): Promise<PhysicalFileDetail> {
    return request<PhysicalFileDetail>(`/api/v1/physical-files/${fileId}`);
  },

  async registerPhysicalFile(payload: RegisterPhysicalFilePayload): Promise<PhysicalFileDetail> {
    return request<PhysicalFileDetail>("/api/v1/physical-files", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async updatePhysicalFile(fileId: string, payload: UpdatePhysicalFilePayload): Promise<PhysicalFileDetail> {
    return request<PhysicalFileDetail>(`/api/v1/physical-files/${fileId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  async changePhysicalFileStatus(fileId: string, payload: ChangePhysicalFileStatusPayload): Promise<PhysicalFileDetail> {
    return request<PhysicalFileDetail>(`/api/v1/physical-files/${fileId}/status`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  async assignFileLocation(fileId: string, payload: AssignFileLocationPayload): Promise<PhysicalFileDetail> {
    return request<PhysicalFileDetail>(`/api/v1/physical-files/${fileId}/assign-location`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async checkoutPhysicalFile(fileId: string, payload: CustodyCheckoutPayload): Promise<CustodyRecord> {
    return request<CustodyRecord>(`/api/v1/physical-files/${fileId}/checkout`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async checkinPhysicalFile(fileId: string, payload: CustodyCheckinPayload): Promise<CustodyRecord> {
    return request<CustodyRecord>(`/api/v1/physical-files/${fileId}/checkin`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async transferPhysicalFile(fileId: string, payload: FileTransferPayload): Promise<MovementHistoryItem> {
    return request<MovementHistoryItem>(`/api/v1/physical-files/${fileId}/transfer`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getPhysicalFileCustody(fileId: string): Promise<CustodyRecord | null> {
    return request<CustodyRecord | null>(`/api/v1/physical-files/${fileId}/custody`);
  },

  async getPhysicalFileCustodyHistory(
    fileId: string,
    params?: { page?: number; page_size?: number }
  ): Promise<PaginatedCustodyRecordsResponse> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set("page", String(params.page));
    if (params?.page_size) searchParams.set("page_size", String(params.page_size));
    const qs = searchParams.toString();
    return request<PaginatedCustodyRecordsResponse>(
      `/api/v1/physical-files/${fileId}/custody-history${qs ? `?${qs}` : ""}`
    );
  },

  async getPhysicalFileMovementHistory(
    fileId: string,
    params?: { page?: number; page_size?: number }
  ): Promise<PaginatedMovementHistoryResponse> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set("page", String(params.page));
    if (params?.page_size) searchParams.set("page_size", String(params.page_size));
    const qs = searchParams.toString();
    return request<PaginatedMovementHistoryResponse>(
      `/api/v1/physical-files/${fileId}/movement-history${qs ? `?${qs}` : ""}`
    );
  },

  async getOverduePhysicalFiles(params?: {
    page?: number;
    page_size?: number;
    department?: string;
    custodian?: string;
    min_days_overdue?: number;
  }): Promise<PaginatedOverdueFilesResponse> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set("page", String(params.page));
    if (params?.page_size) searchParams.set("page_size", String(params.page_size));
    if (params?.department && params.department.trim()) searchParams.set("department", params.department.trim());
    if (params?.custodian && params.custodian.trim()) searchParams.set("custodian", params.custodian.trim());
    if (params?.min_days_overdue !== undefined) searchParams.set("min_days_overdue", String(params.min_days_overdue));
    const qs = searchParams.toString();
    return request<PaginatedOverdueFilesResponse>(`/api/v1/physical-files/overdue${qs ? `?${qs}` : ""}`);
  },

  async getCustodyIntegrityReport(params?: {
    page?: number;
    page_size?: number;
    department?: string;
    issue_type?: string;
  }): Promise<CustodyIntegrityReport> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set("page", String(params.page));
    if (params?.page_size) searchParams.set("page_size", String(params.page_size));
    if (params?.department && params.department.trim()) searchParams.set("department", params.department.trim());
    if (params?.issue_type && params.issue_type.trim()) searchParams.set("issue_type", params.issue_type.trim());
    const qs = searchParams.toString();
    return request<CustodyIntegrityReport>(`/api/v1/physical-files/custody-integrity${qs ? `?${qs}` : ""}`);
  },

  async getLocationTransfersReport(params?: {
    page?: number;
    page_size?: number;
    department?: string;
    from_date?: string;
    to_date?: string;
  }): Promise<PaginatedLocationTransfersResponse> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set("page", String(params.page));
    if (params?.page_size) searchParams.set("page_size", String(params.page_size));
    if (params?.department && params.department.trim()) searchParams.set("department", params.department.trim());
    if (params?.from_date) searchParams.set("from_date", params.from_date);
    if (params?.to_date) searchParams.set("to_date", params.to_date);
    const qs = searchParams.toString();
    return request<PaginatedLocationTransfersResponse>(`/api/v1/physical-files/transfers${qs ? `?${qs}` : ""}`);
  },

  async downloadCustodyReportCsv(params: {
    report_type: "overdue" | "checked_out" | "transfers";
    department?: string;
  }): Promise<Blob> {
    const searchParams = new URLSearchParams({ report_type: params.report_type });
    if (params.department && params.department.trim()) {
      searchParams.set("department", params.department.trim());
    }
    const token = typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;
    const res = await fetch(`${API_BASE}/api/v1/physical-files/export-csv?${searchParams.toString()}`, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    if (!res.ok) {
      throw new ApiError("Failed to export report CSV", res.status);
    }
    return res.blob();
  },

  // Storage Locations
  async getStorageLocations(params?: {
    page?: number;
    page_size?: number;
    search?: string;
    department?: string;
    location_type?: string;
    parent_id?: string;
    top_level?: boolean;
    is_active?: boolean;
    sort_by?: string;
    sort_order?: string;
  }): Promise<PaginatedStorageLocationsResponse> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set("page", String(params.page));
    if (params?.page_size) searchParams.set("page_size", String(params.page_size));
    if (params?.search && params.search.trim()) searchParams.set("search", params.search.trim());
    if (params?.department && params.department.trim()) searchParams.set("department", params.department.trim());
    if (params?.location_type && params.location_type.trim()) searchParams.set("location_type", params.location_type.trim());
    if (params?.parent_id) searchParams.set("parent_id", params.parent_id);
    if (params?.top_level !== undefined) searchParams.set("top_level", String(params.top_level));
    if (params?.is_active !== undefined) searchParams.set("is_active", String(params.is_active));
    if (params?.sort_by) searchParams.set("sort_by", params.sort_by);
    if (params?.sort_order) searchParams.set("sort_order", params.sort_order);
    const qs = searchParams.toString();
    return request<PaginatedStorageLocationsResponse>(`/api/v1/storage-locations${qs ? `?${qs}` : ""}`);
  },

  async getStorageLocation(locationId: string): Promise<StorageLocationDetail> {
    return request<StorageLocationDetail>(`/api/v1/storage-locations/${locationId}`);
  },

  async createStorageLocation(payload: CreateStorageLocationPayload): Promise<StorageLocationDetail> {
    return request<StorageLocationDetail>("/api/v1/storage-locations", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async updateStorageLocation(locationId: string, payload: UpdateStorageLocationPayload): Promise<StorageLocationDetail> {
    return request<StorageLocationDetail>(`/api/v1/storage-locations/${locationId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  async changeStorageLocationStatus(locationId: string, payload: ChangeStorageLocationStatusPayload): Promise<StorageLocationDetail> {
    return request<StorageLocationDetail>(`/api/v1/storage-locations/${locationId}/status`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  async getStorageLocationChildren(locationId: string): Promise<StorageLocationSummary[]> {
    return request<StorageLocationSummary[]>(`/api/v1/storage-locations/${locationId}/children`);
  },

  async getStorageLocationContents(locationId: string, params?: { page?: number; page_size?: number }): Promise<PaginatedPhysicalFilesResponse> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set("page", String(params.page));
    if (params?.page_size) searchParams.set("page_size", String(params.page_size));
    const qs = searchParams.toString();
    return request<PaginatedPhysicalFilesResponse>(`/api/v1/storage-locations/${locationId}/contents${qs ? `?${qs}` : ""}`);
  },

  // Probes
  async getHealth(): Promise<{ status: string; service: string }> {
    return request("/api/v1/health");
  },
};
