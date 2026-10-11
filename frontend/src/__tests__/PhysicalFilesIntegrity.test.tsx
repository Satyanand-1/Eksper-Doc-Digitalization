import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import PhysicalFilesPage from "@/app/physical-files/page";
import { AuthProvider } from "@/context/AuthContext";
import { api } from "@/lib/api";

// Mock API client
jest.mock("@/lib/api", () => {
  const original = jest.requireActual("@/lib/api");
  return {
    ...original,
    api: {
      getCurrentUser: jest.fn(),
      getPhysicalFiles: jest.fn(),
      getPhysicalFile: jest.fn(),
      getPhysicalFileCustody: jest.fn(),
      getPhysicalFileMovementHistory: jest.fn(),
      getOverduePhysicalFiles: jest.fn(),
      getCustodyIntegrityReport: jest.fn(),
      getLocationTransfersReport: jest.fn(),
      downloadCustodyReportCsv: jest.fn(),
    },
    getStoredToken: jest.fn(() => "mock-jwt-token"),
  };
});

const mockAdminUser = {
  id: "admin-uuid",
  email: "admin@edrms.test",
  full_name: "Records Administrator",
  role: "admin",
  department: "Records Management",
  is_active: true,
};

const mockEmptyFilesResponse = {
  items: [],
  page: 1,
  page_size: 15,
  total: 0,
  total_pages: 1,
};

const mockOverdueResponse = {
  items: [
    {
      custody_record_id: "cust-1",
      physical_file_id: "phy-1",
      file_reference: "PHY-2026-OVERDUE01",
      title: "Confidential Lease Agreement",
      department: "Legal",
      custodian_name: "Alice Investigator",
      custodian_department: "Compliance",
      custodian_contact: "alice@test.org",
      checked_out_at: "2026-02-01T10:00:00Z",
      expected_return_at: "2026-02-10T17:00:00Z",
      days_overdue: 12,
      purpose: "Case review",
      storage_location_name: "Room 102 - Shelf 4",
      storage_location_code: "LOC-R102-S4",
    },
  ],
  page: 1,
  page_size: 15,
  total: 1,
  total_pages: 1,
};

const mockTransfersResponse = {
  items: [
    {
      movement_id: "mov-transfer-1",
      physical_file_id: "phy-10",
      file_reference: "PHY-2026-TRANS01",
      title: "Annual Board Minutes 2025",
      department: "Executive",
      source_location_code: "LOC-R101-S1",
      source_location_name: "Cabinet A",
      destination_location_code: "LOC-R102-S2",
      destination_location_name: "Vault B",
      transferred_at: "2026-03-01T14:30:00Z",
      reason: "Relocated to secure archive",
      transferred_by: {
        id: "admin-uuid",
        full_name: "Records Administrator",
        email: "admin@edrms.test",
      },
    },
  ],
  page: 1,
  page_size: 15,
  total: 1,
  total_pages: 1,
};

const mockIntegrityResponseWithIssues = {
  total_files_scanned: 42,
  total_issues_found: 2,
  issues_by_type: {
    MISSING_ACTIVE_CUSTODY: 1,
    LOCATION_MISMATCH_WITH_TRANSFER: 1,
  },
  items: [
    {
      issue_type: "MISSING_ACTIVE_CUSTODY",
      severity: "error",
      physical_file_id: "phy-anom-1",
      file_reference: "PHY-2026-ERR01",
      title: "Missing Custody File",
      department: "Finance",
      description: "File marked checked-out but has no active custody record.",
      diagnostic_details: { has_historical_custody: true },
      detected_at: "2026-03-02T08:00:00Z",
    },
    {
      issue_type: "LOCATION_MISMATCH_WITH_TRANSFER",
      severity: "warning",
      physical_file_id: "phy-anom-2",
      file_reference: "PHY-2026-WARN02",
      title: "Mismatched Location File",
      department: "Operations",
      description: "Storage location does not match latest transfer destination.",
      diagnostic_details: {},
      detected_at: "2026-03-02T08:00:00Z",
    },
  ],
  page: 1,
  page_size: 25,
  total: 2,
  total_pages: 1,
};

describe("Physical Files Chain-of-Custody & Integrity Reporting (Task 6.5)", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getPhysicalFiles as jest.Mock).mockResolvedValue(mockEmptyFilesResponse);
    (api.getOverduePhysicalFiles as jest.Mock).mockResolvedValue(mockOverdueResponse);
    (api.getLocationTransfersReport as jest.Mock).mockResolvedValue(mockTransfersResponse);
    (api.getCustodyIntegrityReport as jest.Mock).mockResolvedValue(mockIntegrityResponseWithIssues);
    (api.downloadCustodyReportCsv as jest.Mock).mockResolvedValue(new Blob(["test,csv"], { type: "text/csv" }));
  });

  test("renders Overdue Circulation tab with custodian and location data", async () => {
    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    // Switch to Overdue tab
    const overdueTabBtn = await screen.findByRole("button", { name: /Overdue Circulation/i });
    fireEvent.click(overdueTabBtn);

    // Verify overdue API was called
    await waitFor(() => {
      expect(api.getOverduePhysicalFiles).toHaveBeenCalled();
    });

    // Verify overdue item information rendered
    expect(await screen.findByText("PHY-2026-OVERDUE01")).toBeInTheDocument();
    expect(screen.getByText("Alice Investigator")).toBeInTheDocument();
    expect(screen.getByText("Room 102 - Shelf 4")).toBeInTheDocument();
    expect(screen.getByText(/12 days overdue/i)).toBeInTheDocument();
  });

  test("renders Location Transfers tab with source and destination details", async () => {
    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    // Switch to Location Transfers tab
    const transfersTabBtn = await screen.findByRole("button", { name: /Location Transfers/i });
    fireEvent.click(transfersTabBtn);

    // Verify transfers API called
    await waitFor(() => {
      expect(api.getLocationTransfersReport).toHaveBeenCalled();
    });

    // Check rendered transfer details
    expect(await screen.findByText("PHY-2026-TRANS01")).toBeInTheDocument();
    expect(screen.getByText("Annual Board Minutes 2025")).toBeInTheDocument();
    expect(screen.getByText("Cabinet A")).toBeInTheDocument();
    expect(screen.getByText("Vault B")).toBeInTheDocument();
    expect(screen.getByText(/Relocated to secure archive/i)).toBeInTheDocument();
  });

  test("renders Custody Integrity Diagnostic tab with invariant issues", async () => {
    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    // Switch to Custody Integrity Diagnostic tab
    const integrityTabBtn = await screen.findByRole("button", { name: /Custody Integrity Diagnostic/i });
    fireEvent.click(integrityTabBtn);

    // Verify integrity diagnostic API called
    await waitFor(() => {
      expect(api.getCustodyIntegrityReport).toHaveBeenCalled();
    });

    // Check detected anomalies and counts
    expect(await screen.findByText(/2 Custody Invariant Inconsistencies Detected/i)).toBeInTheDocument();
    expect(screen.getByText("PHY-2026-ERR01")).toBeInTheDocument();
    expect(screen.getByText("MISSING_ACTIVE_CUSTODY")).toBeInTheDocument();
    expect(screen.getByText("File marked checked-out but has no active custody record.")).toBeInTheDocument();

    expect(screen.getByText("PHY-2026-WARN02")).toBeInTheDocument();
    expect(screen.getByText("LOCATION_MISMATCH_WITH_TRANSFER")).toBeInTheDocument();
  });

  test("triggers CSV export for overdue report", async () => {
    // Mock URL.createObjectURL and URL.revokeObjectURL
    window.URL.createObjectURL = jest.fn(() => "blob:mock-url");
    window.URL.revokeObjectURL = jest.fn();

    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    // Switch to Overdue tab
    const overdueTabBtn = await screen.findByRole("button", { name: /Overdue Circulation/i });
    fireEvent.click(overdueTabBtn);

    await waitFor(() => {
      expect(api.getOverduePhysicalFiles).toHaveBeenCalled();
    });

    // Click Export Overdue CSV button
    const exportBtn = screen.getByRole("button", { name: /Export Overdue CSV/i });
    fireEvent.click(exportBtn);

    await waitFor(() => {
      expect(api.downloadCustodyReportCsv).toHaveBeenCalledWith(
        expect.objectContaining({ report_type: "overdue" })
      );
    });
  });
});
