import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import NotificationCenterPage from "@/app/notifications/page";
import { AuthProvider } from "@/context/AuthContext";
import { NotificationProvider } from "@/context/NotificationContext";
import { NotificationItem } from "@/types/notification";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => {
  const original = jest.requireActual("@/lib/api");
  return {
    ...original,
    api: {
      getCurrentUser: jest.fn(),
      getNotifications: jest.fn(),
      getUnreadCount: jest.fn(),
      markNotificationAsRead: jest.fn(),
    },
    getStoredToken: jest.fn(() => "mock-jwt-token"),
  };
});

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
  }),
}));

const mockUser = {
  id: "user-123",
  email: "analyst@example.com",
  full_name: "Jane Analyst",
  department: "Legal",
  role: "department_user",
  is_active: true,
};

const mockNotifications: NotificationItem[] = [
  {
    id: "notif-1",
    recipient_id: "user-123",
    notification_type: "workflow_submitted",
    title: "Document review required: DOC-2026-001",
    message: "Document 'Contract' has been submitted for your review.",
    document_id: "doc-1",
    workflow_id: "wf-1",
    is_read: false,
    read_at: null,
    created_at: "2026-10-10T14:00:00Z",
  },
  {
    id: "notif-2",
    recipient_id: "user-123",
    notification_type: "workflow_rejected",
    title: "Document review rejected: DOC-2026-002",
    message: "Document was rejected and returned to draft.",
    document_id: "doc-2",
    workflow_id: "wf-2",
    is_read: true,
    read_at: "2026-10-10T14:30:00Z",
    created_at: "2026-10-10T13:00:00Z",
  },
];

describe("NotificationCenterPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockUser);
    (api.getUnreadCount as jest.Mock).mockResolvedValue({ unread_count: 1 });
    (api.getNotifications as jest.Mock).mockResolvedValue({
      items: mockNotifications,
      total: 2,
      unread_count: 1,
      page: 1,
      page_size: 10,
      total_pages: 1,
    });
    (api.markNotificationAsRead as jest.Mock).mockResolvedValue({
      id: "notif-1",
      is_read: true,
      read_at: "2026-10-10T15:00:00Z",
    });
  });

  it("renders page header, unread badge, and notification list", async () => {
    render(
      <AuthProvider>
        <NotificationProvider>
          <NotificationCenterPage />
        </NotificationProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Notification Center" })).toBeInTheDocument();
      expect(screen.getByText("1 unread")).toBeInTheDocument();
      expect(screen.getByText("Document review required: DOC-2026-001")).toBeInTheDocument();
      expect(screen.getByText("Document review rejected: DOC-2026-002")).toBeInTheDocument();
    });
  });

  it("toggles unread-only filter and calls api with unreadOnly flag", async () => {
    render(
      <AuthProvider>
        <NotificationProvider>
          <NotificationCenterPage />
        </NotificationProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("All Notifications")).toBeInTheDocument();
    });

    const filterBtn = screen.getByRole("button", { name: /All Notifications/i });
    fireEvent.click(filterBtn);

    await waitFor(() => {
      expect(api.getNotifications).toHaveBeenCalledWith(1, 10, true);
    });
  });

  it("marks notification as read and shows success banner", async () => {
    render(
      <AuthProvider>
        <NotificationProvider>
          <NotificationCenterPage />
        </NotificationProvider>
      </AuthProvider>
    );

    const markReadBtn = await screen.findByRole("button", { name: /Mark as read/i });
    fireEvent.click(markReadBtn);

    await waitFor(() => {
      expect(api.markNotificationAsRead).toHaveBeenCalledWith("notif-1");
      expect(screen.getByText("Notification marked as read.")).toBeInTheDocument();
    });
  });

  it("renders empty state when there are no notifications", async () => {
    (api.getNotifications as jest.Mock).mockResolvedValue({
      items: [],
      total: 0,
      unread_count: 0,
      page: 1,
      page_size: 10,
      total_pages: 0,
    });

    render(
      <AuthProvider>
        <NotificationProvider>
          <NotificationCenterPage />
        </NotificationProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("No notifications yet")).toBeInTheDocument();
    });
  });

  it("renders error state when notification fetching fails", async () => {
    (api.getNotifications as jest.Mock).mockRejectedValue(new Error("Network connection lost"));

    render(
      <AuthProvider>
        <NotificationProvider>
          <NotificationCenterPage />
        </NotificationProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Network connection lost")).toBeInTheDocument();
    });
  });
});
