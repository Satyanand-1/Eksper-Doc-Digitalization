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
      registerPhysicalFile: jest.fn(),
      updatePhysicalFile: jest.fn(),
      changePhysicalFileStatus: jest.fn(),
    },
    getStoredToken: jest.fn(() => "mock-jwt-token"),
  };
});

const mockAdminUser = {
  id: "admin-uuid",
  email: "admin@edrms.test",
  full_name: "System Admin",
  role: "admin",
  department: "Executive",
  is_active: true,
};

const mockDeptUser = {
  id: "dept-user-uuid",
  email: "finuser@edrms.test",
  full_name: "Finance Officer",
  role: "department_user",
  department: "Finance",
  is_active: true,
};

const mockFilesList = [
  {
    id: "phy-1",
    file_reference: "PHY-2026-A1B2C3D4",
    title: "Master Services Agreement 2026 Original",
    record_type: "contract",
    department: "Finance",
    classification: "Confidential",
    status: "active",
    has_digital_document: true,
    external_reference: "EXT-MSA-99",
    date_received: "2026-01-15T00:00:00Z",
    created_at: "2026-01-15T00:00:00Z",
    updated_at: "2026-01-15T00:00:00Z",
  },
  {
    id: "phy-2",
    file_reference: "PHY-2026-E5F6G7H8",
    title: "Fiscal Audit Binder 2025",
    record_type: "financial_record",
    department: "Finance",
    classification: "Internal",
    status: "archived",
    has_digital_document: false,
    external_reference: null,
    date_received: "2026-02-01T00:00:00Z",
    created_at: "2026-02-01T00:00:00Z",
    updated_at: "2026-02-01T00:00:00Z",
  },
];

const mockDetailFile = {
  id: "phy-1",
  file_reference: "PHY-2026-A1B2C3D4",
  title: "Master Services Agreement 2026 Original",
  description: "Signed physical copy kept in vault drawer 4.",
  record_type: "contract",
  department: "Finance",
  classification: "Confidential",
  status: "active",
  digital_document_id: "doc-123",
  digital_document: {
    id: "doc-123",
    document_reference: "DOC-2026-0001",
    title: "Digital MSA 2026",
    department: "Finance",
    classification: "Confidential",
  },
  external_reference: "EXT-MSA-99",
  date_received: "2026-01-15T00:00:00Z",
  created_by_id: "user-1",
  created_by: {
    id: "user-1",
    email: "finuser@edrms.test",
    full_name: "Finance Officer",
    department: "Finance",
  },
  updated_by_id: null,
  updated_by: null,
  created_at: "2026-01-15T00:00:00Z",
  updated_at: "2026-01-15T00:00:00Z",
};

describe("Physical File Registry UI", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getPhysicalFiles as jest.Mock).mockResolvedValue({
      items: mockFilesList,
      page: 1,
      page_size: 15,
      total: 2,
      total_pages: 1,
    });
    (api.getPhysicalFile as jest.Mock).mockResolvedValue(mockDetailFile);
  });

  test("renders registry title and file records table", async () => {
    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Physical File Registry", level: 1 })).toBeInTheDocument();
    });

    expect(screen.getByText("PHY-2026-A1B2C3D4")).toBeInTheDocument();
    expect(screen.getByText("Master Services Agreement 2026 Original")).toBeInTheDocument();
    expect(screen.getByText("PHY-2026-E5F6G7H8")).toBeInTheDocument();
    expect(screen.getByText("Fiscal Audit Binder 2025")).toBeInTheDocument();
  });

  test("opens register file modal and validates inputs", async () => {
    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Register Physical File")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Register Physical File"));

    expect(screen.getByText("Register Physical Record")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("e.g. Master Services Agreement 2026 Original")).toBeInTheDocument();
  });

  test("opens detail view and displays metadata drawer", async () => {
    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("PHY-2026-A1B2C3D4")).toBeInTheDocument();
    });

    // Click view details action
    const viewButtons = screen.getAllByTitle("View Details");
    fireEvent.click(viewButtons[0]);

    await waitFor(() => {
      expect(api.getPhysicalFile).toHaveBeenCalledWith("phy-1");
      expect(screen.getByText("Signed physical copy kept in vault drawer 4.")).toBeInTheDocument();
      expect(screen.getByText("Digital MSA 2026")).toBeInTheDocument();
    });
  });

  test("handles empty state gracefully", async () => {
    (api.getPhysicalFiles as jest.Mock).mockResolvedValueOnce({
      items: [],
      page: 1,
      page_size: 15,
      total: 0,
      total_pages: 1,
    });

    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("No physical files found")).toBeInTheDocument();
    });
  });
});
