"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { api, ApiError } from "@/lib/api";
import {
  PhysicalFileSummary,
  PhysicalFileDetail,
  PhysicalRecordType,
  PhysicalFileStatus,
  RegisterPhysicalFilePayload,
  UpdatePhysicalFilePayload,
} from "@/types/physical_file";
import {
  CustodyRecord,
  MovementHistoryItem,
  OverdueFileSummary,
  CustodyIntegrityReport,
  CustodyIntegrityIssue,
  LocationTransferEventItem,
} from "@/types/custody";
import { StorageLocationSummary } from "@/types/storage_location";
import { DocumentSummaryResponse } from "@/types/document";
import { PrintLabelModal } from "@/components/PrintLabelModal";
import { ScanLookupModal } from "@/components/ScanLookupModal";
import {
  FolderArchive,
  Search,
  Plus,
  Filter,
  FileText,
  Clock,
  Shield,
  Building,
  CheckCircle2,
  AlertCircle,
  Eye,
  Edit2,
  X,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  MapPin,
  ArrowRightLeft,
  LogIn,
  LogOut,
  History,
  AlertTriangle,
  UserCheck,
  Printer,
  QrCode,
  Download,
  ShieldCheck,
  FileSpreadsheet,
} from "lucide-react";

const RECORD_TYPES: { value: PhysicalRecordType; label: string }[] = [
  { value: "contract", label: "Contract" },
  { value: "case_file", label: "Case File" },
  { value: "correspondence", label: "Correspondence" },
  { value: "archive_folder", label: "Archive Folder" },
  { value: "financial_record", label: "Financial Record" },
  { value: "personnel_file", label: "Personnel File" },
  { value: "policy_document", label: "Policy Document" },
  { value: "other", label: "Other" },
];

const DEPARTMENTS = [
  "Finance",
  "Human Resources",
  "Legal",
  "Operations",
  "Executive",
  "Records Management",
  "IT",
];

const CLASSIFICATIONS = ["Public", "Internal", "Confidential", "Restricted"];

export default function PhysicalFilesPage() {
  const { user } = useAuth();

  // Registry List State
  const [files, setFiles] = useState<PhysicalFileSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [totalCount, setTotalCount] = useState<number>(0);

  // Filters State
  const [search, setSearch] = useState<string>("");
  const [selectedDept, setSelectedDept] = useState<string>("");
  const [selectedRecordType, setSelectedRecordType] = useState<string>("");
  const [selectedStatus, setSelectedStatus] = useState<string>("");
  const [selectedClassification, setSelectedClassification] = useState<string>("");
  const [selectedCustodyState, setSelectedCustodyState] = useState<string>("");

  // Modals & Drawers
  const [showRegisterModal, setShowRegisterModal] = useState<boolean>(false);
  const [viewFileId, setViewFileId] = useState<string | null>(null);
  const [editFile, setEditFile] = useState<PhysicalFileDetail | null>(null);
  const [statusConfirmFile, setStatusConfirmFile] = useState<{
    file: PhysicalFileDetail;
    targetStatus: PhysicalFileStatus;
  } | null>(null);
  const [showScanModal, setShowScanModal] = useState<boolean>(false);
  const [printLabelFile, setPrintLabelFile] = useState<PhysicalFileDetail | PhysicalFileSummary | null>(null);

  // Register Form State
  const [regTitle, setRegTitle] = useState<string>("");
  const [regDescription, setRegDescription] = useState<string>("");
  const [regRecordType, setRegRecordType] = useState<PhysicalRecordType>("contract");
  const [regDepartment, setRegDepartment] = useState<string>("");
  const [regClassification, setRegClassification] = useState<string>("");
  const [regExtRef, setRegExtRef] = useState<string>("");
  const [regDigitalDocId, setRegDigitalDocId] = useState<string>("");
  const [regStorageLocationId, setRegStorageLocationId] = useState<string>("");
  const [regSubmitting, setRegSubmitting] = useState<boolean>(false);
  const [regError, setRegError] = useState<string | null>(null);
  const [regSuccessMsg, setRegSuccessMsg] = useState<string | null>(null);

  // Detail View State
  const [detailFile, setDetailFile] = useState<PhysicalFileDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Edit Form State
  const [editTitle, setEditTitle] = useState<string>("");
  const [editDescription, setEditDescription] = useState<string>("");
  const [editRecordType, setEditRecordType] = useState<PhysicalRecordType>("contract");
  const [editDepartment, setEditDepartment] = useState<string>("");
  const [editClassification, setEditClassification] = useState<string>("");
  const [editExtRef, setEditExtRef] = useState<string>("");
  const [editDigitalDocId, setEditDigitalDocId] = useState<string>("");
  const [editUnlinkDigital, setEditUnlinkDigital] = useState<boolean>(false);
  const [editStorageLocationId, setEditStorageLocationId] = useState<string>("");
  const [editUnlinkLocation, setEditUnlinkLocation] = useState<boolean>(false);
  const [editSubmitting, setEditSubmitting] = useState<boolean>(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Assign Location Modal State
  const [assignModalFile, setAssignModalFile] = useState<PhysicalFileDetail | null>(null);
  const [assignLocationId, setAssignLocationId] = useState<string>("");
  const [assignSubmitting, setAssignSubmitting] = useState<boolean>(false);
  const [assignError, setAssignError] = useState<string | null>(null);
  const [availableLocations, setAvailableLocations] = useState<StorageLocationSummary[]>([]);
  const [availableDocs, setAvailableDocs] = useState<DocumentSummaryResponse[]>([]);

  // Main Page Tab: 'registry' | 'overdue' | 'transfers' | 'integrity'
  const [activeTab, setActiveTab] = useState<"registry" | "overdue" | "transfers" | "integrity">("registry");

  // Overdue Tab State & Filters
  const [overdueFiles, setOverdueFiles] = useState<OverdueFileSummary[]>([]);
  const [overdueLoading, setOverdueLoading] = useState<boolean>(false);
  const [overdueError, setOverdueError] = useState<string | null>(null);
  const [overduePage, setOverduePage] = useState<number>(1);
  const [overdueTotalPages, setOverdueTotalPages] = useState<number>(1);
  const [overdueTotal, setOverdueTotal] = useState<number>(0);
  const [overdueCustodianFilter, setOverdueCustodianFilter] = useState<string>("");
  const [overdueMinDaysFilter, setOverdueMinDaysFilter] = useState<string>("");

  // Storage Location Transfers Tab State & Filters
  const [transfers, setTransfers] = useState<LocationTransferEventItem[]>([]);
  const [transfersLoading, setTransfersLoading] = useState<boolean>(false);
  const [transfersError, setTransfersError] = useState<string | null>(null);
  const [transfersPage, setTransfersPage] = useState<number>(1);
  const [transfersTotalPages, setTransfersTotalPages] = useState<number>(1);
  const [transfersTotal, setTransfersTotal] = useState<number>(0);
  const [transfersStartDate, setTransfersStartDate] = useState<string>("");
  const [transfersEndDate, setTransfersEndDate] = useState<string>("");

  // Custody Integrity Tab State
  const [integrityReport, setIntegrityReport] = useState<CustodyIntegrityReport | null>(null);
  const [integrityLoading, setIntegrityLoading] = useState<boolean>(false);
  const [integrityError, setIntegrityError] = useState<string | null>(null);
  const [integritySeverityFilter, setIntegritySeverityFilter] = useState<string>("all");

  // Export State
  const [exportLoading, setExportLoading] = useState<boolean>(false);
  const [exportError, setExportError] = useState<string | null>(null);

  // Custody Drawer State (for Detail Drawer)
  const [detailCustody, setDetailCustody] = useState<CustodyRecord | null>(null);
  const [detailCustodyLoading, setDetailCustodyLoading] = useState<boolean>(false);

  // Check-Out Modal State
  const [checkoutFile, setCheckoutFile] = useState<PhysicalFileDetail | null>(null);
  const [checkoutCustodianName, setCheckoutCustodianName] = useState<string>("");
  const [checkoutCustodianDept, setCheckoutCustodianDept] = useState<string>("");
  const [checkoutCustodianContact, setCheckoutCustodianContact] = useState<string>("");
  const [checkoutExpectedReturn, setCheckoutExpectedReturn] = useState<string>("");
  const [checkoutPurpose, setCheckoutPurpose] = useState<string>("");
  const [checkoutSubmitting, setCheckoutSubmitting] = useState<boolean>(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

  // Check-In Modal State
  const [checkinFile, setCheckinFile] = useState<PhysicalFileDetail | null>(null);
  const [checkinDestLocationId, setCheckinDestLocationId] = useState<string>("");
  const [checkinNotes, setCheckinNotes] = useState<string>("");
  const [checkinSubmitting, setCheckinSubmitting] = useState<boolean>(false);
  const [checkinError, setCheckinError] = useState<string | null>(null);

  // Transfer Modal State
  const [transferFile, setTransferFile] = useState<PhysicalFileDetail | null>(null);
  const [transferDestLocationId, setTransferDestLocationId] = useState<string>("");
  const [transferLocationSearch, setTransferLocationSearch] = useState<string>("");
  const [transferReason, setTransferReason] = useState<string>("");
  const [transferSubmitting, setTransferSubmitting] = useState<boolean>(false);
  const [transferError, setTransferError] = useState<string | null>(null);

  // Movement History Modal State
  const [historyFile, setHistoryFile] = useState<PhysicalFileDetail | null>(null);
  const [historyItems, setHistoryItems] = useState<MovementHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState<boolean>(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyPage, setHistoryPage] = useState<number>(1);
  const [historyTotalPages, setHistoryTotalPages] = useState<number>(1);

  // Status Change State
  const [statusReason, setStatusReason] = useState<string>("");
  const [statusSubmitting, setStatusSubmitting] = useState<boolean>(false);
  const [statusError, setStatusError] = useState<string | null>(null);

  // Set default department on register modal open
  useEffect(() => {
    if (user) {
      if (user.role === "department_user") {
        setRegDepartment(user.department || "");
      } else {
        setRegDepartment(user.department || "Records Management");
      }
    }
  }, [user]);

  const fetchStorageLocs = React.useCallback(async () => {
    try {
      const res = await api.getStorageLocations({ page_size: 100 });
      if (res && res.items) {
        setAvailableLocations(res.items.filter((loc) => loc.is_active));
      }
    } catch (err) {
      console.error("Failed to fetch storage locations", err);
    }
  }, []);

  const fetchDocs = React.useCallback(async () => {
    try {
      const res = await api.getDocuments(1, 100);
      if (res && res.items) {
        setAvailableDocs(res.items);
      }
    } catch (err) {
      console.error("Failed to fetch digital documents", err);
    }
  }, []);

  // Fetch active storage locations & digital documents whenever user changes or authenticates
  useEffect(() => {
    fetchStorageLocs();
    fetchDocs();
  }, [user, fetchStorageLocs, fetchDocs]);

  // Fetch Physical Files List
  const fetchFiles = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getPhysicalFiles({
        page,
        page_size: 15,
        search: search.trim() || undefined,
        department: selectedDept || undefined,
        record_type: selectedRecordType || undefined,
        status: selectedStatus || undefined,
        classification: selectedClassification || undefined,
        custody_state: (selectedCustodyState as "stored" | "checked_out" | "overdue") || undefined,
      });
      setFiles(res.items);
      setTotalPages(res.total_pages);
      setTotalCount(res.total);
    } catch (err: any) {
      setError(err.message || "Failed to load physical file registry.");
    } finally {
      setLoading(false);
    }
  }, [
    page,
    search,
    selectedDept,
    selectedRecordType,
    selectedStatus,
    selectedClassification,
    selectedCustodyState,
  ]);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchFiles();
  };

  // Fetch Overdue Files List
  const fetchOverdueFiles = React.useCallback(async () => {
    setOverdueLoading(true);
    setOverdueError(null);
    try {
      const minDaysNum = overdueMinDaysFilter.trim() ? parseInt(overdueMinDaysFilter.trim(), 10) : undefined;
      const res = await api.getOverduePhysicalFiles({
        page: overduePage,
        page_size: 15,
        department: selectedDept || undefined,
        custodian: overdueCustodianFilter.trim() || undefined,
        min_days_overdue: isNaN(minDaysNum as any) ? undefined : minDaysNum,
      });
      setOverdueFiles(res.items);
      setOverdueTotalPages(res.total_pages);
      setOverdueTotal(res.total);
    } catch (err: any) {
      setOverdueError(err.message || "Failed to load overdue physical records.");
    } finally {
      setOverdueLoading(false);
    }
  }, [overduePage, selectedDept, overdueCustodianFilter, overdueMinDaysFilter]);

  // Fetch Storage Location Transfers List
  const fetchTransfers = React.useCallback(async () => {
    setTransfersLoading(true);
    setTransfersError(null);
    try {
      const res = await api.getLocationTransfersReport({
        page: transfersPage,
        page_size: 15,
        department: selectedDept || undefined,
        from_date: transfersStartDate ? new Date(transfersStartDate).toISOString() : undefined,
        to_date: transfersEndDate ? new Date(transfersEndDate).toISOString() : undefined,
      });
      setTransfers(res.items);
      setTransfersTotalPages(res.total_pages);
      setTransfersTotal(res.total);
    } catch (err: any) {
      setTransfersError(err.message || "Failed to load storage location transfers.");
    } finally {
      setTransfersLoading(false);
    }
  }, [transfersPage, selectedDept, transfersStartDate, transfersEndDate]);

  // Fetch Custody Integrity Diagnostic Report
  const fetchIntegrityReport = React.useCallback(async () => {
    setIntegrityLoading(true);
    setIntegrityError(null);
    try {
      const res = await api.getCustodyIntegrityReport({
        department: selectedDept || undefined,
      });
      setIntegrityReport(res);
    } catch (err: any) {
      setIntegrityError(err.message || "Failed to load custody integrity diagnostic.");
    } finally {
      setIntegrityLoading(false);
    }
  }, [selectedDept]);

  // Trigger data fetches based on active tab
  useEffect(() => {
    if (activeTab === "overdue") {
      fetchOverdueFiles();
    } else if (activeTab === "transfers") {
      fetchTransfers();
    } else if (activeTab === "integrity") {
      fetchIntegrityReport();
    }
  }, [activeTab, fetchOverdueFiles, fetchTransfers, fetchIntegrityReport]);

  // Export CSV handler
  const handleExportCsv = async (reportType: "overdue" | "transfers" | "checked_out") => {
    setExportLoading(true);
    setExportError(null);
    try {
      const blob = await api.downloadCustodyReportCsv({
        report_type: reportType,
        department: selectedDept || undefined,
      });

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${reportType}_report_${new Date().toISOString().split("T")[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      setExportError(err.message || `Failed to export ${reportType} CSV.`);
    } finally {
      setExportLoading(false);
    }
  };

  // Open Detail View & Load Active Custody
  const handleOpenDetail = async (id: string) => {
    setViewFileId(id);
    setDetailLoading(true);
    setDetailError(null);
    setDetailCustody(null);
    try {
      const data = await api.getPhysicalFile(id);
      setDetailFile(data);

      if (data.is_checked_out) {
        setDetailCustodyLoading(true);
        try {
          const custodyData = await api.getPhysicalFileCustody(id);
          setDetailCustody(custodyData);
        } catch {
          // Non-blocking if custody fetch fails
        } finally {
          setDetailCustodyLoading(false);
        }
      }
    } catch (err: any) {
      setDetailError(err.message || "Failed to load file details.");
    } finally {
      setDetailLoading(false);
    }
  };

  // Open Movement History Modal
  const handleOpenHistory = async (file: PhysicalFileDetail) => {
    setHistoryFile(file);
    setHistoryLoading(true);
    setHistoryError(null);
    setHistoryPage(1);
    try {
      const res = await api.getPhysicalFileMovementHistory(file.id, { page: 1, page_size: 20 });
      setHistoryItems(res.items);
      setHistoryTotalPages(res.total_pages);
    } catch (err: any) {
      setHistoryError(err.message || "Failed to load movement history.");
    } finally {
      setHistoryLoading(false);
    }
  };

  // Open Checkout Modal
  const handleOpenCheckout = (file: PhysicalFileDetail) => {
    setCheckoutFile(file);
    setCheckoutCustodianName("");
    setCheckoutCustodianDept(file.department);
    setCheckoutCustodianContact("");
    setCheckoutExpectedReturn("");
    setCheckoutPurpose("");
    setCheckoutError(null);
  };

  // Handle Checkout Submit
  const handleCheckoutSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!checkoutFile) return;
    if (!checkoutCustodianName.trim()) {
      setCheckoutError("Custodian name is required.");
      return;
    }

    setCheckoutSubmitting(true);
    setCheckoutError(null);
    try {
      let expReturnIso: string | null = null;
      if (checkoutExpectedReturn.trim()) {
        expReturnIso = new Date(checkoutExpectedReturn).toISOString();
      }

      await api.checkoutPhysicalFile(checkoutFile.id, {
        custodian_name: checkoutCustodianName.trim(),
        custodian_department: checkoutCustodianDept.trim() || null,
        custodian_contact: checkoutCustodianContact.trim() || null,
        expected_return_at: expReturnIso,
        purpose: checkoutPurpose.trim() || null,
      });

      const updated = await api.getPhysicalFile(checkoutFile.id);
      setCheckoutFile(null);
      if (viewFileId === updated.id) {
        setDetailFile(updated);
        const cRec = await api.getPhysicalFileCustody(updated.id);
        setDetailCustody(cRec);
      }
      fetchFiles();
      if (activeTab === "overdue") fetchOverdueFiles();
    } catch (err: any) {
      setCheckoutError(err.message || "Failed to check out physical file.");
    } finally {
      setCheckoutSubmitting(false);
    }
  };

  // Open Checkin Modal
  const handleOpenCheckin = (file: PhysicalFileDetail) => {
    setCheckinFile(file);
    setCheckinDestLocationId(file.storage_location_id || "");
    setCheckinNotes("");
    setCheckinError(null);
  };

  // Handle Checkin Submit
  const handleCheckinSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!checkinFile) return;

    setCheckinSubmitting(true);
    setCheckinError(null);
    try {
      await api.checkinPhysicalFile(checkinFile.id, {
        destination_location_id: checkinDestLocationId.trim() || null,
        checkin_notes: checkinNotes.trim() || null,
      });

      const updated = await api.getPhysicalFile(checkinFile.id);
      setCheckinFile(null);
      if (viewFileId === updated.id) {
        setDetailFile(updated);
        setDetailCustody(null);
      }
      fetchFiles();
      if (activeTab === "overdue") fetchOverdueFiles();
    } catch (err: any) {
      setCheckinError(err.message || "Failed to check in physical file.");
    } finally {
      setCheckinSubmitting(false);
    }
  };

  // Open Transfer Modal
  const handleOpenTransfer = (file: PhysicalFileDetail) => {
    setTransferFile(file);
    setTransferDestLocationId("");
    setTransferLocationSearch("");
    setTransferReason("");
    setTransferError(null);
    if (availableLocations.length === 0) {
      fetchStorageLocs();
    }
  };

  // Handle Transfer Submit
  const handleTransferSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!transferFile) return;
    if (!transferDestLocationId.trim()) {
      setTransferError("Destination storage location is required.");
      return;
    }
    if (!transferReason.trim()) {
      setTransferError("Transfer reason is required.");
      return;
    }

    setTransferSubmitting(true);
    setTransferError(null);
    try {
      await api.transferPhysicalFile(transferFile.id, {
        destination_location_id: transferDestLocationId.trim(),
        reason: transferReason.trim(),
      });

      const updated = await api.getPhysicalFile(transferFile.id);
      setTransferFile(null);
      if (viewFileId === updated.id) {
        setDetailFile(updated);
      }
      fetchFiles();
    } catch (err: any) {
      setTransferError(err.message || "Failed to transfer physical file.");
    } finally {
      setTransferSubmitting(false);
    }
  };

  // Open Edit Modal
  const handleOpenEdit = (file: PhysicalFileDetail) => {
    fetchStorageLocs();
    fetchDocs();
    setEditFile(file);
    setEditTitle(file.title);
    setEditDescription(file.description || "");
    setEditRecordType(file.record_type);
    setEditDepartment(file.department);
    setEditClassification(file.classification || "");
    setEditExtRef(file.external_reference || "");
    setEditDigitalDocId(file.digital_document_id || "");
    setEditUnlinkDigital(false);
    setEditStorageLocationId(file.storage_location_id || "");
    setEditUnlinkLocation(false);
    setEditError(null);
  };

  // Handle Register Submit
  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!regTitle.trim()) {
      setRegError("Title is required.");
      return;
    }
    if (!regDepartment.trim()) {
      setRegError("Department is required.");
      return;
    }

    setRegSubmitting(true);
    setRegError(null);
    setRegSuccessMsg(null);

    try {
      const payload: RegisterPhysicalFilePayload = {
        title: regTitle.trim(),
        description: regDescription.trim() || null,
        record_type: regRecordType,
        department: regDepartment.trim(),
        classification: regClassification.trim() || null,
        external_reference: regExtRef.trim() || null,
        digital_document_id: regDigitalDocId.trim() || null,
        storage_location_id: regStorageLocationId.trim() || null,
      };

      const created = await api.registerPhysicalFile(payload);
      setRegSuccessMsg(`Successfully registered ${created.file_reference}`);
      setTimeout(() => {
        setShowRegisterModal(false);
        setRegSuccessMsg(null);
        setRegTitle("");
        setRegDescription("");
        setRegExtRef("");
        setRegDigitalDocId("");
        setRegStorageLocationId("");
        fetchFiles();
      }, 1000);
    } catch (err: any) {
      setRegError(err.message || "Failed to register physical file.");
    } finally {
      setRegSubmitting(false);
    }
  };

  // Handle Edit Submit
  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editFile) return;

    setEditSubmitting(true);
    setEditError(null);

    try {
      const payload: UpdatePhysicalFilePayload = {
        title: editTitle.trim() || null,
        description: editDescription.trim() || null,
        record_type: editRecordType,
        department:
          user?.role === "admin" || user?.role === "records_officer"
            ? editDepartment.trim() || null
            : undefined,
        classification: editClassification.trim() || null,
        external_reference: editExtRef.trim() || null,
        unlink_digital_document: editUnlinkDigital,
        digital_document_id:
          !editUnlinkDigital && editDigitalDocId.trim()
            ? editDigitalDocId.trim()
            : undefined,
        unlink_storage_location: editUnlinkLocation,
        storage_location_id:
          !editUnlinkLocation && editStorageLocationId.trim()
            ? editStorageLocationId.trim()
            : undefined,
      };

      const updated = await api.updatePhysicalFile(editFile.id, payload);
      setEditFile(null);
      if (viewFileId === updated.id) {
        setDetailFile(updated);
      }
      fetchFiles();
    } catch (err: any) {
      setEditError(err.message || "Failed to update physical file.");
    } finally {
      setEditSubmitting(false);
    }
  };

  // Handle Assign Location Submit
  const handleAssignLocationSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!assignModalFile) return;

    setAssignSubmitting(true);
    setAssignError(null);

    try {
      const updated = await api.assignFileLocation(assignModalFile.id, {
        storage_location_id: assignLocationId.trim() ? assignLocationId.trim() : null,
      });
      setAssignModalFile(null);
      setAssignLocationId("");
      if (viewFileId === updated.id) {
        setDetailFile(updated);
      }
      fetchFiles();
    } catch (err: any) {
      setAssignError(err.message || "Failed to assign storage location.");
    } finally {
      setAssignSubmitting(false);
    }
  };

  // Handle Status Transition Submit
  const handleStatusTransitionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!statusConfirmFile) return;

    setStatusSubmitting(true);
    setStatusError(null);

    try {
      const updated = await api.changePhysicalFileStatus(statusConfirmFile.file.id, {
        status: statusConfirmFile.targetStatus,
        reason: statusReason.trim() || undefined,
      });

      setStatusConfirmFile(null);
      setStatusReason("");
      if (viewFileId === updated.id) {
        setDetailFile(updated);
      }
      fetchFiles();
    } catch (err: any) {
      setStatusError(err.message || "Failed to transition file status.");
    } finally {
      setStatusSubmitting(false);
    }
  };

  const canRegister =
    user?.role === "admin" ||
    user?.role === "records_officer" ||
    user?.role === "department_user";

  const canEditRecord = (fileDept: string) => {
    if (!user) return false;
    if (user.role === "admin" || user.role === "records_officer") return true;
    if (user.role === "department_user") {
      return (user.department || "").toLowerCase() === fileDept.toLowerCase();
    }
    return false;
  };

  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4 sm:px-6 lg:px-8 w-full">
      <div className="w-full space-y-6">
        {/* Page Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-200 pb-5">
          <div>
            <div className="flex items-center space-x-3">
              <div className="p-2.5 bg-blue-600 text-white rounded-xl shadow-sm">
                <FolderArchive className="w-6 h-6" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                  Physical File Registry
                </h1>
                <p className="text-sm text-slate-500">
                  Manage paper files, hardcopy contracts, and governed physical record archives.
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={() => fetchFiles()}
              className="inline-flex items-center px-3.5 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 transition-colors shadow-sm"
            >
              <RefreshCw className="w-4 h-4 mr-2 text-slate-500" />
              Refresh
            </button>

            <button
              onClick={() => setShowScanModal(true)}
              className="inline-flex items-center px-3.5 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 transition-colors shadow-sm"
              title="Scan QR Code or Look Up Reference"
            >
              <QrCode className="w-4 h-4 mr-2 text-blue-600" />
              Scan / Lookup
            </button>

            {canRegister && (
              <button
                onClick={() => setShowRegisterModal(true)}
                className="inline-flex items-center px-4 py-2 border border-transparent rounded-lg text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 transition-colors shadow-sm"
              >
                <Plus className="w-4 h-4 mr-2" />
                Register Physical File
              </button>
            )}
          </div>
        </div>

        {/* Tab Switcher */}
        <div className="flex border-b border-slate-200 space-x-6 overflow-x-auto">
          <button
            onClick={() => setActiveTab("registry")}
            className={`pb-3 text-sm font-semibold flex items-center space-x-2 border-b-2 whitespace-nowrap transition-colors ${
              activeTab === "registry"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            <FolderArchive className="w-4 h-4" />
            <span>Physical File Registry</span>
            <span className="ml-1.5 px-2 py-0.5 rounded-full text-xs font-normal bg-slate-100 text-slate-600">
              {totalCount}
            </span>
          </button>

          <button
            onClick={() => setActiveTab("overdue")}
            className={`pb-3 text-sm font-semibold flex items-center space-x-2 border-b-2 whitespace-nowrap transition-colors ${
              activeTab === "overdue"
                ? "border-rose-600 text-rose-600"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            <AlertTriangle className="w-4 h-4 text-rose-600" />
            <span>Overdue Circulation</span>
            {overdueTotal > 0 && (
              <span className="ml-1.5 px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-100 text-rose-700">
                {overdueTotal}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab("transfers")}
            aria-label="Location Transfers Tab"
            className={`pb-3 text-sm font-semibold flex items-center space-x-2 border-b-2 whitespace-nowrap transition-colors ${
              activeTab === "transfers"
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            <ArrowRightLeft className="w-4 h-4 text-indigo-600" />
            <span>Location Transfers</span>
            {transfersTotal > 0 && (
              <span className="ml-1.5 px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-700">
                {transfersTotal}
              </span>
            )}
          </button>

          {(user?.role === "admin" || user?.role === "records_officer") && (
            <button
              onClick={() => setActiveTab("integrity")}
              className={`pb-3 text-sm font-semibold flex items-center space-x-2 border-b-2 whitespace-nowrap transition-colors ${
                activeTab === "integrity"
                  ? "border-amber-600 text-amber-600"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              <ShieldCheck className="w-4 h-4 text-amber-600" />
              <span>Custody Integrity Diagnostic</span>
              {integrityReport && integrityReport.total_issues_found > 0 && (
                <span className="ml-1.5 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">
                  {integrityReport.total_issues_found}
                </span>
              )}
            </button>
          )}
        </div>

        {activeTab === "registry" ? (
          <>
            {/* Filters Bar */}
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-3">
          <form onSubmit={handleSearchSubmit} className="flex flex-col md:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="text"
                placeholder="Search reference, title, or external ref..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-9 pr-4 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {(user?.role === "admin" || user?.role === "records_officer") && (
                <select
                  value={selectedDept}
                  onChange={(e) => {
                    setSelectedDept(e.target.value);
                    setPage(1);
                  }}
                  className="px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white text-slate-700"
                >
                  <option value="">All Departments</option>
                  {DEPARTMENTS.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              )}

              <select
                value={selectedRecordType}
                onChange={(e) => {
                  setSelectedRecordType(e.target.value);
                  setPage(1);
                }}
                className="px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white text-slate-700"
              >
                <option value="">All Record Types</option>
                {RECORD_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>

              <select
                value={selectedStatus}
                onChange={(e) => {
                  setSelectedStatus(e.target.value);
                  setPage(1);
                }}
                className="px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white text-slate-700"
              >
                <option value="">All Statuses</option>
                <option value="active">Active</option>
                <option value="archived">Archived</option>
                <option value="inactive">Inactive</option>
              </select>

              <select
                value={selectedCustodyState}
                aria-label="Circulation State Filter"
                onChange={(e) => {
                  setSelectedCustodyState(e.target.value);
                  setPage(1);
                }}
                className="px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white text-slate-700"
              >
                <option value="">All Circulation</option>
                <option value="stored">Stored Files</option>
                <option value="checked_out">Checked Out Files</option>
                <option value="overdue">Overdue Files</option>
              </select>

              <select
                value={selectedClassification}
                onChange={(e) => {
                  setSelectedClassification(e.target.value);
                  setPage(1);
                }}
                className="px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white text-slate-700"
              >
                <option value="">All Classifications</option>
                {CLASSIFICATIONS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>

              <button
                type="submit"
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 text-sm font-medium rounded-lg transition-colors"
              >
                Filter
              </button>

              {(user?.role === "admin" || user?.role === "records_officer") && (
                <button
                  type="button"
                  onClick={() => handleExportCsv("checked_out")}
                  disabled={exportLoading}
                  className="inline-flex items-center px-3.5 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 transition-colors shadow-sm disabled:opacity-50"
                  title="Export Active Circulation Inventory to Governed CSV"
                >
                  <FileSpreadsheet className="w-4 h-4 mr-1.5 text-emerald-600" />
                  {exportLoading ? "Exporting..." : "Export Circulation CSV"}
                </button>
              )}
            </div>
          </form>
        </div>

        {/* Registry Table / Card */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          {loading ? (
            <div className="py-16 text-center space-y-3">
              <RefreshCw className="w-8 h-8 text-blue-600 animate-spin mx-auto" />
              <p className="text-sm text-slate-500">Loading physical file registry...</p>
            </div>
          ) : error ? (
            <div className="py-12 text-center px-4">
              <AlertCircle className="w-10 h-10 text-red-500 mx-auto mb-2" />
              <p className="text-sm font-semibold text-slate-800">Failed to load registry</p>
              <p className="text-xs text-red-600 mt-1">{error}</p>
              <button
                onClick={fetchFiles}
                className="mt-4 px-4 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium"
              >
                Retry
              </button>
            </div>
          ) : files.length === 0 ? (
            <div className="py-16 text-center px-4 space-y-3">
              <FolderArchive className="w-12 h-12 text-slate-300 mx-auto" />
              <h3 className="text-base font-semibold text-slate-800">No physical files found</h3>
              <p className="text-sm text-slate-500 max-w-sm mx-auto">
                No physical files match the selected filter criteria or department permissions.
              </p>
              {canRegister && (
                <button
                  onClick={() => setShowRegisterModal(true)}
                  className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700"
                >
                  <Plus className="w-4 h-4 mr-2" />
                  Register First File
                </button>
              )}
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Reference
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Title & Type
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Department
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Classification
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Storage Location
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Custody & Circulation
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Digital Link
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-slate-200">
                    {files.map((file) => (
                      <tr key={file.id} className="hover:bg-slate-50/75 transition-colors">
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center space-x-2">
                            <button
                              onClick={() => handleOpenDetail(file.id)}
                              className="font-mono text-xs font-bold text-blue-600 bg-blue-50 hover:bg-blue-100 px-2 py-1 rounded transition-colors text-left hover:underline"
                              title="Click to view file details and custody"
                            >
                              {file.file_reference}
                            </button>
                            <button
                              onClick={() => setPrintLabelFile(file)}
                              className="p-1 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors"
                              title="Preview Barcode & QR Code Label"
                            >
                              <QrCode className="w-4 h-4 text-slate-500 hover:text-blue-600" />
                            </button>
                          </div>
                          {file.external_reference && (
                            <div className="text-[11px] text-slate-400 mt-0.5">
                              Ext: {file.external_reference}
                            </div>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          <button
                            onClick={() => handleOpenDetail(file.id)}
                            className="text-sm font-semibold text-slate-900 hover:text-blue-600 hover:underline text-left block"
                            title="Click to view file details and custody"
                          >
                            {file.title}
                          </button>
                          <div className="text-xs text-slate-500 capitalize">
                            {file.record_type.replace("_", " ")}
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-700">
                          {file.department}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {file.classification ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">
                              {file.classification}
                            </span>
                          ) : (
                            <span className="text-xs text-slate-400">—</span>
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {file.storage_location_name ? (
                            <div>
                              <div className="text-xs font-medium text-slate-900 flex items-center">
                                <MapPin className="w-3.5 h-3.5 mr-1 text-blue-600" />
                                {file.storage_location_name}
                              </div>
                              <div className="text-[11px] text-slate-400 font-mono">
                                {file.storage_location_code}
                              </div>
                            </div>
                          ) : (
                            <span className="text-xs text-slate-400 italic">Unassigned</span>
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {file.is_checked_out ? (
                            <div className="space-y-0.5">
                              <span
                                className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${
                                  file.is_overdue
                                    ? "bg-rose-50 text-rose-700 border border-rose-200"
                                    : "bg-amber-50 text-amber-700 border border-amber-200"
                                }`}
                              >
                                {file.is_overdue ? (
                                  <>
                                    <AlertTriangle className="w-3 h-3 mr-1 text-rose-600" />
                                    Overdue
                                  </>
                                ) : (
                                  <>
                                    <LogOut className="w-3 h-3 mr-1 text-amber-600" />
                                    Checked Out
                                  </>
                                )}
                              </span>
                              {file.current_custodian_name && (
                                <div className="text-[11px] text-slate-600 truncate max-w-[130px]" title={file.current_custodian_name}>
                                  To: {file.current_custodian_name}
                                </div>
                              )}
                            </div>
                          ) : (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-600">
                              <LogIn className="w-3 h-3 mr-1 text-slate-400" />
                              Stored
                            </span>
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium capitalize ${
                              file.status === "active"
                                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                : file.status === "archived"
                                ? "bg-amber-50 text-amber-700 border border-amber-200"
                                : "bg-slate-100 text-slate-600 border border-slate-200"
                            }`}
                          >
                            {file.status}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {file.has_digital_document ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-indigo-50 text-indigo-700">
                              <FileText className="w-3 h-3 mr-1" />
                              Linked
                            </span>
                          ) : (
                            <span className="text-xs text-slate-400">None</span>
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                          <div className="flex items-center justify-end space-x-2">
                            <button
                              onClick={() => setPrintLabelFile(file)}
                              className="p-1.5 text-slate-600 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                              title="Print Label (Barcode / QR)"
                            >
                              <Printer className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleOpenDetail(file.id)}
                              className="p-1.5 text-slate-600 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                              title="View Details"
                            >
                              <Eye className="w-4 h-4" />
                            </button>
                            {canEditRecord(file.department) && (
                              <button
                                onClick={() => handleOpenDetail(file.id)}
                                className="p-1.5 text-slate-600 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                                title="Edit / Update"
                              >
                                <Edit2 className="w-4 h-4" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination Bar */}
              <div className="px-6 py-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-600">
                <div>
                  Showing {files.length} of {totalCount} total physical files
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    className="p-1.5 border border-slate-300 rounded hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <span className="font-semibold text-slate-800">
                    Page {page} of {totalPages}
                  </span>
                  <button
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    className="p-1.5 border border-slate-300 rounded hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </>
    ) : activeTab === "overdue" ? (
      /* Overdue Circulation View */
      <div className="space-y-4">
        {/* Overdue Filters & Export Bar */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
            <div className="relative flex-1 md:w-64">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="text"
                placeholder="Filter by custodian..."
                value={overdueCustodianFilter}
                onChange={(e) => setOverdueCustodianFilter(e.target.value)}
                className="w-full pl-9 pr-4 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-500"
              />
            </div>

            <div className="w-36">
              <input
                type="number"
                min="0"
                placeholder="Min days overdue"
                value={overdueMinDaysFilter}
                onChange={(e) => setOverdueMinDaysFilter(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-500"
              />
            </div>

            <button
              onClick={() => {
                setOverduePage(1);
                fetchOverdueFiles();
              }}
              className="px-4 py-2 bg-rose-50 hover:bg-rose-100 text-rose-700 text-sm font-medium rounded-lg transition-colors border border-rose-200"
            >
              Filter Overdue
            </button>
          </div>

          <div className="flex items-center space-x-2 w-full md:w-auto justify-end">
            {(user?.role === "admin" || user?.role === "records_officer") && (
              <button
                type="button"
                onClick={() => handleExportCsv("overdue")}
                disabled={exportLoading}
                className="inline-flex items-center px-3.5 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 transition-colors shadow-sm disabled:opacity-50"
                title="Export Overdue Physical Files to Governed CSV"
              >
                <FileSpreadsheet className="w-4 h-4 mr-1.5 text-rose-600" />
                {exportLoading ? "Exporting..." : "Export Overdue CSV"}
              </button>
            )}

            <button
              onClick={fetchOverdueFiles}
              className="inline-flex items-center px-3 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 shadow-sm"
            >
              <RefreshCw className="w-3.5 h-3.5 mr-1 text-slate-500" />
              Refresh
            </button>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-rose-50/40">
            <div>
              <h2 className="text-base font-bold text-slate-900 flex items-center">
                <AlertTriangle className="w-5 h-5 mr-2 text-rose-600" />
                Overdue Checked-Out Physical Records
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Physical records whose expected return date has elapsed without check-in.
              </p>
            </div>
          </div>

          {overdueLoading ? (
            <div className="py-16 text-center space-y-3">
              <RefreshCw className="w-8 h-8 text-rose-600 animate-spin mx-auto" />
              <p className="text-sm text-slate-500">Checking for overdue physical files...</p>
            </div>
          ) : overdueError ? (
            <div className="py-12 text-center px-4">
              <AlertCircle className="w-8 h-8 text-rose-500 mx-auto mb-2" />
              <p className="text-sm text-rose-600 font-medium">{overdueError}</p>
              <button
                onClick={fetchOverdueFiles}
                className="mt-4 px-4 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium"
              >
                Retry
              </button>
            </div>
          ) : overdueFiles.length === 0 ? (
            <div className="py-16 text-center px-4 space-y-3">
              <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
              <h3 className="text-base font-semibold text-slate-800">No overdue physical records</h3>
              <p className="text-sm text-slate-500 max-w-sm mx-auto">
                All active checked-out physical files are within their expected return schedules.
              </p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        File Reference & Title
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Department
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Current Custodian
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Location
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Checked Out On
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Expected Return
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Days Overdue
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-slate-200">
                    {overdueFiles.map((item) => (
                      <tr key={item.custody_record_id} className="hover:bg-rose-50/40 transition-colors">
                        <td className="px-6 py-4">
                          <span className="font-mono text-xs font-bold text-rose-700 bg-rose-50 px-2 py-0.5 rounded border border-rose-200">
                            {item.file_reference}
                          </span>
                          <div className="text-sm font-semibold text-slate-900 mt-1">{item.title}</div>
                          {item.purpose && (
                            <div className="text-xs text-slate-500 italic mt-0.5">Purpose: {item.purpose}</div>
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-700">
                          {item.department}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm font-semibold text-slate-900">{item.custodian_name}</div>
                          <div className="text-xs text-slate-500">
                            {item.custodian_department || "No dept"}
                            {item.custodian_contact ? ` • ${item.custodian_contact}` : ""}
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-xs text-slate-600">
                          {item.storage_location_name ? (
                            <span className="inline-flex items-center text-slate-700 font-medium">
                              <MapPin className="w-3.5 h-3.5 mr-1 text-slate-400" />
                              {item.storage_location_name}
                            </span>
                          ) : (
                            <span className="text-slate-400 italic">Unassigned</span>
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-xs text-slate-600">
                          {new Date(item.checked_out_at).toLocaleDateString()}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-xs font-medium text-rose-600">
                          {new Date(item.expected_return_at).toLocaleDateString()}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-rose-100 text-rose-800">
                            <AlertTriangle className="w-3 h-3 mr-1 text-rose-600" />
                            {item.days_overdue} {item.days_overdue === 1 ? "day" : "days"} overdue
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                          <button
                            onClick={() => handleOpenDetail(item.physical_file_id)}
                            className="inline-flex items-center px-3 py-1.5 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-lg text-xs font-semibold"
                          >
                            <Eye className="w-3.5 h-3.5 mr-1" />
                            View / Check In
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Overdue Pagination */}
              <div className="px-6 py-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-600">
                <div>
                  Showing {overdueFiles.length} of {overdueTotal} overdue files
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    disabled={overduePage <= 1}
                    onClick={() => setOverduePage((p) => Math.max(1, p - 1))}
                    className="p-1.5 border border-slate-300 rounded hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <span className="font-semibold text-slate-800">
                    Page {overduePage} of {overdueTotalPages}
                  </span>
                  <button
                    disabled={overduePage >= overdueTotalPages}
                    onClick={() => setOverduePage((p) => Math.min(overdueTotalPages, p + 1))}
                    className="p-1.5 border border-slate-300 rounded hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    ) : activeTab === "transfers" ? (
      /* Location Transfers Governance Report View */
      <div className="space-y-4">
        {/* Transfers Date Filter & Export Bar */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
            <div className="flex items-center space-x-2">
              <span className="text-xs font-semibold text-slate-600">From:</span>
              <input
                type="date"
                value={transfersStartDate}
                onChange={(e) => setTransfersStartDate(e.target.value)}
                className="px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
              />
            </div>

            <div className="flex items-center space-x-2">
              <span className="text-xs font-semibold text-slate-600">To:</span>
              <input
                type="date"
                value={transfersEndDate}
                onChange={(e) => setTransfersEndDate(e.target.value)}
                className="px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
              />
            </div>

            <button
              onClick={() => {
                setTransfersPage(1);
                fetchTransfers();
              }}
              className="px-4 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-sm font-medium rounded-lg transition-colors border border-indigo-200"
            >
              Filter Transfers
            </button>
          </div>

          <div className="flex items-center space-x-2 w-full md:w-auto justify-end">
            {(user?.role === "admin" || user?.role === "records_officer") && (
              <button
                type="button"
                onClick={() => handleExportCsv("transfers")}
                disabled={exportLoading}
                className="inline-flex items-center px-3.5 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 transition-colors shadow-sm disabled:opacity-50"
                title="Export Storage Location Transfers to Governed CSV"
              >
                <FileSpreadsheet className="w-4 h-4 mr-1.5 text-indigo-600" />
                {exportLoading ? "Exporting..." : "Export Transfers CSV"}
              </button>
            )}

            <button
              onClick={fetchTransfers}
              className="inline-flex items-center px-3 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 shadow-sm"
            >
              <RefreshCw className="w-3.5 h-3.5 mr-1 text-slate-500" />
              Refresh
            </button>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-indigo-50/40">
            <div>
              <h2 className="text-base font-bold text-slate-900 flex items-center">
                <ArrowRightLeft className="w-5 h-5 mr-2 text-indigo-600" />
                Storage Location Transfers History
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Audit trail of physical file transfers between shelves, rooms, boxes, and repositories.
              </p>
            </div>
          </div>

          {transfersLoading ? (
            <div className="py-16 text-center space-y-3">
              <RefreshCw className="w-8 h-8 text-indigo-600 animate-spin mx-auto" />
              <p className="text-sm text-slate-500">Loading storage transfers history...</p>
            </div>
          ) : transfersError ? (
            <div className="py-12 text-center px-4">
              <AlertCircle className="w-8 h-8 text-rose-500 mx-auto mb-2" />
              <p className="text-sm text-rose-600 font-medium">{transfersError}</p>
              <button
                onClick={fetchTransfers}
                className="mt-4 px-4 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium"
              >
                Retry
              </button>
            </div>
          ) : transfers.length === 0 ? (
            <div className="py-16 text-center px-4 space-y-3">
              <CheckCircle2 className="w-12 h-12 text-slate-300 mx-auto" />
              <h3 className="text-base font-semibold text-slate-800">No transfer records found</h3>
              <p className="text-sm text-slate-500 max-w-sm mx-auto">
                No storage location transfers have been logged matching the selected date and department filters.
              </p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Date & Time
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        File Reference & Title
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        From Location
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        To Location
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Reason & Performed By
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-slate-200">
                    {transfers.map((item) => (
                      <tr key={item.movement_id} className="hover:bg-slate-50/60 transition-colors">
                        <td className="px-6 py-4 whitespace-nowrap text-xs text-slate-600">
                          {new Date(item.transferred_at).toLocaleString()}
                        </td>
                        <td className="px-6 py-4">
                          <span className="font-mono text-xs font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                            {item.file_reference}
                          </span>
                          <div className="text-sm font-semibold text-slate-900 mt-1">{item.title}</div>
                          <div className="text-xs text-slate-500">{item.department}</div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-xs">
                          {item.source_location_name ? (
                            <span className="inline-flex items-center text-slate-700 font-medium">
                              <MapPin className="w-3.5 h-3.5 mr-1 text-slate-400" />
                              {item.source_location_name}
                            </span>
                          ) : (
                            <span className="text-slate-400 italic">None</span>
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-xs">
                          {item.destination_location_name ? (
                            <span className="inline-flex items-center text-indigo-700 font-semibold bg-indigo-50 px-2 py-0.5 rounded">
                              <MapPin className="w-3.5 h-3.5 mr-1 text-indigo-500" />
                              {item.destination_location_name}
                            </span>
                          ) : (
                            <span className="text-slate-400 italic">None</span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-xs text-slate-600">
                          <div className="font-medium text-slate-800">{item.reason || "Storage relocation"}</div>
                          <div className="text-slate-400 mt-0.5">By: {item.transferred_by?.full_name || item.transferred_by?.email || "System"}</div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                          <button
                            onClick={() => handleOpenDetail(item.physical_file_id)}
                            className="inline-flex items-center px-3 py-1.5 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 rounded-lg text-xs font-semibold"
                          >
                            <Eye className="w-3.5 h-3.5 mr-1" />
                            View File
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Transfers Pagination */}
              <div className="px-6 py-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-600">
                <div>
                  Showing {transfers.length} of {transfersTotal} transfer records
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    disabled={transfersPage <= 1}
                    onClick={() => setTransfersPage((p) => Math.max(1, p - 1))}
                    className="p-1.5 border border-slate-300 rounded hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <span className="font-semibold text-slate-800">
                    Page {transfersPage} of {transfersTotalPages}
                  </span>
                  <button
                    disabled={transfersPage >= transfersTotalPages}
                    onClick={() => setTransfersPage((p) => Math.min(transfersTotalPages, p + 1))}
                    className="p-1.5 border border-slate-300 rounded hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    ) : (
      /* Custody Integrity Diagnostic View */
      <div className="space-y-4">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-center justify-between gap-3">
          <div className="flex items-center space-x-3">
            <span className="text-xs font-semibold text-slate-600">Filter Severity:</span>
            <select
              value={integritySeverityFilter}
              onChange={(e) => setIntegritySeverityFilter(e.target.value)}
              className="px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white text-slate-700"
            >
              <option value="all">All Severities</option>
              <option value="error">Errors Only</option>
              <option value="warning">Warnings Only</option>
            </select>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={fetchIntegrityReport}
              className="inline-flex items-center px-3.5 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 shadow-sm"
            >
              <RefreshCw className="w-4 h-4 mr-2 text-slate-500" />
              Re-Scan Invariants
            </button>
          </div>
        </div>

        {/* Diagnostic Status Card */}
        {integrityLoading ? (
          <div className="bg-white rounded-xl border border-slate-200 p-12 text-center space-y-3">
            <RefreshCw className="w-8 h-8 text-amber-600 animate-spin mx-auto" />
            <p className="text-sm text-slate-500">Scanning repository for chain-of-custody invariants...</p>
          </div>
        ) : integrityError ? (
          <div className="bg-white rounded-xl border border-rose-200 p-8 text-center">
            <AlertCircle className="w-8 h-8 text-rose-500 mx-auto mb-2" />
            <p className="text-sm text-rose-600 font-medium">{integrityError}</p>
            <button
              onClick={fetchIntegrityReport}
              className="mt-4 px-4 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium"
            >
              Retry Diagnostic Scan
            </button>
          </div>
        ) : integrityReport ? (
          <div className="space-y-4">
            <div className={`p-4 rounded-xl border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 ${
              integrityReport.total_issues_found === 0
                ? "bg-emerald-50 border-emerald-200 text-emerald-900"
                : "bg-amber-50 border-amber-200 text-amber-900"
            }`}>
              <div className="flex items-center space-x-3">
                <div className={`p-2.5 rounded-lg ${
                  integrityReport.total_issues_found === 0
                    ? "bg-emerald-600 text-white"
                    : "bg-amber-600 text-white"
                }`}>
                  <ShieldCheck className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-base font-bold">
                    {integrityReport.total_issues_found === 0
                      ? "All Chain-of-Custody Invariants Verified"
                      : `${integrityReport.total_issues_found} Custody Invariant Inconsistencies Detected`}
                  </h3>
                  <p className="text-xs opacity-90 mt-0.5">
                    {integrityReport.total_files_scanned} physical records scanned.
                    {selectedDept ? ` Scoped to department: ${selectedDept}.` : " Organization-wide scan."}
                  </p>
                </div>
              </div>
            </div>

            {/* Invariant Issues List */}
            {integrityReport.items.length === 0 ? (
              <div className="bg-white rounded-xl border border-slate-200 p-12 text-center space-y-2">
                <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
                <h4 className="text-base font-semibold text-slate-800">Clean Chain of Custody</h4>
                <p className="text-sm text-slate-500 max-w-md mx-auto">
                  Every registered physical record has verified custody consistency, synchronized movement events, and matching storage locations.
                </p>
              </div>
            ) : (
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="p-4 border-b border-slate-200 bg-slate-50">
                  <h3 className="text-sm font-bold text-slate-800">Diagnostic Findings</h3>
                </div>
                <div className="divide-y divide-slate-100">
                  {integrityReport.items
                    .filter(
                      (issue) =>
                        integritySeverityFilter === "all" ||
                        issue.severity.toLowerCase() === integritySeverityFilter
                    )
                    .map((issue: CustodyIntegrityIssue, idx: number) => (
                      <div key={idx} className="p-4 hover:bg-slate-50/70 transition-colors flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                        <div className="space-y-1 max-w-2xl">
                          <div className="flex items-center space-x-2">
                            <span className="font-mono text-xs font-bold text-slate-800 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                              {issue.file_reference}
                            </span>
                            <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wide ${
                              issue.severity === "error"
                                ? "bg-rose-100 text-rose-800 border border-rose-200"
                                : "bg-amber-100 text-amber-800 border border-amber-200"
                            }`}>
                              {issue.severity}
                            </span>
                            <span className="text-xs font-semibold text-slate-600 bg-slate-50 px-2 py-0.5 rounded">
                              {issue.issue_type}
                            </span>
                          </div>
                          <div className="text-sm font-bold text-slate-900">{issue.title}</div>
                          <p className="text-xs text-slate-600">{issue.description}</p>
                        </div>

                        <div className="flex items-center space-x-2">
                          <button
                            onClick={() => handleOpenDetail(issue.physical_file_id)}
                            className="inline-flex items-center px-3 py-1.5 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-lg text-xs font-semibold"
                          >
                            <Eye className="w-3.5 h-3.5 mr-1" />
                            Investigate / View File
                          </button>
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </div>
        ) : null}
      </div>
    )}
  </div>

      {/* Registration Modal */}
      {showRegisterModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 max-w-lg w-full overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center space-x-2">
                <FolderArchive className="w-5 h-5 text-blue-600" />
                <h3 className="text-base font-bold text-slate-900">Register Physical Record</h3>
              </div>
              <button
                onClick={() => setShowRegisterModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleRegisterSubmit} className="p-6 space-y-4">
              {regError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                  {regError}
                </div>
              )}
              {regSuccessMsg && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-700">
                  {regSuccessMsg}
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Title <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Master Services Agreement 2026 Original"
                  value={regTitle}
                  onChange={(e) => setRegTitle(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Record Type <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={regRecordType}
                    onChange={(e) => setRegRecordType(e.target.value as PhysicalRecordType)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                  >
                    {RECORD_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Department <span className="text-red-500">*</span>
                  </label>
                  {user?.role === "department_user" ? (
                    <input
                      type="text"
                      disabled
                      value={regDepartment}
                      className="w-full px-3 py-2 text-sm border border-slate-200 bg-slate-50 text-slate-500 rounded-lg"
                    />
                  ) : (
                    <select
                      value={regDepartment}
                      onChange={(e) => setRegDepartment(e.target.value)}
                      className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                    >
                      {DEPARTMENTS.map((d) => (
                        <option key={d} value={d}>
                          {d}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Classification
                  </label>
                  <select
                    value={regClassification}
                    onChange={(e) => setRegClassification(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                  >
                    <option value="">None / Unclassified</option>
                    {CLASSIFICATIONS.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    External Reference
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. BARCODE-9942, ARCH-12"
                    value={regExtRef}
                    onChange={(e) => setRegExtRef(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Linked Digital Document (Optional)
                </label>
                <select
                  value={regDigitalDocId}
                  onChange={(e) => setRegDigitalDocId(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  <option value="">-- No Digital Document (Unlinked) --</option>
                  {availableDocs.map((doc) => (
                    <option key={doc.id} value={doc.id}>
                      {doc.title} ({doc.document_reference}) - {doc.department}
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Associates physical file with an authorized existing digital record.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Storage Location (Optional)
                </label>
                <select
                  value={regStorageLocationId}
                  onChange={(e) => setRegStorageLocationId(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  <option value="">-- No Storage Location Assigned --</option>
                  {availableLocations.map((loc) => (
                    <option key={loc.id} value={loc.id}>
                      {loc.name} ({loc.location_code}) - {loc.department}
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Initial shelf, box, cabinet, or room location for this physical file.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Description / Content Summary
                </label>
                <textarea
                  rows={3}
                  placeholder="Physical binder contents, signatory details, physical location notes..."
                  value={regDescription}
                  onChange={(e) => setRegDescription(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setShowRegisterModal(false)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={regSubmitting}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium shadow-sm disabled:opacity-50"
                >
                  {regSubmitting ? "Registering..." : "Register File"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Detail & Status Modal Drawer */}
      {viewFileId && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center space-x-2">
                <FolderArchive className="w-5 h-5 text-blue-600" />
                <h3 className="text-base font-bold text-slate-900">
                  {detailFile ? detailFile.file_reference : "Physical File Details"}
                </h3>
              </div>
              <button
                onClick={() => {
                  setViewFileId(null);
                  setDetailFile(null);
                }}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-6">
              {detailLoading ? (
                <div className="py-12 text-center">
                  <RefreshCw className="w-8 h-8 text-blue-600 animate-spin mx-auto mb-2" />
                  <p className="text-xs text-slate-500">Loading record metadata...</p>
                </div>
              ) : detailError ? (
                <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                  {detailError}
                </div>
              ) : detailFile ? (
                <>
                  {/* Top Bar Status & Actions */}
                  <div className="bg-slate-50/80 rounded-xl border border-slate-200 p-4 space-y-3">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-200/70">
                      <div>
                        <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
                          Lifecycle Status
                        </span>
                        <div className="flex items-center gap-2 mt-1">
                          <span
                            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold capitalize ${
                              detailFile.status === "active"
                                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                : detailFile.status === "archived"
                                ? "bg-amber-50 text-amber-700 border border-amber-200"
                                : "bg-slate-100 text-slate-600 border border-slate-200"
                            }`}
                          >
                            <span
                              className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
                                detailFile.status === "active"
                                  ? "bg-emerald-500"
                                  : detailFile.status === "archived"
                                  ? "bg-amber-500"
                                  : "bg-slate-400"
                              }`}
                            />
                            {detailFile.status}
                          </span>
                        </div>
                      </div>

                      {/* Primary Utility Actions: Print, History, Edit */}
                      <div className="flex items-center flex-wrap gap-2">
                        <button
                          onClick={() => setPrintLabelFile(detailFile)}
                          className="inline-flex items-center px-3 py-1.5 bg-white border border-slate-200 hover:border-blue-300 hover:bg-blue-50/50 hover:text-blue-700 text-slate-700 text-xs font-semibold rounded-lg shadow-2xs transition-colors"
                          title="Print Label & Barcodes"
                        >
                          <Printer className="w-3.5 h-3.5 mr-1.5 text-blue-600" />
                          Print Label
                        </button>

                        <button
                          onClick={() => handleOpenHistory(detailFile)}
                          className="inline-flex items-center px-3 py-1.5 bg-white border border-slate-200 hover:border-slate-300 hover:bg-slate-100 text-slate-700 text-xs font-semibold rounded-lg shadow-2xs transition-colors"
                          title="View Movement and Custody History"
                        >
                          <History className="w-3.5 h-3.5 mr-1.5 text-slate-500" />
                          Movement History
                        </button>

                        {canEditRecord(detailFile.department) && (
                          <button
                            onClick={() => handleOpenEdit(detailFile)}
                            className="inline-flex items-center px-3 py-1.5 bg-white border border-slate-200 hover:border-slate-300 hover:bg-slate-100 text-slate-700 text-xs font-semibold rounded-lg shadow-2xs transition-colors"
                            title="Edit Record Metadata"
                          >
                            <Edit2 className="w-3.5 h-3.5 mr-1.5 text-slate-500" />
                            Edit Metadata
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Governance Lifecycle Transition Bar (Archive / Deactivate / Reactivate) */}
                    {canEditRecord(detailFile.department) && (
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-0.5">
                        <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                          Lifecycle Control
                        </span>
                        <div className="flex items-center flex-wrap gap-2">
                          {detailFile.status === "active" && (
                            <>
                              <button
                                onClick={() =>
                                  setStatusConfirmFile({
                                    file: detailFile,
                                    targetStatus: "archived",
                                  })
                                }
                                className="inline-flex items-center px-3 py-1.5 bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200 rounded-lg text-xs font-semibold transition-colors"
                              >
                                <FolderArchive className="w-3.5 h-3.5 mr-1.5 text-amber-600" />
                                Archive Record
                              </button>
                              <button
                                onClick={() =>
                                  setStatusConfirmFile({
                                    file: detailFile,
                                    targetStatus: "inactive",
                                  })
                                }
                                className="inline-flex items-center px-3 py-1.5 bg-slate-100 hover:bg-red-50 hover:text-red-700 hover:border-red-200 text-slate-700 border border-slate-200 rounded-lg text-xs font-semibold transition-colors"
                              >
                                <AlertCircle className="w-3.5 h-3.5 mr-1.5 text-slate-500" />
                                Deactivate
                              </button>
                            </>
                          )}

                          {(detailFile.status === "archived" || detailFile.status === "inactive") && (
                            <button
                              onClick={() =>
                                setStatusConfirmFile({
                                  file: detailFile,
                                  targetStatus: "active",
                                })
                              }
                              className="inline-flex items-center px-3 py-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200 rounded-lg text-xs font-semibold transition-colors"
                            >
                              <CheckCircle2 className="w-3.5 h-3.5 mr-1.5 text-emerald-600" />
                              Reactivate Record
                            </button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Metadata Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <span className="text-xs font-medium text-slate-500">Title</span>
                      <p className="text-sm font-semibold text-slate-900 mt-0.5">
                        {detailFile.title}
                      </p>
                    </div>

                    <div>
                      <span className="text-xs font-medium text-slate-500">Record Type</span>
                      <p className="text-sm font-semibold text-slate-900 mt-0.5 capitalize">
                        {detailFile.record_type.replace("_", " ")}
                      </p>
                    </div>

                    <div>
                      <span className="text-xs font-medium text-slate-500">Department</span>
                      <p className="text-sm font-semibold text-slate-900 mt-0.5">
                        {detailFile.department}
                      </p>
                    </div>

                    <div>
                      <span className="text-xs font-medium text-slate-500">Classification</span>
                      <p className="text-sm font-semibold text-slate-900 mt-0.5">
                        {detailFile.classification || "Unclassified"}
                      </p>
                    </div>

                    <div>
                      <span className="text-xs font-medium text-slate-500">
                        External Reference
                      </span>
                      <p className="text-sm font-semibold text-slate-900 mt-0.5 font-mono">
                        {detailFile.external_reference || "None"}
                      </p>
                    </div>

                    <div>
                      <span className="text-xs font-medium text-slate-500">Date Received</span>
                      <p className="text-sm font-semibold text-slate-900 mt-0.5">
                        {new Date(detailFile.date_received).toLocaleDateString()}
                      </p>
                    </div>
                  </div>

                  {/* Description */}
                  {detailFile.description && (
                    <div className="border-t border-slate-200 pt-4">
                      <span className="text-xs font-medium text-slate-500">Description</span>
                      <p className="text-sm text-slate-700 mt-1 whitespace-pre-line bg-slate-50 p-3 rounded-lg border border-slate-200">
                        {detailFile.description}
                      </p>
                    </div>
                  )}

                  {/* Linked Digital Document Box */}
                  <div className="border-t border-slate-200 pt-4">
                    <span className="text-xs font-semibold text-slate-600 uppercase tracking-wider block mb-2">
                      Associated Digital Document
                    </span>
                    {detailFile.digital_document ? (
                      <div className="p-3 bg-blue-50/70 border border-blue-200 rounded-xl flex items-center justify-between">
                        <div className="space-y-0.5">
                          <span className="font-mono text-xs font-bold text-blue-700">
                            {detailFile.digital_document.document_reference}
                          </span>
                          <p className="text-sm font-semibold text-slate-900">
                            {detailFile.digital_document.title}
                          </p>
                          <p className="text-xs text-slate-500">
                            Dept: {detailFile.digital_document.department} • Classification:{" "}
                            {detailFile.digital_document.classification}
                          </p>
                        </div>
                        <a
                          href={`/documents/${detailFile.digital_document.id}`}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center px-3 py-1.5 bg-white border border-blue-300 text-blue-700 text-xs font-medium rounded-lg hover:bg-blue-50 shadow-sm"
                        >
                          <ExternalLink className="w-3.5 h-3.5 mr-1" />
                          View Digital Record
                        </a>
                      </div>
                    ) : (
                      <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-500">
                        No digital document is currently linked to this physical file.
                      </div>
                    )}
                  </div>

                  {/* Storage Location Box */}
                  <div className="border-t border-slate-200 pt-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Storage Location
                      </span>
                      {canEditRecord(detailFile.department) && (
                        <button
                          onClick={() => {
                            setAssignModalFile(detailFile);
                            setAssignLocationId(detailFile.storage_location_id || "");
                            setAssignError(null);
                          }}
                          className="text-xs font-medium text-blue-600 hover:text-blue-800"
                        >
                          {detailFile.storage_location_id ? "Change / Reassign" : "Assign Location"}
                        </button>
                      )}
                    </div>
                    {detailFile.storage_location_name ? (
                      <div className="p-3 bg-emerald-50/70 border border-emerald-200 rounded-xl space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-sm text-slate-900 flex items-center">
                            <MapPin className="w-4 h-4 mr-1.5 text-emerald-600" />
                            {detailFile.storage_location_name}
                          </span>
                          <span className="font-mono text-xs font-bold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded">
                            {detailFile.storage_location_code}
                          </span>
                        </div>
                        {detailFile.location_path && (
                          <p className="text-xs text-slate-600 flex items-center pt-0.5">
                            <span className="font-medium text-slate-500 mr-1.5">Full Path:</span>
                            <span className="text-slate-800">{detailFile.location_path}</span>
                          </p>
                        )}
                      </div>
                    ) : (
                      <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-500 flex items-center justify-between">
                        <span>No physical storage location currently assigned.</span>
                      </div>
                    )}
                  </div>

                  {/* Circulation & Custody Status Box */}
                  <div className="border-t border-slate-200 pt-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-semibold text-slate-600 uppercase tracking-wider">
                        Circulation & Custody State
                      </span>
                      {canEditRecord(detailFile.department) && detailFile.status === "active" && (
                        <div className="flex items-center space-x-2">
                          {detailFile.is_checked_out ? (
                            <button
                              onClick={() => handleOpenCheckin(detailFile)}
                              className="inline-flex items-center px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg shadow-sm"
                            >
                              <LogIn className="w-3.5 h-3.5 mr-1" />
                              Check In
                            </button>
                          ) : (
                            <>
                              <button
                                onClick={() => handleOpenCheckout(detailFile)}
                                className="inline-flex items-center px-2.5 py-1 bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold rounded-lg shadow-sm"
                              >
                                <LogOut className="w-3.5 h-3.5 mr-1" />
                                Check Out
                              </button>
                              <button
                                onClick={() => handleOpenTransfer(detailFile)}
                                className="inline-flex items-center px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg shadow-sm"
                              >
                                <ArrowRightLeft className="w-3.5 h-3.5 mr-1" />
                                Transfer
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </div>

                    {detailFile.is_checked_out ? (
                      <div className={`p-4 rounded-xl border ${
                        detailFile.is_overdue
                          ? "bg-rose-50/80 border-rose-200"
                          : "bg-amber-50/80 border-amber-200"
                      } space-y-2`}>
                        <div className="flex items-center justify-between">
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs font-bold ${
                            detailFile.is_overdue
                              ? "bg-rose-100 text-rose-800"
                              : "bg-amber-100 text-amber-800"
                          }`}>
                            {detailFile.is_overdue ? (
                              <>
                                <AlertTriangle className="w-3.5 h-3.5 mr-1 text-rose-600" />
                                OVERDUE FOR RETURN
                              </>
                            ) : (
                              <>
                                <LogOut className="w-3.5 h-3.5 mr-1 text-amber-600" />
                                CURRENTLY CHECKED OUT
                              </>
                            )}
                          </span>
                        </div>

                        {detailCustodyLoading ? (
                          <div className="py-2 text-xs text-slate-500 flex items-center">
                            <RefreshCw className="w-3 h-3 animate-spin mr-1.5" /> Loading custody record...
                          </div>
                        ) : detailCustody ? (
                          <div className="text-xs space-y-1 text-slate-700">
                            <div>
                              <span className="font-semibold text-slate-900">Current Custodian:</span>{" "}
                              {detailCustody.custodian_name}
                              {detailCustody.custodian_department && ` (${detailCustody.custodian_department})`}
                            </div>
                            {detailCustody.custodian_contact && (
                              <div>
                                <span className="font-semibold text-slate-900">Contact:</span>{" "}
                                {detailCustody.custodian_contact}
                              </div>
                            )}
                            <div>
                              <span className="font-semibold text-slate-900">Checked out at:</span>{" "}
                              {new Date(detailCustody.checked_out_at).toLocaleString()}
                            </div>
                            {detailCustody.expected_return_at && (
                              <div className={detailFile.is_overdue ? "font-bold text-rose-700" : ""}>
                                <span className="font-semibold text-slate-900">Expected return:</span>{" "}
                                {new Date(detailCustody.expected_return_at).toLocaleString()}
                              </div>
                            )}
                            {detailCustody.purpose && (
                              <div className="pt-1 italic text-slate-600">
                                <span className="font-semibold not-italic text-slate-900">Purpose:</span>{" "}
                                {detailCustody.purpose}
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="text-xs text-slate-700">
                            Custodian: <strong>{detailFile.current_custodian_name || "Assigned"}</strong>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-600 flex items-center justify-between">
                        <span className="flex items-center">
                          <LogIn className="w-4 h-4 mr-1.5 text-slate-400" />
                          File is stored in archive location and eligible for check-out or transfer.
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Provenance & Audit Info */}
                  <div className="border-t border-slate-200 pt-4 text-xs text-slate-400 space-y-1">
                    <div>
                      Registered by:{" "}
                      <span className="text-slate-600 font-medium">
                        {detailFile.created_by?.full_name || detailFile.created_by_id}
                      </span>{" "}
                      on {new Date(detailFile.created_at).toLocaleString()}
                    </div>
                    {detailFile.updated_by && (
                      <div>
                        Last modified by:{" "}
                        <span className="text-slate-600 font-medium">
                          {detailFile.updated_by.full_name}
                        </span>{" "}
                        on {new Date(detailFile.updated_at).toLocaleString()}
                      </div>
                    )}
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </div>
      )}

      {/* Edit Metadata Modal */}
      {editFile && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 max-w-lg w-full overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center space-x-2">
                <Edit2 className="w-5 h-5 text-indigo-600" />
                <h3 className="text-base font-bold text-slate-900">
                  Edit Physical File Metadata
                </h3>
              </div>
              <button
                onClick={() => setEditFile(null)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleEditSubmit} className="p-6 space-y-4">
              {editError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                  {editError}
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Title</label>
                <input
                  type="text"
                  required
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Record Type
                  </label>
                  <select
                    value={editRecordType}
                    onChange={(e) => setEditRecordType(e.target.value as PhysicalRecordType)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                  >
                    {RECORD_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Department
                  </label>
                  {user?.role === "admin" || user?.role === "records_officer" ? (
                    <select
                      value={editDepartment}
                      onChange={(e) => setEditDepartment(e.target.value)}
                      className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                    >
                      {DEPARTMENTS.map((d) => (
                        <option key={d} value={d}>
                          {d}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      disabled
                      value={editDepartment}
                      className="w-full px-3 py-2 text-sm border border-slate-200 bg-slate-50 text-slate-500 rounded-lg"
                    />
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Classification
                  </label>
                  <select
                    value={editClassification}
                    onChange={(e) => setEditClassification(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                  >
                    <option value="">None / Unclassified</option>
                    {CLASSIFICATIONS.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    External Reference
                  </label>
                  <input
                    type="text"
                    value={editExtRef}
                    onChange={(e) => setEditExtRef(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>

              {/* Digital Document Association */}
              <div className="border-t border-slate-200 pt-3">
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Linked Digital Document
                </label>
                <select
                  disabled={editUnlinkDigital}
                  value={editDigitalDocId}
                  onChange={(e) => setEditDigitalDocId(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white disabled:bg-slate-50"
                >
                  <option value="">-- No Digital Document (Unlinked) --</option>
                  {availableDocs.length === 0 && (
                    <option disabled value="">Loading digital records...</option>
                  )}
                  {editFile?.digital_document && !availableDocs.some((d) => d.id === editFile.digital_document?.id) && (
                    <option value={editFile.digital_document.id}>
                      {editFile.digital_document.title} ({editFile.digital_document.document_reference})
                    </option>
                  )}
                  {availableDocs.map((doc) => (
                    <option key={doc.id} value={doc.id}>
                      {doc.title} ({doc.document_reference}) - {doc.department}
                    </option>
                  ))}
                </select>
                <label className="flex items-center space-x-2 mt-2 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={editUnlinkDigital}
                    onChange={(e) => {
                      setEditUnlinkDigital(e.target.checked);
                      if (e.target.checked) setEditDigitalDocId("");
                    }}
                    className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span>Unlink existing digital document</span>
                </label>
              </div>

              {/* Storage Location Association */}
              <div className="border-t border-slate-200 pt-3">
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Storage Location
                </label>
                <select
                  disabled={editUnlinkLocation}
                  value={editStorageLocationId}
                  onChange={(e) => setEditStorageLocationId(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white disabled:bg-slate-50"
                >
                  <option value="">-- No Storage Location Assigned --</option>
                  {availableLocations.length === 0 && (
                    <option disabled value="">Loading locations...</option>
                  )}
                  {editFile?.storage_location_id && !availableLocations.some((l) => l.id === editFile.storage_location_id) && (
                    <option value={editFile.storage_location_id}>
                      {editFile.storage_location_name || "Current Location"} ({editFile.storage_location_code || "Code"})
                    </option>
                  )}
                  {availableLocations.map((loc) => (
                    <option key={loc.id} value={loc.id}>
                      {loc.name} ({loc.location_code}) - {loc.department}
                    </option>
                  ))}
                </select>
                <label className="flex items-center space-x-2 mt-2 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={editUnlinkLocation}
                    onChange={(e) => {
                      setEditUnlinkLocation(e.target.checked);
                      if (e.target.checked) setEditStorageLocationId("");
                    }}
                    className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span>Unlink / Remove from current storage location</span>
                </label>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Description
                </label>
                <textarea
                  rows={3}
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setEditFile(null)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editSubmitting}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium shadow-sm disabled:opacity-50"
                >
                  {editSubmitting ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Lifecycle Status Confirmation Modal */}
      {statusConfirmFile && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 max-w-md w-full overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center space-x-2">
                <AlertCircle className="w-5 h-5 text-amber-600" />
                <h3 className="text-base font-bold text-slate-900">
                  Confirm Status Transition
                </h3>
              </div>
              <button
                onClick={() => setStatusConfirmFile(null)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleStatusTransitionSubmit} className="p-6 space-y-4">
              {statusError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                  {statusError}
                </div>
              )}

              <p className="text-sm text-slate-600">
                Are you sure you want to transition{" "}
                <strong className="text-slate-900 font-mono">
                  {statusConfirmFile.file.file_reference}
                </strong>{" "}
                from{" "}
                <span className="capitalize font-semibold text-slate-800">
                  {statusConfirmFile.file.status}
                </span>{" "}
                to{" "}
                <span className="capitalize font-semibold text-amber-700">
                  {statusConfirmFile.targetStatus}
                </span>
                ?
              </p>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Reason / Governance Notes
                </label>
                <textarea
                  rows={2}
                  placeholder="e.g. Relocated to secure historical archive room."
                  value={statusReason}
                  onChange={(e) => setStatusReason(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setStatusConfirmFile(null)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={statusSubmitting}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm font-medium shadow-sm disabled:opacity-50"
                >
                  {statusSubmitting ? "Updating..." : "Confirm Transition"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Assign Storage Location Modal */}
      {assignModalFile && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 max-w-md w-full overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center space-x-2">
                <MapPin className="w-5 h-5 text-blue-600" />
                <h3 className="text-base font-bold text-slate-900">
                  Assign Storage Location
                </h3>
              </div>
              <button
                onClick={() => setAssignModalFile(null)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleAssignLocationSubmit} className="p-6 space-y-4">
              {assignError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                  {assignError}
                </div>
              )}

              <p className="text-sm text-slate-600">
                Assign physical file{" "}
                <strong className="text-slate-900 font-mono">
                  {assignModalFile.file_reference}
                </strong>{" "}
                to an active storage location in department{" "}
                <span className="font-semibold text-slate-800">
                  {assignModalFile.department}
                </span>
                .
              </p>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Target Storage Location
                </label>
                <select
                  value={assignLocationId}
                  onChange={(e) => setAssignLocationId(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  <option value="">-- No Storage Location (Unassign) --</option>
                  {availableLocations.map((loc) => (
                    <option key={loc.id} value={loc.id}>
                      {loc.name} ({loc.location_code}) - {loc.department}
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-slate-400 mt-1">
                  Select an active location to assign. Select the top option to unassign.
                </p>
              </div>

              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setAssignModalFile(null)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={assignSubmitting}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium shadow-sm disabled:opacity-50"
                >
                  {assignSubmitting ? "Assigning..." : "Save Location"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Check Out Modal */}
      {checkoutFile && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 max-w-md w-full overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-amber-50/50">
              <div className="flex items-center space-x-2">
                <LogOut className="w-5 h-5 text-amber-600" />
                <h3 className="text-base font-bold text-slate-900">
                  Check Out Physical File
                </h3>
              </div>
              <button
                onClick={() => setCheckoutFile(null)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCheckoutSubmit} className="p-6 space-y-4">
              {checkoutError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                  {checkoutError}
                </div>
              )}

              <p className="text-sm text-slate-600">
                Check out file <strong className="text-slate-900 font-mono">{checkoutFile.file_reference}</strong> ({checkoutFile.title}) to an authorized custodian.
              </p>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Custodian Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. John Doe, Solicitor Smith"
                  value={checkoutCustodianName}
                  onChange={(e) => setCheckoutCustodianName(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Custodian Department
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Finance, Legal"
                    value={checkoutCustodianDept}
                    onChange={(e) => setCheckoutCustodianDept(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Contact / Extension
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. ext. 4022, email"
                    value={checkoutCustodianContact}
                    onChange={(e) => setCheckoutCustodianContact(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Expected Return Date & Time
                </label>
                <input
                  type="datetime-local"
                  value={checkoutExpectedReturn}
                  onChange={(e) => setCheckoutExpectedReturn(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500"
                />
                <p className="text-[11px] text-slate-400 mt-1">
                  Files past this deadline without return will be flagged as overdue.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Purpose / Checkout Reason
                </label>
                <textarea
                  rows={2}
                  placeholder="Court filing, external audit inspection, board review..."
                  value={checkoutPurpose}
                  onChange={(e) => setCheckoutPurpose(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setCheckoutFile(null)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={checkoutSubmitting}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm font-medium shadow-sm disabled:opacity-50"
                >
                  {checkoutSubmitting ? "Processing..." : "Confirm Check Out"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Check In Modal */}
      {checkinFile && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 max-w-md w-full overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-emerald-50/50">
              <div className="flex items-center space-x-2">
                <LogIn className="w-5 h-5 text-emerald-600" />
                <h3 className="text-base font-bold text-slate-900">
                  Check In Physical File
                </h3>
              </div>
              <button
                onClick={() => setCheckinFile(null)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCheckinSubmit} className="p-6 space-y-4">
              {checkinError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                  {checkinError}
                </div>
              )}

              <p className="text-sm text-slate-600">
                Return file <strong className="text-slate-900 font-mono">{checkinFile.file_reference}</strong> to storage.
              </p>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Destination Storage Location (Optional)
                </label>
                <select
                  value={checkinDestLocationId}
                  onChange={(e) => setCheckinDestLocationId(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-white"
                >
                  <option value="">
                    Defaults to original location ({checkinFile.storage_location_name || "Unassigned"})
                  </option>
                  {availableLocations.map((loc) => (
                    <option key={loc.id} value={loc.id}>
                      {loc.name} ({loc.location_code}) - {loc.department}
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-slate-400 mt-1">
                  Leave default to return to original location: {checkinFile.storage_location_name || "Unassigned"}.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Check-in Notes / Condition
                </label>
                <textarea
                  rows={2}
                  placeholder="Returned in good condition, missing pages noted, etc."
                  value={checkinNotes}
                  onChange={(e) => setCheckinNotes(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setCheckinFile(null)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={checkinSubmitting}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium shadow-sm disabled:opacity-50"
                >
                  {checkinSubmitting ? "Returning..." : "Confirm Check In"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Transfer Location Modal */}
      {transferFile && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 max-w-md w-full overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-indigo-50/50">
              <div className="flex items-center space-x-2">
                <ArrowRightLeft className="w-5 h-5 text-indigo-600" />
                <h3 className="text-base font-bold text-slate-900">
                  Transfer Physical File Location
                </h3>
              </div>
              <button
                onClick={() => setTransferFile(null)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleTransferSubmit} className="p-6 space-y-4">
              {transferError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                  {transferError}
                </div>
              )}

              <p className="text-sm text-slate-600">
                Transfer file <strong className="text-slate-900 font-mono">{transferFile.file_reference}</strong> from current location (
                <span className="font-semibold text-slate-800">
                  {transferFile.storage_location_name || "Unassigned"}
                </span>
                ) to an active storage location.
              </p>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Destination Storage Location <span className="text-red-500">*</span>
                </label>
                {availableLocations.length > 5 && (
                  <div className="relative mb-2">
                    <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                    <input
                      type="text"
                      placeholder="Type to filter locations (e.g. Cabinet, Floor, Room)..."
                      value={transferLocationSearch}
                      onChange={(e) => setTransferLocationSearch(e.target.value)}
                      className="w-full pl-8 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-slate-50"
                    />
                  </div>
                )}
                <select
                  required
                  value={transferDestLocationId}
                  onChange={(e) => setTransferDestLocationId(e.target.value)}
                  className="w-full px-3 py-2.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                >
                  <option value="">-- Select Destination Storage Location --</option>
                  {availableLocations.length === 0 && (
                    <option disabled value="">No storage locations available</option>
                  )}
                  {availableLocations
                    .filter((loc) => {
                      if (!transferLocationSearch.trim()) return true;
                      const q = transferLocationSearch.toLowerCase();
                      return (
                        loc.name.toLowerCase().includes(q) ||
                        loc.location_code.toLowerCase().includes(q) ||
                        (loc.location_type && loc.location_type.toLowerCase().includes(q)) ||
                        (loc.department && loc.department.toLowerCase().includes(q))
                      );
                    })
                    .map((loc) => {
                      const isCurrent = transferFile.storage_location_id === loc.id;
                      return (
                        <option key={loc.id} value={loc.id} disabled={isCurrent}>
                          {loc.name} ({loc.location_code}) • {loc.location_type?.toUpperCase() || "LOCATION"} • {loc.department} {isCurrent ? "— (Current Location)" : ""}
                        </option>
                      );
                    })}
                </select>
                <p className="text-[11px] text-slate-400 mt-1">
                  Destination must be an active storage location within permitted department with capacity.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Reason for Transfer <span className="text-red-500">*</span>
                </label>
                <textarea
                  required
                  rows={2}
                  placeholder="Relocating to permanent archive, shelf consolidation, department transfer..."
                  value={transferReason}
                  onChange={(e) => setTransferReason(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setTransferFile(null)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={transferSubmitting}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium shadow-sm disabled:opacity-50"
                >
                  {transferSubmitting ? "Transferring..." : "Confirm Transfer"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Movement History Modal */}
      {historyFile && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 max-w-2xl w-full max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center space-x-2">
                <History className="w-5 h-5 text-indigo-600" />
                <h3 className="text-base font-bold text-slate-900">
                  Movement History: {historyFile.file_reference}
                </h3>
              </div>
              <button
                onClick={() => setHistoryFile(null)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6">
              {historyLoading ? (
                <div className="py-12 text-center space-y-2">
                  <RefreshCw className="w-8 h-8 text-indigo-600 animate-spin mx-auto" />
                  <p className="text-xs text-slate-500">Loading movement timeline...</p>
                </div>
              ) : historyError ? (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                  {historyError}
                </div>
              ) : historyItems.length === 0 ? (
                <div className="py-12 text-center text-xs text-slate-500">
                  No movement or circulation history recorded yet.
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="relative border-l-2 border-slate-200 ml-4 space-y-6">
                    {historyItems.map((m) => (
                      <div key={m.id} className="relative pl-6">
                        <span className={`absolute -left-2 top-0.5 w-4 h-4 rounded-full border-2 border-white ${
                          m.movement_type === "checkout"
                            ? "bg-amber-500"
                            : m.movement_type === "checkin"
                            ? "bg-emerald-500"
                            : m.movement_type === "transfer"
                            ? "bg-indigo-500"
                            : "bg-blue-500"
                        }`} />
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold uppercase tracking-wider text-slate-800">
                            {m.movement_type.replace("_", " ")}
                          </span>
                          <span className="text-[11px] text-slate-400">
                            {new Date(m.event_at).toLocaleString()}
                          </span>
                        </div>
                        <div className="text-xs text-slate-600 mt-1">
                          {m.source_location_code && (
                            <span>From: <strong>{m.source_location_name || m.source_location_code}</strong></span>
                          )}
                          {m.source_location_code && m.destination_location_code && <span> → </span>}
                          {m.destination_location_code && (
                            <span>To: <strong>{m.destination_location_name || m.destination_location_code}</strong></span>
                          )}
                        </div>
                        {m.reason && (
                          <p className="text-xs text-slate-500 italic mt-0.5">
                            Reason / Notes: {m.reason}
                          </p>
                        )}
                        <div className="text-[11px] text-slate-400 mt-1">
                          Recorded by: {m.actor?.full_name || m.actor_id}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Barcode & QR Code Identification / Camera Scanner Modal */}
      {showScanModal && (
        <ScanLookupModal
          onClose={() => setShowScanModal(false)}
          onFileFound={(found) => {
            handleOpenDetail(found.id);
          }}
        />
      )}

      {/* Label Print Modal (Standard Badge / Code 128 / QR Code) */}
      {printLabelFile && (
        <PrintLabelModal
          file={printLabelFile}
          onClose={() => setPrintLabelFile(null)}
        />
      )}
    </div>
  );
}
