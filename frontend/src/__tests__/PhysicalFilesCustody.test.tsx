import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import PhysicalFilesPage from "@/app/physical-files/page";
import { AuthProvider } from "@/context/AuthContext";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => {
  const original = jest.requireActual("@/lib/api");
  return {
    ...original,
    api: {
      getCurrentUser: jest.fn(),
      getPhysicalFiles: jest.fn(),
      getPhysicalFile: jest.fn(),
      registerPhysicalFile: jest.fn(),
      updatePhysicalFile: jest.fn(),
      changePhysicalFileStatus: jest.fn(),
      assignFileLocation: jest.fn(),
      checkoutPhysicalFile: jest.fn(),
      checkinPhysicalFile: jest.fn(),
      transferPhysicalFile: jest.fn(),
      getPhysicalFileCustody: jest.fn(),
      getPhysicalFileCustodyHistory: jest.fn(),
      getPhysicalFileMovementHistory: jest.fn(),
      getOverduePhysicalFiles: jest.fn(),
    },
    getStoredToken: jest.fn(() => "mock-jwt-token"),
  };
});

describe("Physical File Circulation and Custody UI", () => {
  const mockUser = {
    id: "user-123",
    email: "records@example.com",
    full_name: "Records Manager",
    role: "records_officer",
    department: "Records Management",
  };

  const mockFiles = [
    {
      id: "file-1",
      file_reference: "PHY-2026-STORED01",
      title: "Confidential M&A Agreement",
      record_type: "contract",
      department: "Records Management",
      classification: "Confidential",
      status: "active",
      has_digital_document: false,
      storage_location_id: "loc-1",
      storage_location_name: "Archive Cabinet A",
      storage_location_code: "CAB-A",
      is_checked_out: false,
      current_custodian_name: null,
      is_overdue: false,
      date_received: "2026-03-01T10:00:00Z",
      created_at: "2026-03-01T10:00:00Z",
      updated_at: "2026-03-01T10:00:00Z",
    },
    {
      id: "file-2",
      file_reference: "PHY-2026-CHECKEDOUT",
      title: "Audited Financial Statement Binder",
      record_type: "financial_record",
      department: "Records Management",
      classification: "Restricted",
      status: "active",
      has_digital_document: true,
      storage_location_id: "loc-2",
      storage_location_name: "Shelf 4B",
      storage_location_code: "SH-4B",
      is_checked_out: true,
      current_custodian_name: "Senior Auditor Smith",
      is_overdue: true,
      date_received: "2026-03-05T10:00:00Z",
      created_at: "2026-03-05T10:00:00Z",
      updated_at: "2026-03-05T10:00:00Z",
    },
  ];

  const mockStoredDetail = {
    ...mockFiles[0],
    description: "Physical legal agreement with signatures.",
    created_by_id: "user-123",
    created_by: { id: "user-123", email: "records@example.com", full_name: "Records Manager", department: "Records Management" },
    location_path: "HQ / Archive / Cabinet A",
  };

  const mockCheckedOutDetail = {
    ...mockFiles[1],
    description: "Original paper receipts and tax declarations.",
    created_by_id: "user-123",
    created_by: { id: "user-123", email: "records@example.com", full_name: "Records Manager", department: "Records Management" },
    location_path: "HQ / Archive / Shelf 4B",
  };

  const mockActiveCustody = {
    id: "custody-99",
    physical_file_id: "file-2",
    file_reference: "PHY-2026-CHECKEDOUT",
    file_title: "Audited Financial Statement Binder",
    custodian_name: "Senior Auditor Smith",
    custodian_department: "Finance",
    custodian_contact: "ext. 4022",
    status: "active",
    checked_out_at: "2026-03-10T09:00:00Z",
    expected_return_at: "2026-03-15T18:00:00Z",
    purpose: "Statutory Financial Audit",
    issued_by_id: "user-123",
    is_overdue: true,
    created_at: "2026-03-10T09:00:00Z",
    updated_at: "2026-03-10T09:00:00Z",
  };

  const mockMovementHistory = [
    {
      id: "mov-1",
      physical_file_id: "file-1",
      movement_type: "checkout",
      source_location_id: "loc-1",
      source_location_code: "CAB-A",
      source_location_name: "Archive Cabinet A",
      destination_location_id: null,
      from_custody_state: "stored",
      to_custody_state: "checked_out",
      actor_id: "user-123",
      actor: { id: "user-123", email: "records@example.com", full_name: "Records Manager" },
      event_at: "2026-03-10T09:00:00Z",
      reason: "Temporary checkout for legal review",
      custody_record_id: "custody-99",
      created_at: "2026-03-10T09:00:00Z",
    },
  ];

  const mockOverdueResponse = {
    items: [
      {
        physical_file_id: "file-2",
        file_reference: "PHY-2026-CHECKEDOUT",
        title: "Audited Financial Statement Binder",
        department: "Records Management",
        classification: "Restricted",
        custody_record_id: "custody-99",
        custodian_name: "Senior Auditor Smith",
        custodian_department: "Finance",
        custodian_contact: "ext. 4022",
        checked_out_at: "2026-03-10T09:00:00Z",
        expected_return_at: "2026-03-15T18:00:00Z",
        days_overdue: 5,
        purpose: "Statutory Financial Audit",
        issued_by: { id: "user-123", email: "records@example.com", full_name: "Records Manager" },
      },
    ],
    page: 1,
    page_size: 15,
    total: 1,
    total_pages: 1,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockUser);
    (api.getPhysicalFiles as jest.Mock).mockResolvedValue({
      items: mockFiles,
      page: 1,
      page_size: 15,
      total: 2,
      total_pages: 1,
    });
    (api.getOverduePhysicalFiles as jest.Mock).mockResolvedValue(mockOverdueResponse);
  });

  test("renders custody status badges (Stored vs Overdue / Checked Out) in table", async () => {
    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("PHY-2026-STORED01")).toBeInTheDocument();
    });

    expect(screen.getByText("Stored")).toBeInTheDocument();
    expect(screen.getByText("Overdue")).toBeInTheDocument();
    expect(screen.getByText("To: Senior Auditor Smith")).toBeInTheDocument();
  });

  test("opens detail drawer for stored file and displays Check Out and Transfer buttons", async () => {
    (api.getPhysicalFile as jest.Mock).mockResolvedValue(mockStoredDetail);

    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("PHY-2026-STORED01")).toBeInTheDocument();
    });

    const viewButtons = screen.getAllByTitle("View Details");
    fireEvent.click(viewButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("Circulation & Custody State")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /^Check Out$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Transfer$/i })).toBeInTheDocument();
    expect(screen.getByText(/File is stored in archive location/i)).toBeInTheDocument();
  });

  test("opens checkout modal, submits checkout payload, and closes modal", async () => {
    (api.getPhysicalFile as jest.Mock).mockResolvedValue(mockStoredDetail);
    (api.checkoutPhysicalFile as jest.Mock).mockResolvedValue(mockActiveCustody);

    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("PHY-2026-STORED01")).toBeInTheDocument();
    });

    const viewButtons = screen.getAllByTitle("View Details");
    fireEvent.click(viewButtons[0]);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Check Out/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Check Out/i }));

    expect(screen.getByText("Check Out Physical File")).toBeInTheDocument();

    const nameInput = screen.getByPlaceholderText(/e\.g\. John Doe/i);
    fireEvent.change(nameInput, { target: { value: "Attorney Vance" } });

    fireEvent.click(screen.getByRole("button", { name: /Confirm Check Out/i }));

    await waitFor(() => {
      expect(api.checkoutPhysicalFile).toHaveBeenCalledWith("file-1", expect.objectContaining({
        custodian_name: "Attorney Vance",
      }));
    });
  });

  test("switches to Overdue Circulation tab and lists overdue files", async () => {
    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Overdue Circulation")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Overdue Circulation"));

    await waitFor(() => {
      expect(api.getOverduePhysicalFiles).toHaveBeenCalled();
    });

    expect(screen.getByText("Overdue Checked-Out Physical Records")).toBeInTheDocument();
    expect(screen.getByText("5 days overdue")).toBeInTheDocument();
    expect(screen.getByText("Senior Auditor Smith")).toBeInTheDocument();
  });

  test("opens movement history modal and displays timeline entries", async () => {
    (api.getPhysicalFile as jest.Mock).mockResolvedValue(mockStoredDetail);
    (api.getPhysicalFileMovementHistory as jest.Mock).mockResolvedValue({
      items: mockMovementHistory,
      page: 1,
      page_size: 20,
      total: 1,
      total_pages: 1,
    });

    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("PHY-2026-STORED01")).toBeInTheDocument();
    });

    const viewButtons = screen.getAllByTitle("View Details");
    fireEvent.click(viewButtons[0]);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Movement History/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Movement History/i }));

    await waitFor(() => {
      expect(api.getPhysicalFileMovementHistory).toHaveBeenCalledWith("file-1", expect.anything());
    });

    expect(screen.getByText("Movement History: PHY-2026-STORED01")).toBeInTheDocument();
    expect(screen.getByText(/Temporary checkout for legal review/i)).toBeInTheDocument();
  });
});
