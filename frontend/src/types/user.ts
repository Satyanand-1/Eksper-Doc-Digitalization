export type UserRole =
  | "admin"
  | "records_officer"
  | "department_user"
  | "approver"
  | "auditor"
  | "read_only";

export interface EligibleApprover {
  id: string;
  email: string;
  full_name: string;
  department: string;
}

export interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  department: string | null;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PaginatedUsersResponse {
  items: AdminUser[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface CreateUserPayload {
  full_name: string;
  email: string;
  role: UserRole;
  department?: string | null;
  password: string;
}

export interface UpdateUserPayload {
  full_name?: string;
  department?: string | null;
  role?: UserRole;
}

export interface UpdateUserStatusPayload {
  is_active: boolean;
}
