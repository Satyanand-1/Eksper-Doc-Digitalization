import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import RetentionManagementPage from "@/app/retention/page";
import { AuthProvider } from "@/context/AuthContext";
import { api } from "@/lib/api";

// Mock API client
jest.mock("@/lib/api", () => {
  const original = jest.requireActual("@/lib/api");
  return {
    ...original,
    api: {
      getCurrentUser: jest.fn(),
      getDisposalEligibility: jest.fn(),
      listRetentionRules: jest.fn(),
      createRetentionRule: jest.fn(),
      setRetentionRuleStatus: jest.fn(),
      listDocumentLegalHolds: jest.fn(),
      placeLegalHold: jest.fn(),
      releaseLegalHold: jest.fn(),
    },
    getStoredToken: jest.fn(() => "mock-jwt-token"),
  };
});

const mockAdminUser = {
  id: "admin-uuid",
  email: "admin@edrms.test",
  full_name: "System Admin",
  role: "admin",
  department: "IT",
  is_active: true,
};

const mockReadOnlyUser = {
  id: "readonly-uuid",
  email: "readonly@edrms.test",
  full_name: "Read Only",
  role: "read_only",
  department: "IT",
  is_active: true,
};

const mockDisposalItems = [
  {
    document_id: "doc-1",
    document_reference: "DOC-2026-0001",
    title: "Financial Audit 2020",
    department: "Finance",
    classification: "Audit",
    status: "active",
    created_at: "2020-01-01T00:00:00Z",
    retention_rule_id: "rule-1",
    retention_rule_name: "Audit 5 Year Rule",
    retention_start_date: "2020-01-01T00:00:00Z",
    retention_end_date: "2025-01-01T00:00:00Z",
    is_expired: true,
    has_active_hold: false,
    active_hold_count: 0,
    eligibility_status: "eligible_for_review",
    eligibility_explanation: "Retention period expired. Eligible for formal disposal review.",
  },
  {
    document_id: "doc-2",
    document_reference: "DOC-2026-0002",
    title: "Litigation Evidence Memo",
    department: "Legal",
    classification: "Legal",
    status: "active",
    created_at: "2021-01-01T00:00:00Z",
    retention_rule_id: "rule-2",
    retention_rule_name: "Legal 3 Year Rule",
    retention_start_date: "2021-01-01T00:00:00Z",
    retention_end_date: "2024-01-01T00:00:00Z",
    is_expired: true,
    has_active_hold: true,
    active_hold_count: 1,
    eligibility_status: "on_hold",
    eligibility_explanation: "Protected by active legal hold.",
  },
];

const mockRules = [
  {
    id: "rule-1",
    name: "Audit 5 Year Rule",
    description: "Financial audits",
    classification: "Audit",
    retention_period_unit: "years",
    retention_period_value: 5,
    trigger_event: "creation",
    is_active: true,
    created_by_id: "admin-uuid",
    updated_by_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

describe("RetentionManagementPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("1. Renders access denied for unauthorized read_only role", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockReadOnlyUser);

    render(
      <AuthProvider>
        <RetentionManagementPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Access Denied")).toBeInTheDocument();
    });
  });

  test("2. Renders disposal eligibility table for authorized administrator", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getDisposalEligibility as jest.Mock).mockResolvedValue({
      items: mockDisposalItems,
      page: 1,
      page_size: 15,
      total: 2,
      total_pages: 1,
    });

    render(
      <AuthProvider>
        <RetentionManagementPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Records Retention Governance")).toBeInTheDocument();
      expect(screen.getByText("Financial Audit 2020")).toBeInTheDocument();
      expect(screen.getAllByText("Eligible for Review").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Litigation Evidence Memo")).toBeInTheDocument();
      expect(screen.getByText("Legal Hold")).toBeInTheDocument();
    });
  });

  test("3. Switches to retention schedules tab and loads rules", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getDisposalEligibility as jest.Mock).mockResolvedValue({
      items: [],
      page: 1,
      page_size: 15,
      total: 0,
      total_pages: 1,
    });
    (api.listRetentionRules as jest.Mock).mockResolvedValue({
      items: mockRules,
      page: 1,
      page_size: 15,
      total: 1,
      total_pages: 1,
    });

    render(
      <AuthProvider>
        <RetentionManagementPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Retention Schedules" })).toBeInTheDocument();
    });

    const rulesTabBtn = screen.getByRole("button", { name: "Retention Schedules" });
    fireEvent.click(rulesTabBtn);

    await waitFor(() => {
      expect(screen.getByText("Audit 5 Year Rule")).toBeInTheDocument();
      expect(screen.getByText("5 years")).toBeInTheDocument();
    });
  });

  test("4. Opens legal holds modal and displays existing holds", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getDisposalEligibility as jest.Mock).mockResolvedValue({
      items: mockDisposalItems,
      page: 1,
      page_size: 15,
      total: 2,
      total_pages: 1,
    });
    (api.listDocumentLegalHolds as jest.Mock).mockResolvedValue([
      {
        id: "hold-1",
        document_id: "doc-2",
        hold_reason: "Grand jury subpoena pending.",
        status: "active",
        placed_by_id: "admin-uuid",
        placed_at: "2026-02-01T00:00:00Z",
        released_by_id: null,
        released_at: null,
        release_reason: null,
      },
    ]);

    render(
      <AuthProvider>
        <RetentionManagementPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Litigation Evidence Memo")).toBeInTheDocument();
    });

    const holdBtns = screen.getAllByRole("button", { name: "Holds & Governance" });
    fireEvent.click(holdBtns[1]);

    await waitFor(() => {
      expect(screen.getByText("Legal Holds & Record Governance")).toBeInTheDocument();
      expect(screen.getByText("Grand jury subpoena pending.")).toBeInTheDocument();
      expect(screen.getByText("Release Hold")).toBeInTheDocument();
    });
  });
});
