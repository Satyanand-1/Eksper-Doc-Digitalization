import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import DocumentDetailPage from "@/app/documents/[documentId]/page";
import DocumentsPage from "@/app/documents/page";
import { AuthProvider } from "@/context/AuthContext";
import { NotificationProvider } from "@/context/NotificationContext";
import {
  DocumentDetailResponse,
  DocumentVersionResponse,
  WorkflowSubmissionResponse,
} from "@/types/document";
import { DocumentWorkflowHistoryResponse } from "@/types/workflow";
import { EligibleApprover } from "@/types/user";
import { api, ApiError } from "@/lib/api";

jest.mock("@/lib/api", () => {
  const original = jest.requireActual("@/lib/api");
  return {
    ...original,
    api: {
      getCurrentUser: jest.fn(),
      getNotifications: jest.fn(),
      getUnreadCount: jest.fn(),
      getDocument: jest.fn(),
      getDocumentVersions: jest.fn(),
      submitForReview: jest.fn(),
      getDocumentWorkflowHistory: jest.fn(),
      getDocuments: jest.fn(),
      getEligibleApprovers: jest.fn(),
    },
    getStoredToken: jest.fn(() => "mock-jwt-token"),
  };
});

jest.mock("next/navigation", () => ({
  useParams: () => ({ documentId: "doc-123" }),
  useRouter: () => ({
    push: jest.fn(),
  }),
}));

const mockDeptUser = {
  id: "user-legal-1",
  email: "legal.user@example.com",
  full_name: "Leslie Legal",
  department: "Legal",
  role: "department_user",
  is_active: true,
};

const mockApproverUser = {
  id: "approver-legal-1",
  email: "approver.legal@example.com",
  full_name: "Arthur Approver",
  department: "Legal",
  role: "approver",
  is_active: true,
};

const mockDraftDocument: DocumentDetailResponse = {
  id: "doc-123",
  document_reference: "DOC-2026-0088",
  title: "Service Level Agreement 2026",
  subject: "Master SLA agreement for legal vendors",
  department: "Legal",
  classification: "confidential",
  mime_type: "application/pdf",
  status: "draft",
  created_by_id: "user-legal-1",
  creator: {
    id: "user-legal-1",
    email: "legal.user@example.com",
    full_name: "Leslie Legal",
    department: "Legal",
  },
  created_at: "2026-10-10T10:00:00Z",
  updated_at: "2026-10-10T10:00:00Z",
  archived_at: null,
  available_versions: [1],
  version_count: 1,
};

const mockUnderReviewDocument: DocumentDetailResponse = {
  ...mockDraftDocument,
  status: "under_review",
};

const mockVersion: DocumentVersionResponse = {
  id: "ver-1",
  document_id: "doc-123",
  version_number: 1,
  original_filename: "sla_final.pdf",
  mime_type: "application/pdf",
  file_size_bytes: 524288,
  file_hash_sha256: "abc123hash",
  extraction_status: "completed",
  extraction_completed_at: "2026-10-10T10:05:00Z",
  extraction_error: null,
  created_by_id: "user-legal-1",
  creator: null,
  created_at: "2026-10-10T10:00:00Z",
};

const mockEmptyHistory: DocumentWorkflowHistoryResponse = {
  document_id: "doc-123",
  document_reference: "DOC-2026-0088",
  document_status: "draft",
  total_attempts: 0,
  attempts: [],
};

const mockMultiAttemptHistory: DocumentWorkflowHistoryResponse = {
  document_id: "doc-123",
  document_reference: "DOC-2026-0088",
  document_status: "draft",
  total_attempts: 2,
  attempts: [
    {
      workflow_id: "wf-attempt-1",
      state: "rejected",
      submitted_at: "2026-10-09T09:00:00Z",
      submission_comments: "Initial draft for review",
      submitter: {
        id: "user-legal-1",
        email: "legal.user@example.com",
        full_name: "Leslie Legal",
        department: "Legal",
      },
      cancelled_by: null,
      cancelled_at: null,
      cancellation_comments: null,
      assignments: [
        {
          id: "assign-1",
          workflow_id: "wf-attempt-1",
          assigned_approver: {
            id: "approver-legal-1",
            email: "approver.legal@example.com",
            full_name: "Arthur Approver",
            department: "Legal",
          },
          assigned_at: "2026-10-09T09:00:00Z",
          decision: "rejected",
          decided_at: "2026-10-09T11:00:00Z",
          decision_comments: "Section 4 terms must be revised.",
        },
      ],
    },
    {
      workflow_id: "wf-attempt-2",
      state: "cancelled",
      submitted_at: "2026-10-09T14:00:00Z",
      submission_comments: "Second submission",
      submitter: {
        id: "user-legal-1",
        email: "legal.user@example.com",
        full_name: "Leslie Legal",
        department: "Legal",
      },
      cancelled_by: {
        id: "user-legal-1",
        email: "legal.user@example.com",
        full_name: "Leslie Legal",
        department: "Legal",
      },
      cancelled_at: "2026-10-09T14:30:00Z",
      cancellation_comments: "Withdrawn to attach appendix B.",
      assignments: [],
    },
  ],
};

const mockEligibleApprovers: EligibleApprover[] = [
  {
    id: "11111111-2222-3333-4444-555555555555",
    email: "arthur.approver@example.com",
    full_name: "Arthur Approver",
    department: "Legal",
  },
  {
    id: "22222222-3333-4444-5555-666666666666",
    email: "beatrice.approver@example.com",
    full_name: "Beatrice Approver",
    department: "Legal",
  },
];

describe("Document Review Submission Flow & Approver Selector (Task 5.8 & 5.9)", () => {
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
    (api.getEligibleApprovers as jest.Mock).mockResolvedValue(mockEligibleApprovers);
  });

  const renderDetailPage = () => {
    return render(
      <AuthProvider>
        <NotificationProvider>
          <DocumentDetailPage />
        </NotificationProvider>
      </AuthProvider>
    );
  };

  test("1. Eligible draft document displays the submission action", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockDeptUser);
    (api.getDocument as jest.Mock).mockResolvedValue(mockDraftDocument);
    (api.getDocumentVersions as jest.Mock).mockResolvedValue([mockVersion]);
    (api.getDocumentWorkflowHistory as jest.Mock).mockResolvedValue(mockEmptyHistory);

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText("Service Level Agreement 2026")).toBeInTheDocument();
      expect(screen.getByTestId("submit-for-review-button")).toBeInTheDocument();
      expect(screen.queryByTestId("submission-ineligible-notice")).not.toBeInTheDocument();
    });
  });

  test("2. Ineligible document (under_review or active) does not offer submission and explains status", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockDeptUser);
    (api.getDocument as jest.Mock).mockResolvedValue(mockUnderReviewDocument);
    (api.getDocumentVersions as jest.Mock).mockResolvedValue([mockVersion]);
    (api.getDocumentWorkflowHistory as jest.Mock).mockResolvedValue(mockEmptyHistory);

    renderDetailPage();

    await waitFor(() => {
      expect(screen.queryByTestId("submit-for-review-button")).not.toBeInTheDocument();
      expect(screen.getByTestId("submission-ineligible-notice")).toBeInTheDocument();
      expect(screen.getByText(/Only draft documents can be submitted for review/)).toBeInTheDocument();
    });
  });

  test("3. Unauthorized role (approver) does not receive submission controls", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockApproverUser);
    (api.getDocument as jest.Mock).mockResolvedValue(mockDraftDocument);
    (api.getDocumentVersions as jest.Mock).mockResolvedValue([mockVersion]);
    (api.getDocumentWorkflowHistory as jest.Mock).mockResolvedValue(mockEmptyHistory);

    renderDetailPage();

    await waitFor(() => {
      expect(screen.queryByTestId("submit-for-review-button")).not.toBeInTheDocument();
      expect(screen.getByTestId("submission-ineligible-notice")).toBeInTheDocument();
      expect(screen.getByText(/Role 'approver' does not have document review submission rights/)).toBeInTheDocument();
    });
  });

  test("4. UUID text input is replaced by searchable approver directory selector displaying names & departments", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockDeptUser);
    (api.getDocument as jest.Mock).mockResolvedValue(mockDraftDocument);
    (api.getDocumentVersions as jest.Mock).mockResolvedValue([mockVersion]);
    (api.getDocumentWorkflowHistory as jest.Mock).mockResolvedValue(mockEmptyHistory);

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByTestId("submit-for-review-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("submit-for-review-button"));
    expect(screen.getByTestId("submit-for-review-modal")).toBeInTheDocument();

    // Confirm raw UUID input does not exist
    expect(screen.queryByTestId("approver-id-input")).not.toBeInTheDocument();

    // Search input and approver options exist
    expect(screen.getByTestId("approver-search-input")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Arthur Approver")).toBeInTheDocument();
      expect(screen.getByText("Beatrice Approver")).toBeInTheDocument();
      expect(screen.getByText("arthur.approver@example.com")).toBeInTheDocument();
    });
  });

  test("5. Approver search query triggers filtered directory search", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockDeptUser);
    (api.getDocument as jest.Mock).mockResolvedValue(mockDraftDocument);
    (api.getDocumentVersions as jest.Mock).mockResolvedValue([mockVersion]);
    (api.getDocumentWorkflowHistory as jest.Mock).mockResolvedValue(mockEmptyHistory);

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByTestId("submit-for-review-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("submit-for-review-button"));

    await waitFor(() => {
      expect(screen.getByTestId("approver-search-input")).toBeInTheDocument();
    });

    const searchInput = screen.getByTestId("approver-search-input");
    fireEvent.change(searchInput, { target: { value: "Beatrice" } });

    await waitFor(() => {
      expect(api.getEligibleApprovers).toHaveBeenCalledWith({
        document_id: "doc-123",
        q: "Beatrice",
      });
    });
  });

  test("6. Renders empty and error states for approver directory", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockDeptUser);
    (api.getDocument as jest.Mock).mockResolvedValue(mockDraftDocument);
    (api.getDocumentVersions as jest.Mock).mockResolvedValue([mockVersion]);
    (api.getDocumentWorkflowHistory as jest.Mock).mockResolvedValue(mockEmptyHistory);

    // Mock empty approvers
    (api.getEligibleApprovers as jest.Mock).mockResolvedValueOnce([]);

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByTestId("submit-for-review-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("submit-for-review-button"));

    await waitFor(() => {
      expect(screen.getByTestId("approver-empty-state")).toBeInTheDocument();
      expect(screen.getByText("No eligible approvers found")).toBeInTheDocument();
    });
  });

  test("7. Requires valid approver selection before submission can proceed", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockDeptUser);
    (api.getDocument as jest.Mock).mockResolvedValue(mockDraftDocument);
    (api.getDocumentVersions as jest.Mock).mockResolvedValue([mockVersion]);
    (api.getDocumentWorkflowHistory as jest.Mock).mockResolvedValue(mockEmptyHistory);

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByTestId("submit-for-review-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("submit-for-review-button"));

    await waitFor(() => {
      expect(screen.getByText("Arthur Approver")).toBeInTheDocument();
    });

    // Attempt to submit without selecting an approver
    const submitBtn = screen.getByTestId("confirm-submit-button");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByTestId("submission-validation-error")).toBeInTheDocument();
      expect(screen.getByText(/Please select an eligible approver from the directory/)).toBeInTheDocument();
      expect(api.submitForReview).not.toHaveBeenCalled();
    });
  });

  test("8. Selecting an approver sends the correct approver ID and comments to submission API", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockDeptUser);
    (api.getDocument as jest.Mock)
      .mockResolvedValueOnce(mockDraftDocument)
      .mockResolvedValueOnce(mockUnderReviewDocument);
    (api.getDocumentVersions as jest.Mock).mockResolvedValue([mockVersion]);
    (api.getDocumentWorkflowHistory as jest.Mock).mockResolvedValue(mockEmptyHistory);

    const mockSubmissionResponse: WorkflowSubmissionResponse = {
      workflow_id: "wf-new-999",
      document_id: "doc-123",
      document_reference: "DOC-2026-0088",
      document_status: "under_review",
      workflow_state: "pending",
      submitter_id: "user-legal-1",
      submitted_at: "2026-10-10T11:00:00Z",
      comments: "Final draft for executive signoff",
      assignment: {
        id: "assign-new-1",
        workflow_id: "wf-new-999",
        assigned_approver_id: "11111111-2222-3333-4444-555555555555",
        assigned_at: "2026-10-10T11:00:00Z",
        decision: null,
        decided_at: null,
        decision_comments: null,
      },
    };

    (api.submitForReview as jest.Mock).mockResolvedValue(mockSubmissionResponse);

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByTestId("submit-for-review-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("submit-for-review-button"));

    await waitFor(() => {
      expect(screen.getByTestId("approver-option-11111111-2222-3333-4444-555555555555")).toBeInTheDocument();
    });

    // Click Arthur Approver option
    fireEvent.click(screen.getByTestId("approver-option-11111111-2222-3333-4444-555555555555"));

    expect(screen.getByTestId("selected-approver-display")).toHaveTextContent("Arthur Approver");

    fireEvent.change(screen.getByTestId("submission-comments-input"), {
      target: { value: "Final draft for executive signoff" },
    });

    fireEvent.click(screen.getByTestId("confirm-submit-button"));

    await waitFor(() => {
      expect(api.submitForReview).toHaveBeenCalledWith("doc-123", {
        approver_id: "11111111-2222-3333-4444-555555555555",
        comments: "Final draft for executive signoff",
      });
      expect(screen.getByTestId("submission-success-banner")).toBeInTheDocument();
      expect(screen.getByTestId("document-status-pill")).toHaveTextContent("under review");
    });
  });

  test("9. Duplicate submissions are prevented while request is in progress", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockDeptUser);
    (api.getDocument as jest.Mock).mockResolvedValue(mockDraftDocument);
    (api.getDocumentVersions as jest.Mock).mockResolvedValue([mockVersion]);
    (api.getDocumentWorkflowHistory as jest.Mock).mockResolvedValue(mockEmptyHistory);

    let resolveSubmission: (val: any) => void;
    (api.submitForReview as jest.Mock).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSubmission = resolve;
        })
    );

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByTestId("submit-for-review-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("submit-for-review-button"));

    await waitFor(() => {
      expect(screen.getByTestId("approver-option-11111111-2222-3333-4444-555555555555")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("approver-option-11111111-2222-3333-4444-555555555555"));

    const submitBtn = screen.getByTestId("confirm-submit-button");
    fireEvent.click(submitBtn);

    expect(submitBtn).toBeDisabled();
    expect(submitBtn).toHaveTextContent("Submitting...");

    // Second click ignored
    fireEvent.click(submitBtn);
    expect(api.submitForReview).toHaveBeenCalledTimes(1);

    resolveSubmission!({
      workflow_id: "wf-new-999",
      document_id: "doc-123",
      document_reference: "DOC-2026-0088",
      document_status: "under_review",
      workflow_state: "pending",
      submitter_id: "user-legal-1",
      submitted_at: "2026-10-10T11:00:00Z",
      comments: null,
      assignment: { id: "a1", workflow_id: "wf-new-999", assigned_approver_id: "11111111-2222-3333-4444-555555555555", assigned_at: "2026-10-10", decision: null, decided_at: null, decision_comments: null },
    });
  });

  test("10. Handles 409 conflict error cleanly", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockDeptUser);
    (api.getDocument as jest.Mock).mockResolvedValue(mockDraftDocument);
    (api.getDocumentVersions as jest.Mock).mockResolvedValue([mockVersion]);
    (api.getDocumentWorkflowHistory as jest.Mock).mockResolvedValue(mockEmptyHistory);

    (api.submitForReview as jest.Mock).mockRejectedValueOnce(
      new ApiError("Document already has an active review workflow pending.", 409)
    );

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByTestId("submit-for-review-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("submit-for-review-button"));

    await waitFor(() => {
      expect(screen.getByTestId("approver-option-11111111-2222-3333-4444-555555555555")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("approver-option-11111111-2222-3333-4444-555555555555"));
    fireEvent.click(screen.getByTestId("confirm-submit-button"));

    await waitFor(() => {
      expect(screen.getByTestId("submission-api-error")).toBeInTheDocument();
      expect(
        screen.getByText(/Document already has an active review workflow pending/)
      ).toBeInTheDocument();
    });
  });

  test("11. Notification unread count refreshes after successful submission", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockDeptUser);
    (api.getDocument as jest.Mock)
      .mockResolvedValueOnce(mockDraftDocument)
      .mockResolvedValueOnce(mockUnderReviewDocument);
    (api.getDocumentVersions as jest.Mock).mockResolvedValue([mockVersion]);
    (api.getDocumentWorkflowHistory as jest.Mock).mockResolvedValue(mockEmptyHistory);

    (api.submitForReview as jest.Mock).mockResolvedValue({
      workflow_id: "wf-new-999",
      document_id: "doc-123",
      document_reference: "DOC-2026-0088",
      document_status: "under_review",
      workflow_state: "pending",
      submitter_id: "user-legal-1",
      submitted_at: "2026-10-10T11:00:00Z",
      comments: null,
      assignment: { id: "a1", workflow_id: "wf-new-999", assigned_approver_id: "11111111-2222-3333-4444-555555555555", assigned_at: "2026-10-10", decision: null, decided_at: null, decision_comments: null },
    });

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByTestId("submit-for-review-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("submit-for-review-button"));

    await waitFor(() => {
      expect(screen.getByTestId("approver-option-11111111-2222-3333-4444-555555555555")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("approver-option-11111111-2222-3333-4444-555555555555"));
    fireEvent.click(screen.getByTestId("confirm-submit-button"));

    await waitFor(() => {
      expect(api.getUnreadCount).toHaveBeenCalled();
    });
  });

  test("12. Workflow history displays multiple review attempts preserving prior rejected/cancelled history", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockDeptUser);
    (api.getDocument as jest.Mock).mockResolvedValue(mockDraftDocument);
    (api.getDocumentVersions as jest.Mock).mockResolvedValue([mockVersion]);
    (api.getDocumentWorkflowHistory as jest.Mock).mockResolvedValue(mockMultiAttemptHistory);

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByTestId("workflow-history-section")).toBeInTheDocument();
      expect(screen.getByText("Attempt #1")).toBeInTheDocument();
      expect(screen.getByText("Attempt #2")).toBeInTheDocument();
      expect(screen.getByText("Section 4 terms must be revised.")).toBeInTheDocument();
      expect(screen.getByText("Withdrawn to attach appendix B.")).toBeInTheDocument();
    });
  });

  test("13. Documents listing page quick submit works with searchable approver selector", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockDeptUser);
    (api.getDocuments as jest.Mock).mockResolvedValue({
      items: [
        {
          id: "doc-123",
          document_reference: "DOC-2026-0088",
          title: "Service Level Agreement 2026",
          subject: "Master SLA agreement",
          department: "Legal",
          classification: "confidential",
          mime_type: "application/pdf",
          status: "draft",
          created_at: "2026-10-10T10:00:00Z",
          updated_at: "2026-10-10T10:00:00Z",
          version_count: 1,
        },
      ],
      page: 1,
      page_size: 10,
      total: 1,
      total_pages: 1,
    });

    render(
      <AuthProvider>
        <NotificationProvider>
          <DocumentsPage />
        </NotificationProvider>
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Documents Repository")).toBeInTheDocument();
      expect(screen.getByTestId("quick-submit-btn-doc-123")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("quick-submit-btn-doc-123"));
    expect(screen.getByTestId("submit-for-review-modal")).toBeInTheDocument();
    expect(screen.getByTestId("approver-search-input")).toBeInTheDocument();
  });
});
