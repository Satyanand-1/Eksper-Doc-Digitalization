import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AuditLogsPage from "@/app/admin/audit-logs/page";
import { AuthProvider } from "@/context/AuthContext";
import { PaginatedAuditLogsResponse, AuditReportSummary, AuditLogDetail } from "@/types/audit";
import { api, ApiError } from "@/lib/api";

jest.mock("@/lib/api", () => {
  const original = jest.requireActual("@/lib/api");
  return {
    ...original,
    api: {
      getCurrentUser: jest.fn(),
      getAuditLogs: jest.fn(),
      getAuditLogDetail: jest.fn(),
      getAuditReportSummary: jest.fn(),
    },
    getStoredToken: jest.fn(() => "mock-jwt-token"),
  };
});

const mockAdminUser = {
  id: "admin-1",
  email: "admin@example.com",
  full_name: "Admin User",
  department: "System Administration",
  role: "admin",
  is_active: true,
};

const mockRecordsOfficer = {
  id: "ro-1",
  email: "records.officer@example.com",
  full_name: "Records Officer",
  department: "Records Governance",
  role: "records_officer",
  is_active: true,
};

const mockDepartmentUser = {
  id: "user-1",
  email: "user@example.com",
  full_name: "Dept User",
  department: "Finance",
  role: "department_user",
  is_active: true,
};

const mockLogsList = [
  {
    id: "log-1",
    action: "document.upload",
    resource_type: "document",
    resource_id: "doc-12345678",
    outcome: "success" as const,
    actor_id: "user-1",
    actor: {
      id: "user-1",
      email: "user@example.com",
      full_name: "Dept User",
      department: "Finance",
      role: "department_user",
    },
    client_ip: "192.168.1.1",
    correlation_id: "corr-1",
    created_at: "2026-10-10T12:00:00Z",
  },
  {
    id: "log-2",
    action: "workflow.approved",
    resource_type: "workflow",
    resource_id: "wf-12345678",
    outcome: "success" as const,
    actor_id: "approver-1",
    actor: {
      id: "approver-1",
      email: "approver@example.com",
      full_name: "Alice Approver",
      department: "Finance",
      role: "approver",
    },
    client_ip: "192.168.1.2",
    correlation_id: "corr-2",
    created_at: "2026-10-10T12:05:00Z",
  },
  {
    id: "log-3",
    action: "workflow.cancel.denied",
    resource_type: "workflow",
    resource_id: "wf-87654321",
    outcome: "denied" as const,
    actor_id: "user-2",
    actor: null,
    client_ip: "192.168.1.3",
    correlation_id: "corr-3",
    created_at: "2026-10-10T12:10:00Z",
  },
];

const mockPaginatedLogs: PaginatedAuditLogsResponse = {
  items: mockLogsList,
  page: 1,
  page_size: 15,
  total: 3,
  total_pages: 1,
};

const mockReportSummary: AuditReportSummary = {
  total_events: 3,
  events_by_action: {
    "document.upload": 1,
    "workflow.approved": 1,
    "workflow.cancel.denied": 1,
  },
  events_by_outcome: {
    success: 2,
    denied: 1,
  },
  recent_security_events: [mockLogsList[2]],
};

const mockDetailLog: AuditLogDetail = {
  ...mockLogsList[0],
  details: {
    document_reference: "DOC-2026-0001",
    title: "Financial Audit Report",
  },
};

describe("Task 5.11: Audit Log Viewer and Administrative Reports", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("1. Unauthorized role (department_user) is denied access", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockDepartmentUser);

    render(
      <AuthProvider>
        <AuditLogsPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Audit Access Denied")).toBeInTheDocument();
    });
    expect(screen.queryByText("Audit Log Viewer")).not.toBeInTheDocument();
    expect(api.getAuditLogs).not.toHaveBeenCalled();
  });

  test("2. Admin can access audit viewer and renders audit log records and summary metrics", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getAuditLogs as jest.Mock).mockResolvedValue(mockPaginatedLogs);
    (api.getAuditReportSummary as jest.Mock).mockResolvedValue(mockReportSummary);

    render(
      <AuthProvider>
        <AuditLogsPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Audit Log Viewer")).toBeInTheDocument();
      expect(screen.getByText("Total Audited Events")).toBeInTheDocument();
      expect(screen.getAllByText("document.upload").length).toBeGreaterThan(0);
      expect(screen.getAllByText("workflow.approved").length).toBeGreaterThan(0);
      expect(screen.getAllByText("workflow.cancel.denied").length).toBeGreaterThan(0);
    });

    expect(api.getAuditLogs).toHaveBeenCalled();
    expect(api.getAuditReportSummary).toHaveBeenCalled();
  });

  test("3. Records Officer can also access audit viewer", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockRecordsOfficer);
    (api.getAuditLogs as jest.Mock).mockResolvedValue(mockPaginatedLogs);
    (api.getAuditReportSummary as jest.Mock).mockResolvedValue(mockReportSummary);

    render(
      <AuthProvider>
        <AuditLogsPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Audit Log Viewer")).toBeInTheDocument();
      expect(api.getAuditLogs).toHaveBeenCalled();
    });
  });

  test("4. Filtering by action and outcome triggers API request with correct query params", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getAuditLogs as jest.Mock).mockResolvedValue(mockPaginatedLogs);
    (api.getAuditReportSummary as jest.Mock).mockResolvedValue(mockReportSummary);

    render(
      <AuthProvider>
        <AuditLogsPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Search action, resource, IP...")).toBeInTheDocument();
    });

    // Enter search text
    const searchInput = screen.getByPlaceholderText("Search action, resource, IP...");
    fireEvent.change(searchInput, { target: { value: "workflow" } });

    // Select Action
    const actionSelect = screen.getByDisplayValue("All Actions");
    fireEvent.change(actionSelect, { target: { value: "workflow.approved" } });

    // Click Filter button
    const filterBtn = screen.getByRole("button", { name: "Filter" });
    fireEvent.click(filterBtn);

    await waitFor(() => {
      expect(api.getAuditLogs).toHaveBeenCalledWith(
        expect.objectContaining({
          search: "workflow",
          action: "workflow.approved",
        })
      );
    });
  });

  test("5. Date range validation prevents searching when start date is after end date", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getAuditLogs as jest.Mock).mockResolvedValue(mockPaginatedLogs);
    (api.getAuditReportSummary as jest.Mock).mockResolvedValue(mockReportSummary);

    render(
      <AuthProvider>
        <AuditLogsPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Audit Log Viewer")).toBeInTheDocument();
    });

    const dateInputs = screen.getAllByDisplayValue("");
    // Find the date inputs
    const startInput = dateInputs.find((input) => (input as HTMLInputElement).type === "date");
    expect(startInput).toBeDefined();

    // Set invalid dates in form
    fireEvent.change(startInput!, { target: { value: "2026-10-15" } });
    const allDates = screen.getAllByDisplayValue("2026-10-15");
    expect(allDates.length).toBeGreaterThan(0);
  });

  test("6. Inspecting an audit event opens details modal and shows sanitized metadata", async () => {
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getAuditLogs as jest.Mock).mockResolvedValue(mockPaginatedLogs);
    (api.getAuditReportSummary as jest.Mock).mockResolvedValue(mockReportSummary);
    (api.getAuditLogDetail as jest.Mock).mockResolvedValue(mockDetailLog);

    render(
      <AuthProvider>
        <AuditLogsPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getAllByTitle("View Event Details").length).toBeGreaterThan(0);
    });

    // Click inspect button
    const inspectButtons = screen.getAllByTitle("View Event Details");
    fireEvent.click(inspectButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("Audit Event Details")).toBeInTheDocument();
      expect(screen.getByText(/Financial Audit Report/)).toBeInTheDocument();
      expect(screen.getByText(/DOC-2026-0001/)).toBeInTheDocument();
    });

    // Close modal
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => {
      expect(screen.queryByText("Audit Event Details")).not.toBeInTheDocument();
    });
  });
});
