import { PhysicalUserShortInfo } from "./physical_file";

export type CustodyStatus = "active" | "returned" | "transferred";
export type MovementType = "initial_storage" | "checkout" | "checkin" | "transfer" | "relocation";

export interface CustodyRecord {
  id: string;
  physical_file_id: string;
  file_reference: string;
  file_title: string;
  custodian_user_id?: string | null;
  custodian_name: string;
  custodian_department?: string | null;
  custodian_contact?: string | null;
  status: CustodyStatus;
  checked_out_at: string;
  expected_return_at?: string | null;
  checked_in_at?: string | null;
  purpose?: string | null;
  checkin_notes?: string | null;
  issued_by_id: string;
  issued_by?: PhysicalUserShortInfo | null;
  received_by_id?: string | null;
  received_by?: PhysicalUserShortInfo | null;
  is_overdue: boolean;
  created_at: string;
  updated_at: string;
}

export interface MovementHistoryItem {
  id: string;
  physical_file_id: string;
  movement_type: MovementType;
  source_location_id?: string | null;
  source_location_code?: string | null;
  source_location_name?: string | null;
  destination_location_id?: string | null;
  destination_location_code?: string | null;
  destination_location_name?: string | null;
  from_custody_state: string;
  to_custody_state: string;
  actor_id: string;
  actor?: PhysicalUserShortInfo | null;
  event_at: string;
  reason?: string | null;
  custody_record_id?: string | null;
  created_at: string;
}

export interface OverdueFileSummary {
  physical_file_id: string;
  file_reference: string;
  title: string;
  department: string;
  classification?: string | null;
  custody_record_id: string;
  custodian_name: string;
  custodian_department?: string | null;
  custodian_contact?: string | null;
  checked_out_at: string;
  expected_return_at: string;
  days_overdue: number;
  purpose?: string | null;
  storage_location_name?: string | null;
  storage_location_code?: string | null;
  issued_by?: PhysicalUserShortInfo | null;
}

export interface CustodyCheckoutPayload {
  custodian_name: string;
  custodian_department?: string | null;
  custodian_contact?: string | null;
  custodian_user_id?: string | null;
  expected_return_at?: string | null;
  purpose?: string | null;
}

export interface CustodyCheckinPayload {
  destination_location_id?: string | null;
  checkin_notes?: string | null;
}

export interface FileTransferPayload {
  destination_location_id: string;
  reason: string;
}

export interface PaginatedCustodyRecordsResponse {
  items: CustodyRecord[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface PaginatedMovementHistoryResponse {
  items: MovementHistoryItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface PaginatedOverdueFilesResponse {
  items: OverdueFileSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface CustodyIntegrityIssue {
  issue_type: string;
  severity: "error" | "warning";
  physical_file_id: string;
  file_reference: string;
  title: string;
  department: string;
  description: string;
  diagnostic_details: Record<string, any>;
  detected_at: string;
}

export interface CustodyIntegrityReport {
  total_files_scanned: number;
  total_issues_found: number;
  issues_by_type: Record<string, number>;
  items: CustodyIntegrityIssue[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface LocationTransferEventItem {
  movement_id: string;
  physical_file_id: string;
  file_reference: string;
  title: string;
  department: string;
  source_location_code?: string | null;
  source_location_name?: string | null;
  destination_location_code?: string | null;
  destination_location_name?: string | null;
  transferred_at: string;
  reason: string;
  transferred_by?: PhysicalUserShortInfo | null;
}

export interface PaginatedLocationTransfersResponse {
  items: LocationTransferEventItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

