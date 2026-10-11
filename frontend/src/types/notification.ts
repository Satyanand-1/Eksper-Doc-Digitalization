export type NotificationType =
  | "workflow_submitted"
  | "workflow_approved"
  | "workflow_rejected"
  | "workflow_cancelled";

export interface NotificationItem {
  id: string;
  recipient_id: string;
  notification_type: NotificationType;
  title: string;
  message: string;
  document_id: string | null;
  workflow_id: string | null;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

export interface PaginatedNotificationsResponse {
  items: NotificationItem[];
  total: number;
  unread_count: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface UnreadCountResponse {
  unread_count: number;
}

export interface MarkNotificationReadResponse {
  id: string;
  is_read: boolean;
  read_at: string;
}

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  department: string | null;
  role: string;
  is_active: boolean;
}
