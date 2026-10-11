import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import StorageLocationsPage from "@/app/storage-locations/page";
import { AuthProvider } from "@/context/AuthContext";
import { api } from "@/lib/api";

// Mock API client
jest.mock("@/lib/api", () => {
  const original = jest.requireActual("@/lib/api");
  return {
    ...original,
    api: {
      getCurrentUser: jest.fn(),
      getStorageLocations: jest.fn(),
      getStorageLocation: jest.fn(),
      createStorageLocation: jest.fn(),
      updateStorageLocation: jest.fn(),
      changeStorageLocationStatus: jest.fn(),
      getStorageLocationChildren: jest.fn(),
      getStorageLocationContents: jest.fn(),
    },
    getStoredToken: jest.fn(() => "mock-jwt-token"),
  };
});

const mockAdminUser = {
  id: "admin-uuid",
  email: "admin@edrms.test",
  full_name: "System Admin",
  role: "admin",
  department: "Records Management",
  is_active: true,
};

const mockLocationsList = [
  {
    id: "loc-hq",
    location_code: "HQ-BLD-01",
    name: "Headquarters Main Facility",
    location_type: "building",
    department: "Records Management",
    parent_id: null,
    is_active: true,
    max_capacity: null,
    direct_file_count: 0,
    child_count: 3,
    location_path: "Headquarters Main Facility",
    created_at: "2026-01-15T00:00:00Z",
    updated_at: "2026-01-15T00:00:00Z",
  },
  {
    id: "loc-vault",
    location_code: "HQ-RM-V01",
    name: "Central Archive Vault",
    location_type: "room",
    department: "Records Management",
    parent_id: "loc-hq",
    is_active: true,
    max_capacity: 100,
    direct_file_count: 24,
    child_count: 2,
    location_path: "Headquarters Main Facility > Central Archive Vault",
    created_at: "2026-01-16T00:00:00Z",
    updated_at: "2026-01-16T00:00:00Z",
  },
];

const mockDetailLocation = {
  id: "loc-vault",
  location_code: "HQ-RM-V01",
  name: "Central Archive Vault",
  location_type: "room",
  description: "Secure climate-controlled storage for legal and historical papers.",
  department: "Records Management",
  parent_id: "loc-hq",
  parent: {
    id: "loc-hq",
    location_code: "HQ-BLD-01",
    name: "Headquarters Main Facility",
    location_type: "building",
    department: "Records Management",
    is_active: true,
    direct_file_count: 0,
    child_count: 3,
    location_path: "Headquarters Main Facility",
    created_at: "2026-01-15T00:00:00Z",
    updated_at: "2026-01-15T00:00:00Z",
  },
  is_active: true,
  max_capacity: 100,
  direct_file_count: 24,
  child_count: 2,
  location_path: "Headquarters Main Facility > Central Archive Vault",
  breadcrumbs: [
    {
      id: "loc-hq",
      location_code: "HQ-BLD-01",
      name: "Headquarters Main Facility",
      location_type: "building",
    },
    {
      id: "loc-vault",
      location_code: "HQ-RM-V01",
      name: "Central Archive Vault",
      location_type: "room",
    },
  ],
  created_by_id: "admin-uuid",
  created_by: {
    id: "admin-uuid",
    email: "admin@edrms.test",
    full_name: "System Admin",
    department: "Records Management",
  },
  updated_by_id: null,
  updated_by: null,
  created_at: "2026-01-16T00:00:00Z",
  updated_at: "2026-01-16T00:00:00Z",
};

const mockVaultContents = [
  {
    id: "phy-1",
    file_reference: "PHY-2026-A1B2C3D4",
    title: "Master Services Agreement 2026 Original",
    record_type: "contract",
    department: "Records Management",
    classification: "Confidential",
    status: "active",
    has_digital_document: true,
    storage_location_id: "loc-vault",
    storage_location_name: "Central Archive Vault",
    storage_location_code: "HQ-RM-V01",
    location_path: "Headquarters Main Facility > Central Archive Vault",
    external_reference: "EXT-MSA-99",
    date_received: "2026-01-15T00:00:00Z",
    created_at: "2026-01-15T00:00:00Z",
    updated_at: "2026-01-15T00:00:00Z",
  },
];

describe("Storage Locations Management UI", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.getCurrentUser as jest.Mock).mockResolvedValue(mockAdminUser);
    (api.getStorageLocations as jest.Mock).mockResolvedValue({
      items: mockLocationsList,
      page: 1,
      page_size: 25,
      total: 2,
      total_pages: 1,
    });
    (api.getStorageLocation as jest.Mock).mockResolvedValue(mockDetailLocation);
    (api.getStorageLocationContents as jest.Mock).mockResolvedValue({
      items: mockVaultContents,
      page: 1,
      page_size: 15,
      total: 1,
      total_pages: 1,
    });
  });

  test("renders storage locations header and table list", async () => {
    render(
      <AuthProvider>
        <StorageLocationsPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Storage Locations")).toBeInTheDocument();
    });

    expect(screen.getByText("HQ-BLD-01")).toBeInTheDocument();
    expect(screen.getByText("Headquarters Main Facility")).toBeInTheDocument();
    expect(screen.getByText("HQ-RM-V01")).toBeInTheDocument();
    expect(screen.getByText("Central Archive Vault")).toBeInTheDocument();
  });

  test("opens create storage location modal and checks inputs", async () => {
    render(
      <AuthProvider>
        <StorageLocationsPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("New Storage Location")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("New Storage Location"));

    expect(screen.getByPlaceholderText("e.g. CAB-FIN-01")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("e.g. Finance Vault Cabinet A")).toBeInTheDocument();
  });

  test("selects a location and displays details drawer and direct contents", async () => {
    render(
      <AuthProvider>
        <StorageLocationsPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("HQ-RM-V01")).toBeInTheDocument();
    });

    // Click on the table row for the vault
    fireEvent.click(screen.getByText("Central Archive Vault"));

    await waitFor(() => {
      expect(api.getStorageLocation).toHaveBeenCalledWith("loc-vault");
      expect(api.getStorageLocationContents).toHaveBeenCalledWith("loc-vault", { page: 1, page_size: 15 });
      expect(
        screen.getByText("Secure climate-controlled storage for legal and historical papers.")
      ).toBeInTheDocument();
      expect(screen.getByText("Master Services Agreement 2026 Original")).toBeInTheDocument();
      expect(screen.getByText("PHY-2026-A1B2C3D4")).toBeInTheDocument();
    });
  });

  test("displays empty state when no locations match criteria", async () => {
    (api.getStorageLocations as jest.Mock).mockResolvedValueOnce({
      items: [],
      page: 1,
      page_size: 25,
      total: 0,
      total_pages: 1,
    });

    render(
      <AuthProvider>
        <StorageLocationsPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("No storage locations found")).toBeInTheDocument();
    });
  });
});
