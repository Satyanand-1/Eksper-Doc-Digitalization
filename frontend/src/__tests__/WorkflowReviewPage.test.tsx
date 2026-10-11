import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import WorkflowReviewPage from "@/app/workflows/[workflowId]/page";
import { AuthProvider } from "@/context/AuthContext";
import { NotificationProvider } from "@/context/NotificationContext";
import { WorkflowDetailResponse } from "@/types/workflow";
import { api, ApiError } from "@/lib/api";

jest.mock("@/lib/api", () => {
  const original = jest.requireActual("@/lib/api");
  return {
    ...original,
    api: {
      getCurrentUser: jest.fn(),
      getNotifications: jest.fn(),
      getUnreadCount: jest.fn(),
      getWorkflowDetail: jest.fn(),
      submitWorkflowDecision: jest.fn(),
    },
    getStoredToken: jest.fn(() => "mock-jwt-token"),
  };
});

jest.mock("next/navigation", () => ({
  useParams: () => ({ workflowId: "wf-123" }),
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

const mockPendingWorkflow: WorkflowDetailResponse = {
  id: "wf-123",
  document_id: "doc-999",
  state: "pending",
  submitted_at: "2026-10-10T14:00:00Z",
  submission_comments: "Please inspect the attached budget spreadsheet.",
  submitter: {
    id: "user-456",
    email: "analyst@example.com",
    full_name: "Bob Submitter",
    department: "Finance",
  },
  document: {
    id: "doc-999",
    document_reference: "DOC-2026-0042",
    title: "Annual Operational Budget",
    subject: "Operational expenses breakdown for FY2027",
    department: "Finance",
    classification: "official",
    status: "under_review",
    current_version: {
      id: "ver-1",
      version_number: 1,
      original_filename: "budget_v1.pdf",
      mime_type: "application/pdf",
      file_size_bytes: 204800,
      extraction_status: "completed",
      created_at: "2026-10-10T13:50:00Z",
    },
  },
  assignments: [
    {
      id: "assign-1",
      workflow_id: "wf-123",
      assigned_approver_id: "approver-123",
      assigned_at: "2026-10-10T14:00:00Z",
      decision: null,
      decided_at: null,
      decision_comments: null,
    },
  ],
};

const mockApprovedWorkflow: WorkflowDetailResponse = {
  ...mockPendingWorkflow,
  state: "approved",
  document: {
    ...mockPendingWorkflow.document,
    status: "active",
  },
  assignments: [
    {
      id: "assign-1",
      workflow_id: "wf-123",
      assigned_approver_id: "approver-123",
      assigned_at: "2026-10-10T14:00:00Z",
      decision: "approved",
      decided_at: "2026-10-10T14:30:00Z",
      decision_comments: "Approved without reservation.",
    },
  ],
};

describe("WorkflowReviewPage", () => {
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
          <WorkflowReviewPage />
        </NotificationProvider>
      </AuthProvider>
    );
  };

  test("shows authentication required when user is not signed in", async () => {
    (api.getCurrentUser as jest.Mock).mockRejectedValue(new Error("No token"));

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText("Authentication Required")).toBeInTheDocument();
    });
  });

  test("renders document and workflow metadata for pending review", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockApproverUser);
    (api.getWorkflowDetail as jest.Mock).mockResolvedValue(mockPendingWorkflow);

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText("DOC-2026-0042")).toBeInTheDocument();
      expect(screen.getByText("Annual Operational Budget")).toBeInTheDocument();
      expect(screen.getByText("budget_v1.pdf")).toBeInTheDocument();
      expect(screen.getByText("Bob Submitter")).toBeInTheDocument();
      expect(screen.getByTestId("approve-button")).toBeInTheDocument();
      expect(screen.getByTestId("reject-button")).toBeInTheDocument();
    });
  });

  test("approves document with optional comment", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockApproverUser);
    (api.getWorkflowDetail as jest.Mock)
      .mockResolvedValueOnce(mockPendingWorkflow)
      .mockResolvedValueOnce(mockApprovedWorkflow);

    (api.submitWorkflowDecision as jest.Mock).mockResolvedValue({
      workflow_id: "wf-123",
      document_id: "doc-999",
      document_reference: "DOC-2026-0042",
      document_status: "active",
      workflow_state: "approved",
      decision: "approved",
      decided_by_id: "approver-123",
      decided_at: "2026-10-10T14:35:00Z",
      comments: "Budget figures verified.",
    });

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByTestId("approve-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("approve-button"));

    expect(screen.getByTestId("decision-modal")).toBeInTheDocument();
    expect(screen.getByText("Confirm Approval")).toBeInTheDocument();

    const textarea = screen.getByTestId("decision-comments-input");
    fireEvent.change(textarea, { target: { value: "Budget figures verified." } });

    fireEvent.click(screen.getByTestId("submit-decision-button"));

    await waitFor(() => {
      expect(api.submitWorkflowDecision).toHaveBeenCalledWith("wf-123", {
        decision: "approved",
        comments: "Budget figures verified.",
      });
      expect(screen.getByTestId("decision-success-banner")).toBeInTheDocument();
    });
  });

  test("validates mandatory comments when rejecting a document", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockApproverUser);
    (api.getWorkflowDetail as jest.Mock).mockResolvedValue(mockPendingWorkflow);

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByTestId("reject-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("reject-button"));

    expect(screen.getByTestId("decision-modal")).toBeInTheDocument();
    expect(screen.getByText("Confirm Rejection")).toBeInTheDocument();

    // Try submitting without any comments
    fireEvent.click(screen.getByTestId("submit-decision-button"));

    await waitFor(() => {
      expect(screen.getByTestId("modal-validation-error")).toBeInTheDocument();
      expect(screen.getByText(/A comment is mandatory when rejecting/)).toBeInTheDocument();
      expect(api.submitWorkflowDecision).not.toHaveBeenCalled();
    });

    // Provide non-empty comments and submit successfully
    (api.submitWorkflowDecision as jest.Mock).mockResolvedValue({
      workflow_id: "wf-123",
      document_id: "doc-999",
      document_reference: "DOC-2026-0042",
      document_status: "draft",
      workflow_state: "rejected",
      decision: "rejected",
      decided_by_id: "approver-123",
      decided_at: "2026-10-10T14:40:00Z",
      comments: "Missing department head signature.",
    });

    const textarea = screen.getByTestId("decision-comments-input");
    fireEvent.change(textarea, { target: { value: "Missing department head signature." } });

    fireEvent.click(screen.getByTestId("submit-decision-button"));

    await waitFor(() => {
      expect(api.submitWorkflowDecision).toHaveBeenCalledWith("wf-123", {
        decision: "rejected",
        comments: "Missing department head signature.",
      });
    });
  });

  test("handles 409 conflict when workflow was already decided", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockApproverUser);
    (api.getWorkflowDetail as jest.Mock).mockResolvedValue(mockPendingWorkflow);
    (api.submitWorkflowDecision as jest.Mock).mockRejectedValue(
      new ApiError("Workflow conflict", 409)
    );

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByTestId("approve-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("approve-button"));
    fireEvent.click(screen.getByTestId("submit-decision-button"));

    await waitFor(() => {
      expect(screen.getByTestId("modal-api-error")).toBeInTheDocument();
      expect(
        screen.getByText(/This review workflow has already been decided or cancelled/)
      ).toBeInTheDocument();
    });
  });

  test("handles 404 not found error cleanly", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockApproverUser);
    (api.getWorkflowDetail as jest.Mock).mockRejectedValue(
      new ApiError("Workflow not found", 404)
    );

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByTestId("workflow-error-banner")).toBeInTheDocument();
      expect(
        screen.getByText(/Review workflow not found or you are not authorized/)
      ).toBeInTheDocument();
    });
  });

  test("renders decided state and hides decision buttons when workflow is already approved", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockApproverUser);
    (api.getWorkflowDetail as jest.Mock).mockResolvedValue(mockApprovedWorkflow);

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByTestId("workflow-decided-banner")).toBeInTheDocument();
      expect(screen.getByText("Approved without reservation.")).toBeInTheDocument();
      expect(screen.queryByTestId("approve-button")).not.toBeInTheDocument();
      expect(screen.queryByTestId("reject-button")).not.toBeInTheDocument();
    });
  });
});
