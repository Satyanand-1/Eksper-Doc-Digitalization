import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import PhysicalFilesPage from "@/app/physical-files/page";
import { PrintLabelModal } from "@/components/PrintLabelModal";
import { ScanLookupModal } from "@/components/ScanLookupModal";
import { AuthProvider } from "@/context/AuthContext";
import { api, ApiError } from "@/lib/api";
import { PhysicalFileDetail, PhysicalFileSummary } from "@/types/physical_file";

// Mock api methods
jest.mock("@/lib/api", () => {
  const original = jest.requireActual("@/lib/api");
  return {
    ...original,
    api: {
      getPhysicalFiles: jest.fn(),
      getOverduePhysicalFiles: jest.fn(),
      getPhysicalFile: jest.fn(),
      getPhysicalFileCustody: jest.fn(),
      getPhysicalFileMovementHistory: jest.fn(),
      lookupPhysicalFile: jest.fn(),
      recordLabelPrint: jest.fn(),
    },
  };
});

// Mock QRCode
jest.mock("qrcode", () => ({
  toDataURL: jest.fn((text, opts, callback) => {
    callback(null, "data:image/png;base64,mockedQrCodeDataUrl");
  }),
}));

// Mock JsBarcode
jest.mock("jsbarcode", () => jest.fn());

// Mock html5-qrcode
const mockHtml5QrcodeInstance = {
  start: jest.fn().mockResolvedValue(undefined),
  stop: jest.fn().mockResolvedValue(undefined),
  clear: jest.fn().mockResolvedValue(undefined),
  isScanning: true,
};

jest.mock("html5-qrcode", () => ({
  Html5Qrcode: Object.assign(
    jest.fn().mockImplementation(() => mockHtml5QrcodeInstance),
    {
      getCameras: jest.fn().mockResolvedValue([
        { id: "cam-1", label: "Rear Environment Camera" },
      ]),
    }
  ),
}));

// Mock AuthContext
jest.mock("@/context/AuthContext", () => {
  const actual = jest.requireActual("@/context/AuthContext");
  return {
    ...actual,
    useAuth: () => ({
      user: {
        id: "usr-admin-1",
        email: "admin@edrms.local",
        full_name: "Records Officer Jane",
        role: "records_officer",
        department: "Records Management",
        is_active: true,
      },
      loading: false,
      login: jest.fn(),
      logout: jest.fn(),
    }),
  };
});

const mockFilesSummary: PhysicalFileSummary[] = [
  {
    id: "f-1111-2222",
    file_reference: "PHY-2026-A1B2C3D4",
    title: "Master Services Contract 2026",
    record_type: "contract",
    department: "Legal",
    classification: "Confidential",
    status: "active",
    external_reference: "EXT-BC-9988",
    storage_location_id: "loc-cabinet-1",
    storage_location_name: "Cabinet C-10",
    has_digital_document: true,
    is_checked_out: false,
    current_custodian_name: null,
    is_overdue: false,
    created_at: "2026-10-10T08:00:00Z",
    updated_at: "2026-10-10T08:00:00Z",
  },
  {
    id: "f-3333-4444",
    file_reference: "PHY-2026-E5F6G7H8",
    title: "Executive Strategic Audit Folder",
    record_type: "archive_folder",
    department: "Executive",
    classification: "Restricted",
    status: "active",
    external_reference: null,
    storage_location_id: null,
    storage_location_name: null,
    has_digital_document: false,
    is_checked_out: true,
    current_custodian_name: "Counsel Vance",
    is_overdue: true,
    created_at: "2026-10-10T08:30:00Z",
    updated_at: "2026-10-10T08:30:00Z",
  },
];

const mockFileDetail: PhysicalFileDetail = {
  ...mockFilesSummary[0],
  description: "Signed physical contract file with supplier",
  digital_document_id: "doc-uuid-1",
  created_by_id: "usr-admin-1",
  created_by_name: "Records Officer Jane",
  current_location: null,
};

describe("Physical File Identification, Scanning, and Label Printing (Task 6.4)", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.getPhysicalFiles as jest.Mock).mockResolvedValue({
      items: mockFilesSummary,
      total: 2,
      page: 1,
      page_size: 15,
      total_pages: 1,
    });
    (api.getPhysicalFile as jest.Mock).mockResolvedValue(mockFileDetail);
    (api.getPhysicalFileCustody as jest.Mock).mockResolvedValue(null);
  });

  test("renders Scan / Lookup button in page header", async () => {
    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("PHY-2026-A1B2C3D4")).toBeInTheDocument();
    });

    const scanBtn = screen.getByRole("button", { name: /scan \/ lookup/i });
    expect(scanBtn).toBeInTheDocument();
  });

  test("opens scan modal and performs successful manual barcode lookup", async () => {
    (api.lookupPhysicalFile as jest.Mock).mockResolvedValue(mockFileDetail);

    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("PHY-2026-A1B2C3D4")).toBeInTheDocument();
    });

    // Open scan modal
    fireEvent.click(screen.getByRole("button", { name: /scan \/ lookup/i }));

    expect(screen.getByText("Identify & Scan Physical File")).toBeInTheDocument();

    // Switch to Manual tab
    fireEvent.click(screen.getByRole("button", { name: /manual \/ usb scanner/i }));

    const input = screen.getByPlaceholderText(/e\.g\. PHY-2026-A1B2C3D4/i);
    fireEvent.change(input, { target: { value: "PHY-2026-A1B2C3D4" } });

    fireEvent.click(screen.getByRole("button", { name: /lookup file/i }));

    await waitFor(() => {
      expect(api.lookupPhysicalFile).toHaveBeenCalledWith("PHY-2026-A1B2C3D4");
    });

    // Successfully opened the file detail drawer
    await waitFor(() => {
      expect(screen.getByText("Signed physical contract file with supplier")).toBeInTheDocument();
    });
  });

  test("displays non-disclosing error message when scanned reference is not found or denied", async () => {
    (api.lookupPhysicalFile as jest.Mock).mockRejectedValue(
      new ApiError("Record not found or access denied.", 404)
    );

    render(
      <ScanLookupModal
        onClose={jest.fn()}
        onFileFound={jest.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /manual \/ usb scanner/i }));

    const input = screen.getByPlaceholderText(/e\.g\. PHY-2026-A1B2C3D4/i);
    fireEvent.change(input, { target: { value: "NONEXISTENT-CODE" } });

    fireEvent.click(screen.getByRole("button", { name: /lookup file/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/record not found for "NONEXISTENT-CODE"/i)
      ).toBeInTheDocument();
    });
  });

  test("opens PrintLabelModal and displays QR code, barcode, and triggers audited print", async () => {
    (api.recordLabelPrint as jest.Mock).mockResolvedValue({
      status: "success",
      printed_count: 1,
    });
    const printSpy = jest.spyOn(window, "print").mockImplementation(() => {});

    render(
      <PrintLabelModal
        file={mockFileDetail}
        onClose={jest.fn()}
      />
    );

    expect(screen.getByText("Print Physical File Label")).toBeInTheDocument();
    expect(screen.getByText("PHY-2026-A1B2C3D4")).toBeInTheDocument();
    expect(screen.getByText("Master Services Contract 2026")).toBeInTheDocument();
    expect(screen.getByText(/scan qr/i)).toBeInTheDocument();

    // Trigger Print
    const printBtn = screen.getByRole("button", { name: /print label/i });
    fireEvent.click(printBtn);

    await waitFor(() => {
      expect(api.recordLabelPrint).toHaveBeenCalledWith({
        file_ids: ["f-1111-2222"],
        label_format: "standard_badge",
      });
    });

    expect(printSpy).toHaveBeenCalled();
    printSpy.mockRestore();
  });

  test("filters physical files by classification and custody state", async () => {
    render(
      <AuthProvider>
        <PhysicalFilesPage />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("PHY-2026-A1B2C3D4")).toBeInTheDocument();
    });

    // Select Custody State: "Overdue Files"
    const custodySelect = screen.getByLabelText("Circulation State Filter");
    fireEvent.change(custodySelect, { target: { value: "overdue" } });

    await waitFor(() => {
      expect(api.getPhysicalFiles).toHaveBeenCalledWith(
        expect.objectContaining({
          custody_state: "overdue",
        })
      );
    });
  });
});
