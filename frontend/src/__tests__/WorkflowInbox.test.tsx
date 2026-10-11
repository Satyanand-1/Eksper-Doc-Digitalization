import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ApproverInboxPage from "@/app/workflows/inbox/page";
import { AuthProvider } from "@/context/AuthContext";
import { NotificationProvider } from "@/context/NotificationContext";
import { PaginatedAssignmentsResponse } from "@/types/workflow";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => {
  const original = jest.requireActual("@/lib/api");
  return {
    ...original,
    api: {
      getCurrentUser: jest.fn(),
      getNotifications: jest.fn(),
      getUnreadCount: jest.fn(),
      getMyAssignments: jest.fn(),
    },
    getStoredToken: jest.fn(() => "mock-jwt-token"),
  };
});

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
  }),
}));

const mockApproverUser = {
  id: "approver-123",
  email: "approver@example.com",
  full_name: "Alice Approver",
  department: "Finance",
  role: "approver",
  is_active: true,
};

const mockDepartmentUser = {
  id: "user-456",
  email: "user@example.com",
  full_name: "Bob Submitter",
  department: "Finance",
  role: "department_user",
  is_active: true,
};

const mockAssignmentsResponse: PaginatedAssignmentsResponse = {
  items: [
    {
      assignment_id: "assign-1",
      workflow_id: "wf-1",
      workflow_state: "pending",
      submitted_at: "2026-10-10T12:00:00Z",
      submission_comments: "Please review the Q4 financial budget.",
      submitter: {
        id: "user-456",
        email: "user@example.com",
        full_name: "Bob Submitter",
        department: "Finance",
      },
      document: {
        id: "doc-1",
        document_reference: "DOC-2026-0001",
        title: "Q4 Financial Budget Report",
        department: "Finance",
        classification: "official",
        status: "under_review",
        created_at: "2026-10-10T11:30:00Z",
      },
    },
  ],
  total: 1,
  page: 1,
  page_size: 10,
  total_pages: 1,
};

describe("ApproverInboxPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.getUnreadCount as jest.Mock).mockResolvedValue({ unread_count: 0 });
    (api.getNotifications as jest.Mock).mockResolvedValue({
      items: [],
      total: 0,
      unread_count: 0,
      page: 1,
      page_size: 5,
      total_pages: 0,
    });
  });

  const renderWithProviders = () => {
    return render(
      <AuthProvider>
        <NotificationProvider>
          <ApproverInboxPage />
        </NotificationProvider>
      </AuthProvider>
    );
  };

  test("shows authentication required when user is not logged in", async () => {
    (api.getCurrentUser as jest.Mock).mockRejectedValue(new Error("No token"));

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText("Authentication Required")).toBeInTheDocument();
    });
  });

  test("shows access restricted when user role is not approver", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockDepartmentUser);

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText("Access Restricted")).toBeInTheDocument();
      expect(screen.getByText(/Only users with the/)).toBeInTheDocument();
    });
  });

  test("renders pending review assignments for approver role", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockApproverUser);
    (api.getMyAssignments as jest.Mock).mockResolvedValue(mockAssignmentsResponse);

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText("Review Inbox")).toBeInTheDocument();
      expect(screen.getByText("DOC-2026-0001")).toBeInTheDocument();
      expect(screen.getByText("Q4 Financial Budget Report")).toBeInTheDocument();
      expect(screen.getByText("Bob Submitter")).toBeInTheDocument();
      expect(screen.getByText("Please review the Q4 financial budget.")).toBeInTheDocument();
      expect(screen.getByText("Open Review")).toBeInTheDocument();
      expect(screen.getByTestId("pending-count-badge")).toHaveTextContent("1 pending review");
    });
  });

  test("renders empty state when approver has zero assignments", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockApproverUser);
    (api.getMyAssignments as jest.Mock).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 10,
      total_pages: 0,
    });

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText("No pending review assignments")).toBeInTheDocument();
      expect(screen.getByTestId("pending-count-badge")).toHaveTextContent("0 pending reviews");
    });
  });

  test("displays error message when fetching assignments fails", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockApproverUser);
    (api.getMyAssignments as jest.Mock).mockRejectedValue(new Error("Network connection lost"));

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText("Network connection lost")).toBeInTheDocument();
    });
  });

  test("supports pagination navigation when multiple pages exist", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockApproverUser);
    (api.getMyAssignments as jest.Mock).mockResolvedValue({
      ...mockAssignmentsResponse,
      total: 15,
      total_pages: 2,
    });

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText(/Showing page/)).toBeInTheDocument();
    });

    const nextButton = screen.getByRole("button", { name: /Next/i });
    expect(nextButton).toBeEnabled();

    fireEvent.click(nextButton);

    await waitFor(() => {
      expect(api.getMyAssignments).toHaveBeenCalledWith(2, 10);
    });
  });
});
