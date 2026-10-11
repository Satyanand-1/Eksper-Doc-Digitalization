import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { NotificationBell } from "@/components/NotificationBell";
import { NotificationCard } from "@/components/NotificationCard";
import { AuthProvider } from "@/context/AuthContext";
import { NotificationProvider } from "@/context/NotificationContext";
import { NotificationItem } from "@/types/notification";
import { api } from "@/lib/api";

// Mock api methods
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

// Mock next/navigation
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

const sampleNotifications: NotificationItem[] = [
  {
    id: "notif-1",
    recipient_id: "user-123",
    notification_type: "workflow_submitted",
    title: "Document review required: DOC-2026-001",
    message: "Document 'Agreement' has been submitted for your review.",
    document_id: "doc-1",
    workflow_id: "wf-1",
    is_read: false,
    read_at: null,
    created_at: "2026-10-10T14:00:00Z",
  },
  {
    id: "notif-2",
    recipient_id: "user-123",
    notification_type: "workflow_approved",
    title: "Document approved: DOC-2026-002",
    message: "Document 'Policy' has been approved and activated.",
    document_id: "doc-2",
    workflow_id: "wf-2",
    is_read: true,
    read_at: "2026-10-10T14:30:00Z",
    created_at: "2026-10-10T13:00:00Z",
  },
];

describe("Notification Components", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockUser);
    (api.getUnreadCount as jest.Mock).mockResolvedValue({ unread_count: 3 });
    (api.getNotifications as jest.Mock).mockResolvedValue({
      items: sampleNotifications,
      total: 2,
      unread_count: 1,
      page: 1,
      page_size: 10,
      total_pages: 1,
    });
  });

  describe("NotificationBell", () => {
    it("renders unread badge when unread count is greater than zero", async () => {
      render(
        <AuthProvider>
          <NotificationProvider>
            <NotificationBell />
          </NotificationProvider>
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId("unread-badge")).toBeInTheDocument();
        expect(screen.getByTestId("unread-badge")).toHaveTextContent("3");
      });
    });

    it("hides badge when unread count is zero", async () => {
      (api.getUnreadCount as jest.Mock).mockResolvedValue({ unread_count: 0 });

      render(
        <AuthProvider>
          <NotificationProvider>
            <NotificationBell />
          </NotificationProvider>
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.queryByTestId("unread-badge")).not.toBeInTheDocument();
      });
    });

    it("displays 99+ when unread count exceeds 99", async () => {
      (api.getUnreadCount as jest.Mock).mockResolvedValue({ unread_count: 120 });

      render(
        <AuthProvider>
          <NotificationProvider>
            <NotificationBell />
          </NotificationProvider>
        </AuthProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId("unread-badge")).toHaveTextContent("99+");
      });
    });

    it("opens dropdown on click and displays quick notifications", async () => {
      render(
        <AuthProvider>
          <NotificationProvider>
            <NotificationBell />
          </NotificationProvider>
        </AuthProvider>
      );

      const bellButton = await screen.findByRole("button", { name: /Notifications/i });
      fireEvent.click(bellButton);

      await waitFor(() => {
        expect(screen.getByTestId("notification-dropdown")).toBeInTheDocument();
        expect(screen.getByText("Document review required: DOC-2026-001")).toBeInTheDocument();
      });
    });
  });

  describe("NotificationCard", () => {
    it("renders unread card with action button and triggers mark as read", async () => {
      const onMarkAsRead = jest.fn().mockResolvedValue(undefined);
      const onNavigate = jest.fn();

      render(
        <NotificationCard
          notification={sampleNotifications[0]}
          onMarkAsRead={onMarkAsRead}
          onNavigate={onNavigate}
        />
      );

      expect(screen.getByText("Document review required: DOC-2026-001")).toBeInTheDocument();
      expect(screen.getByText("NEW")).toBeInTheDocument();
      expect(screen.getByText("Review Required")).toBeInTheDocument();

      const readBtn = screen.getByRole("button", { name: /Mark as read/i });
      fireEvent.click(readBtn);

      expect(onMarkAsRead).toHaveBeenCalledWith("notif-1");
    });

    it("renders read notification without mark as read button", () => {
      const onMarkAsRead = jest.fn();

      render(
        <NotificationCard
          notification={sampleNotifications[1]}
          onMarkAsRead={onMarkAsRead}
        />
      );

      expect(screen.getByText("Document approved: DOC-2026-002")).toBeInTheDocument();
      expect(screen.queryByText("NEW")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Mark as read/i })).not.toBeInTheDocument();
    });

    it("calls onNavigate when view details button is clicked", () => {
      const onMarkAsRead = jest.fn();
      const onNavigate = jest.fn();

      render(
        <NotificationCard
          notification={sampleNotifications[0]}
          onMarkAsRead={onMarkAsRead}
          onNavigate={onNavigate}
        />
      );

      const viewBtn = screen.getByRole("button", { name: /View details/i });
      fireEvent.click(viewBtn);

      expect(onNavigate).toHaveBeenCalledWith(sampleNotifications[0]);
    });
  });
});
