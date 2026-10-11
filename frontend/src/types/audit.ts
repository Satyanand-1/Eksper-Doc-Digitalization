export interface AuditActor {
  id: string;
  email: string;
  full_name: string;
  department: string | null;
  role: string;
}

export interface AuditLogSummary {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  outcome: "success" | "denied" | "failed";
  actor_id: string | null;
  actor: AuditActor | null;
  client_ip: string | null;
  correlation_id: string | null;
  created_at: string;
}

export interface AuditLogDetail extends AuditLogSummary {
  details: Record<string, any> | null;
}

export interface PaginatedAuditLogsResponse {
  items: AuditLogSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AuditReportSummary {
  total_events: number;
  events_by_action: Record<string, number>;
  events_by_outcome: Record<string, number>;
  recent_security_events: AuditLogSummary[];
}
