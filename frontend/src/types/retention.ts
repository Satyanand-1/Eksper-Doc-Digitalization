export type RetentionPeriodUnit = "days" | "months" | "years";
export type RetentionTriggerEvent = "creation" | "approval";
export type LegalHoldStatus = "active" | "released";
export type DisposalEligibilityStatus = "retained" | "eligible_for_review" | "on_hold" | "needs_attention";

export interface RetentionRule {
  id: string;
  name: string;
  description: string | null;
  classification: string | null;
  retention_period_unit: RetentionPeriodUnit;
  retention_period_value: number;
  trigger_event: RetentionTriggerEvent;
  is_active: boolean;
  created_by_id: string;
  updated_by_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaginatedRetentionRulesResponse {
  items: RetentionRule[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface CreateRetentionRulePayload {
  name: string;
  description?: string;
  classification?: string;
  retention_period_unit: RetentionPeriodUnit;
  retention_period_value: number;
  trigger_event: RetentionTriggerEvent;
}

export interface UpdateRetentionRulePayload {
  name?: string;
  description?: string;
  classification?: string;
  retention_period_unit?: RetentionPeriodUnit;
  retention_period_value?: number;
  trigger_event?: RetentionTriggerEvent;
  is_active?: boolean;
}

export interface LegalHold {
  id: string;
  document_id: string;
  hold_reason: string;
  status: LegalHoldStatus;
  placed_by_id: string;
  placed_at: string;
  released_by_id: string | null;
  released_at: string | null;
  release_reason: string | null;
}

export interface CreateLegalHoldPayload {
  hold_reason: string;
}

export interface ReleaseLegalHoldPayload {
  release_reason: string;
}

export interface DocumentRetentionInfo {
  document_id: string;
  retention_rule: RetentionRule | null;
  retention_trigger_date: string | null;
  retention_start_date: string | null;
  retention_end_date: string | null;
  retention_assigned_at: string | null;
  retention_assigned_by_id: string | null;
  active_legal_hold_count: number;
  eligibility_status: DisposalEligibilityStatus;
  eligibility_explanation: string;
}

export interface AssignRetentionRulePayload {
  retention_rule_id: string;
  override_start_date?: string;
}

export interface DisposalEligibilityItem {
  document_id: string;
  document_reference: string;
  title: string;
  department: string;
  classification: string;
  status: string;
  created_at: string;
  retention_rule_id: string | null;
  retention_rule_name: string | null;
  retention_start_date: string | null;
  retention_end_date: string | null;
  is_expired: boolean;
  has_active_hold: boolean;
  active_hold_count: number;
  eligibility_status: DisposalEligibilityStatus;
  eligibility_explanation: string;
}

export interface PaginatedDisposalEligibilityResponse {
  items: DisposalEligibilityItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}
