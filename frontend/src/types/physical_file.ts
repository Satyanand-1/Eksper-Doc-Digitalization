export type PhysicalRecordType =
  | "contract"
  | "case_file"
  | "correspondence"
  | "archive_folder"
  | "financial_record"
  | "personnel_file"
  | "policy_document"
  | "other";

export type PhysicalFileStatus = "active" | "archived" | "inactive";

export interface LinkedDigitalDocumentInfo {
  id: string;
  document_reference: string;
  title: string;
  department: string;
  classification: string;
}

export interface PhysicalUserShortInfo {
  id: string;
  email: string;
  full_name: string;
  department?: string | null;
}

export interface PhysicalFileSummary {
  id: string;
  file_reference: string;
  title: string;
  record_type: PhysicalRecordType;
  department: string;
  classification?: string | null;
  status: PhysicalFileStatus;
  has_digital_document: boolean;
  storage_location_id?: string | null;
  storage_location_name?: string | null;
  storage_location_code?: string | null;
  location_path?: string | null;
  is_checked_out: boolean;
  current_custodian_name?: string | null;
  is_overdue: boolean;
  external_reference?: string | null;
  date_received: string;
  created_at: string;
  updated_at: string;
}

export interface PhysicalFileDetail {
  id: string;
  file_reference: string;
  title: string;
  description?: string | null;
  record_type: PhysicalRecordType;
  department: string;
  classification?: string | null;
  status: PhysicalFileStatus;
  digital_document_id?: string | null;
  digital_document?: LinkedDigitalDocumentInfo | null;
  storage_location_id?: string | null;
  storage_location_name?: string | null;
  storage_location_code?: string | null;
  location_path?: string | null;
  is_checked_out: boolean;
  current_custodian_name?: string | null;
  is_overdue: boolean;
  external_reference?: string | null;
  date_received: string;
  created_by_id: string;
  created_by?: PhysicalUserShortInfo | null;
  updated_by_id?: string | null;
  updated_by?: PhysicalUserShortInfo | null;
  created_at: string;
  updated_at: string;
}

export interface PaginatedPhysicalFilesResponse {
  items: PhysicalFileSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface RegisterPhysicalFilePayload {
  title: string;
  description?: string | null;
  record_type: PhysicalRecordType;
  department: string;
  classification?: string | null;
  digital_document_id?: string | null;
  storage_location_id?: string | null;
  external_reference?: string | null;
  date_received?: string | null;
}

export interface UpdatePhysicalFilePayload {
  title?: string | null;
  description?: string | null;
  record_type?: PhysicalRecordType | null;
  department?: string | null;
  classification?: string | null;
  digital_document_id?: string | null;
  unlink_digital_document?: boolean;
  storage_location_id?: string | null;
  unlink_storage_location?: boolean;
  external_reference?: string | null;
  date_received?: string | null;
}

export interface ChangePhysicalFileStatusPayload {
  status: PhysicalFileStatus;
  reason?: string | null;
}
