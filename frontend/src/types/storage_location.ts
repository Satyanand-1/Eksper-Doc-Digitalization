export type LocationType =
  | "building"
  | "floor"
  | "room"
  | "cabinet"
  | "shelf"
  | "bay"
  | "box"
  | "other";

export interface StorageLocationBreadcrumb {
  id: string;
  location_code: string;
  name: string;
  location_type: LocationType;
}

export interface StorageLocationSummary {
  id: string;
  location_code: string;
  name: string;
  location_type: LocationType;
  department: string;
  parent_id?: string | null;
  is_active: boolean;
  max_capacity?: number | null;
  direct_file_count: number;
  child_count: number;
  location_path: string;
  created_at: string;
  updated_at: string;
}

export interface StorageLocationDetail {
  id: string;
  location_code: string;
  name: string;
  location_type: LocationType;
  description?: string | null;
  department: string;
  parent_id?: string | null;
  parent?: StorageLocationSummary | null;
  is_active: boolean;
  max_capacity?: number | null;
  direct_file_count: number;
  child_count: number;
  location_path: string;
  breadcrumbs: StorageLocationBreadcrumb[];
  created_by_id: string;
  created_by?: {
    id: string;
    email: string;
    full_name: string;
    department?: string | null;
  } | null;
  updated_by_id?: string | null;
  updated_by?: {
    id: string;
    email: string;
    full_name: string;
    department?: string | null;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface PaginatedStorageLocationsResponse {
  items: StorageLocationSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface CreateStorageLocationPayload {
  location_code: string;
  name: string;
  location_type: LocationType;
  description?: string | null;
  department: string;
  parent_id?: string | null;
  max_capacity?: number | null;
}

export interface UpdateStorageLocationPayload {
  name?: string | null;
  description?: string | null;
  location_type?: LocationType | null;
  parent_id?: string | null;
  clear_parent?: boolean;
  max_capacity?: number | null;
  clear_max_capacity?: boolean;
  department?: string | null;
}

export interface ChangeStorageLocationStatusPayload {
  is_active: boolean;
  reason?: string | null;
}

export interface AssignFileLocationPayload {
  storage_location_id: string | null;
  notes?: string | null;
}
