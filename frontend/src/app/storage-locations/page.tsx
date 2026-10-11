"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { api, ApiError } from "@/lib/api";
import {
  StorageLocationSummary,
  StorageLocationDetail,
  LocationType,
  CreateStorageLocationPayload,
  UpdateStorageLocationPayload,
} from "@/types/storage_location";
import { PhysicalFileSummary } from "@/types/physical_file";
import {
  Boxes,
  Plus,
  Search,
  RefreshCw,
  FolderTree,
  Building2,
  ChevronRight,
  ChevronDown,
  Layers,
  Archive,
  CheckCircle2,
  AlertCircle,
  Eye,
  Edit2,
  X,
  FileText,
  Shield,
  Move,
  Power,
  ChevronLeft,
} from "lucide-react";

const LOCATION_TYPES: { value: LocationType; label: string }[] = [
  { value: "building", label: "Building" },
  { value: "floor", label: "Floor" },
  { value: "room", label: "Room / Vault" },
  { value: "cabinet", label: "Cabinet" },
  { value: "shelf", label: "Shelf" },
  { value: "bay", label: "Bay" },
  { value: "box", label: "Storage Box" },
  { value: "other", label: "Other" },
];

const DEPARTMENTS = [
  "Records Management",
  "General / Facilities",
  "Enterprise Shared",
  "Finance",
  "Human Resources",
  "Legal",
  "Operations",
  "Executive",
  "IT",
];

interface SearchableLocationPickerProps {
  value: string;
  onChange: (id: string) => void;
  options: StorageLocationSummary[];
  excludeId?: string;
  placeholder?: string;
  disabled?: boolean;
}

function SearchableLocationPicker({
  value,
  onChange,
  options,
  excludeId,
  placeholder = "Select parent location (optional)...",
  disabled = false,
}: SearchableLocationPickerProps) {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const dropdownRef = React.useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  const filteredOptions = options.filter((loc) => {
    if (excludeId && loc.id === excludeId) return false;
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase().trim();
    return (
      loc.location_code.toLowerCase().includes(q) ||
      loc.name.toLowerCase().includes(q) ||
      loc.location_type.toLowerCase().includes(q) ||
      (loc.location_path && loc.location_path.toLowerCase().includes(q))
    );
  });

  const selectedLoc = options.find((loc) => loc.id === value);

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => {
          if (!disabled) {
            setIsOpen(!isOpen);
            setSearchQuery("");
          }
        }}
        className={`w-full px-3 py-2 text-sm border rounded-lg flex items-center justify-between text-left transition-colors ${
          disabled
            ? "bg-slate-50 border-slate-200 text-slate-400 cursor-not-allowed"
            : isOpen
            ? "border-blue-500 ring-2 ring-blue-100 bg-white"
            : "border-slate-300 bg-white hover:border-slate-400 text-slate-800"
        }`}
      >
        <div className="flex items-center space-x-2 truncate">
          {selectedLoc ? (
            <>
              <span className="font-mono text-xs font-bold text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded border border-blue-200">
                {selectedLoc.location_code}
              </span>
              <span className="font-medium text-slate-900 truncate">{selectedLoc.name}</span>
              <span className="text-xs text-slate-400 capitalize">({selectedLoc.location_type})</span>
            </>
          ) : (
            <span className="text-slate-500 italic">None (Top-Level / Root Location)</span>
          )}
        </div>
        <div className="flex items-center space-x-1.5 flex-shrink-0 ml-2">
          {selectedLoc && !disabled && (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation();
                onChange("");
              }}
              className="p-1 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded cursor-pointer"
              title="Clear selection"
            >
              <X className="w-3.5 h-3.5" />
            </span>
          )}
          <ChevronDown
            className={`w-4 h-4 text-slate-400 transition-transform ${
              isOpen ? "rotate-180 text-blue-600" : ""
            }`}
          />
        </div>
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute z-50 mt-1 w-full bg-white rounded-xl shadow-2xl border border-slate-200 overflow-hidden max-h-72 flex flex-col">
          {/* Integrated Search Bar */}
          <div className="p-2 border-b border-slate-200 bg-slate-50 flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
              <input
                type="text"
                autoFocus
                placeholder="Search locations by code, name, or type..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 text-xs border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white text-slate-800"
              />
            </div>
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="p-1 text-slate-400 hover:text-slate-600 text-xs"
              >
                Clear
              </button>
            )}
          </div>

          {/* Options List */}
          <div className="overflow-y-auto divide-y divide-slate-100 text-xs flex-1">
            {/* Top-Level Option */}
            <button
              type="button"
              onClick={() => {
                onChange("");
                setIsOpen(false);
              }}
              className={`w-full px-3 py-2.5 text-left flex items-center justify-between hover:bg-slate-50 transition-colors ${
                !value ? "bg-blue-50/70 text-blue-900 font-semibold" : "text-slate-700"
              }`}
            >
              <div className="flex items-center space-x-2">
                <FolderTree className="w-4 h-4 text-slate-400" />
                <div>
                  <div className="font-semibold text-slate-800">None (Top-Level / Root Location)</div>
                  <div className="text-[10px] text-slate-400">Standalone building, facility, or root archive</div>
                </div>
              </div>
              {!value && <CheckCircle2 className="w-4 h-4 text-blue-600 flex-shrink-0" />}
            </button>

            {filteredOptions.length === 0 ? (
              <div className="p-4 text-center text-slate-400 text-xs">
                {options.length === 0
                  ? "No locations exist yet. This will be created as a top-level location."
                  : "No matching locations found for your search."}
              </div>
            ) : (
              filteredOptions.map((loc) => {
                const isItemActive = loc.id === value;
                return (
                  <button
                    key={loc.id}
                    type="button"
                    onClick={() => {
                      onChange(loc.id);
                      setIsOpen(false);
                    }}
                    className={`w-full px-3 py-2.5 text-left flex items-center justify-between hover:bg-blue-50/50 transition-colors ${
                      isItemActive ? "bg-blue-50/80 font-semibold text-blue-900" : "text-slate-800"
                    }`}
                  >
                    <div className="flex flex-col truncate pr-2">
                      <div className="flex items-center space-x-2 truncate">
                        <span className="font-mono text-[11px] font-bold text-blue-700 bg-blue-100/70 px-1.5 py-0.5 rounded">
                          {loc.location_code}
                        </span>
                        <span className="text-slate-900 font-medium truncate">{loc.name}</span>
                        <span className="text-[10px] text-slate-500 capitalize bg-slate-100 px-1.5 py-0.5 rounded">
                          {loc.location_type}
                        </span>
                      </div>
                      {loc.location_path && loc.location_path !== loc.name && (
                        <span className="text-[10px] text-slate-400 truncate mt-0.5 pl-0.5">
                          {loc.location_path}
                        </span>
                      )}
                    </div>
                    {isItemActive && (
                      <CheckCircle2 className="w-4 h-4 text-blue-600 flex-shrink-0 ml-2" />
                    )}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function StorageLocationsPage() {
  const { user } = useAuth();

  // Locations state
  const [locations, setLocations] = useState<StorageLocationSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [totalCount, setTotalCount] = useState<number>(0);

  // Filters state
  const [search, setSearch] = useState<string>("");
  const [selectedDept, setSelectedDept] = useState<string>("");
  const [selectedType, setSelectedType] = useState<string>("");
  const [activeFilter, setActiveFilter] = useState<string>("");

  // Modals & Drawers
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null);
  const [detailLocation, setDetailLocation] = useState<StorageLocationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Contents of selected location
  const [locationContents, setLocationContents] = useState<PhysicalFileSummary[]>([]);
  const [contentsLoading, setContentsLoading] = useState<boolean>(false);
  const [contentsPage, setContentsPage] = useState<number>(1);
  const [contentsTotal, setContentsTotal] = useState<number>(0);

  // Edit State
  const [editLocation, setEditLocation] = useState<StorageLocationDetail | null>(null);
  const [editName, setEditName] = useState<string>("");
  const [editDescription, setEditDescription] = useState<string>("");
  const [editType, setEditType] = useState<LocationType>("room");
  const [editParentId, setEditParentId] = useState<string>("");
  const [editClearParent, setEditClearParent] = useState<boolean>(false);
  const [editMaxCapacity, setEditMaxCapacity] = useState<string>("");
  const [editClearCapacity, setEditClearCapacity] = useState<boolean>(false);
  const [editDepartment, setEditDepartment] = useState<string>("");
  const [editSubmitting, setEditSubmitting] = useState<boolean>(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Status Change State
  const [statusConfirmLoc, setStatusConfirmLoc] = useState<StorageLocationDetail | null>(null);
  const [statusReason, setStatusReason] = useState<string>("");
  const [statusSubmitting, setStatusSubmitting] = useState<boolean>(false);
  const [statusError, setStatusError] = useState<string | null>(null);

  // Create Form State
  const [createCode, setCreateCode] = useState<string>("");
  const [createName, setCreateName] = useState<string>("");
  const [createType, setCreateType] = useState<LocationType>("room");
  const [createDescription, setCreateDescription] = useState<string>("");
  const [createDepartment, setCreateDepartment] = useState<string>("");
  const [createParentId, setCreateParentId] = useState<string>("");
  const [createMaxCapacity, setCreateMaxCapacity] = useState<string>("");
  const [createSubmitting, setCreateSubmitting] = useState<boolean>(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccessMsg, setCreateSuccessMsg] = useState<string | null>(null);

  // Default department
  useEffect(() => {
    if (user) {
      if (user.role === "department_user") {
        setCreateDepartment(user.department || "");
      } else {
        setCreateDepartment(user.department || "Records Management");
      }
    }
  }, [user]);

  // All active locations for Parent Location Picker
  const [parentCandidates, setParentCandidates] = useState<StorageLocationSummary[]>([]);

  const fetchParentCandidates = useCallback(async () => {
    try {
      const res = await api.getStorageLocations({
        page: 1,
        page_size: 100,
        is_active: true,
      });
      setParentCandidates(res.items);
    } catch (err) {
      console.error("Failed to load parent candidates:", err);
    }
  }, []);

  useEffect(() => {
    if (showCreateModal || editLocation) {
      fetchParentCandidates();
    }
  }, [showCreateModal, editLocation, fetchParentCandidates]);

  // Fetch Storage Locations
  const fetchLocations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getStorageLocations({
        page,
        page_size: 25,
        search: search.trim() || undefined,
        department: selectedDept || undefined,
        location_type: selectedType || undefined,
        is_active: activeFilter === "true" ? true : activeFilter === "false" ? false : undefined,
      });
      setLocations(res.items);
      setTotalPages(res.total_pages);
      setTotalCount(res.total);
      if (res.items && res.items.length > 0) {
        setParentCandidates((prev) => (prev.length === 0 ? res.items : prev));
      }
    } catch (err: any) {
      setError(err.message || "Failed to load storage locations.");
    } finally {
      setLoading(false);
    }
  }, [page, search, selectedDept, selectedType, activeFilter, fetchParentCandidates]);

  useEffect(() => {
    fetchLocations();
  }, [fetchLocations]);

  // Fetch Location Details & Direct Contents
  const handleSelectLocation = async (id: string) => {
    setSelectedLocationId(id);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const [detailData, contentsData] = await Promise.all([
        api.getStorageLocation(id),
        api.getStorageLocationContents(id, { page: 1, page_size: 15 }),
      ]);
      setDetailLocation(detailData);
      setLocationContents(contentsData.items);
      setContentsTotal(contentsData.total);
      setContentsPage(1);
    } catch (err: any) {
      setDetailError(err.message || "Failed to load location details.");
    } finally {
      setDetailLoading(false);
    }
  };

  // Open Edit Modal
  const handleOpenEdit = (loc: StorageLocationDetail) => {
    setEditLocation(loc);
    setEditName(loc.name);
    setEditDescription(loc.description || "");
    setEditType(loc.location_type);
    setEditParentId(loc.parent_id || "");
    setEditClearParent(false);
    setEditMaxCapacity(loc.max_capacity !== null && loc.max_capacity !== undefined ? String(loc.max_capacity) : "");
    setEditClearCapacity(false);
    setEditDepartment(loc.department);
    setEditError(null);
  };

  // Create Storage Location Submit
  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createCode.trim() || !createName.trim() || !createDepartment.trim()) {
      setCreateError("Code, name, and department are required.");
      return;
    }

    setCreateSubmitting(true);
    setCreateError(null);
    setCreateSuccessMsg(null);

    try {
      const payload: CreateStorageLocationPayload = {
        location_code: createCode.trim().toUpperCase(),
        name: createName.trim(),
        location_type: createType,
        description: createDescription.trim() || null,
        department: createDepartment.trim(),
        parent_id: createParentId.trim() || null,
        max_capacity: createMaxCapacity.trim() ? parseInt(createMaxCapacity.trim(), 10) : null,
      };

      const created = await api.createStorageLocation(payload);
      setCreateSuccessMsg(`Created location ${created.location_code}`);
      setTimeout(() => {
        setShowCreateModal(false);
        setCreateSuccessMsg(null);
        setCreateCode("");
        setCreateName("");
        setCreateDescription("");
        setCreateParentId("");
        setCreateMaxCapacity("");
        fetchLocations();
      }, 1000);
    } catch (err: any) {
      setCreateError(err.message || "Failed to create storage location.");
    } finally {
      setCreateSubmitting(false);
    }
  };

  // Edit Storage Location Submit
  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editLocation) return;

    setEditSubmitting(true);
    setEditError(null);

    try {
      const payload: UpdateStorageLocationPayload = {
        name: editName.trim() || null,
        description: editDescription.trim() || null,
        location_type: editType,
        clear_parent: editClearParent,
        parent_id: !editClearParent && editParentId.trim() ? editParentId.trim() : undefined,
        clear_max_capacity: editClearCapacity,
        max_capacity:
          !editClearCapacity && editMaxCapacity.trim()
            ? parseInt(editMaxCapacity.trim(), 10)
            : undefined,
        department:
          user?.role === "admin" || user?.role === "records_officer"
            ? editDepartment.trim() || null
            : undefined,
      };

      const updated = await api.updateStorageLocation(editLocation.id, payload);
      setEditLocation(null);
      if (selectedLocationId === updated.id) {
        setDetailLocation(updated);
      }
      fetchLocations();
    } catch (err: any) {
      setEditError(err.message || "Failed to update storage location.");
    } finally {
      setEditSubmitting(false);
    }
  };

  // Status Change Submit
  const handleStatusSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!statusConfirmLoc) return;

    setStatusSubmitting(true);
    setStatusError(null);

    try {
      const targetState = !statusConfirmLoc.is_active;
      const updated = await api.changeStorageLocationStatus(statusConfirmLoc.id, {
        is_active: targetState,
        reason: statusReason.trim() || undefined,
      });

      setStatusConfirmLoc(null);
      setStatusReason("");
      if (selectedLocationId === updated.id) {
        setDetailLocation(updated);
      }
      fetchLocations();
    } catch (err: any) {
      setStatusError(err.message || "Failed to change status.");
    } finally {
      setStatusSubmitting(false);
    }
  };

  const canManage =
    user?.role === "admin" ||
    user?.role === "records_officer" ||
    user?.role === "department_user";

  const canEditLoc = (locDept: string) => {
    if (!user) return false;
    if (user.role === "admin" || user.role === "records_officer") return true;
    if (user.role === "department_user") {
      return (user.department || "").toLowerCase() === locDept.toLowerCase();
    }
    return false;
  };

  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4 sm:px-6 lg:px-8 w-full">
      <div className="w-full space-y-6">
        {/* Page Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-200 pb-5">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-blue-600 text-white rounded-xl shadow-sm">
              <Boxes className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                Storage Locations
              </h1>
              <p className="text-sm text-slate-500">
                Organize facilities, archives, rooms, cabinets, shelves, and storage containers.
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={() => fetchLocations()}
              className="inline-flex items-center px-3.5 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 shadow-sm"
            >
              <RefreshCw className="w-4 h-4 mr-2 text-slate-500" />
              Refresh
            </button>

            {canManage && (
              <button
                onClick={() => setShowCreateModal(true)}
                className="inline-flex items-center px-4 py-2 border border-transparent rounded-lg text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 shadow-sm"
              >
                <Plus className="w-4 h-4 mr-2" />
                New Storage Location
              </button>
            )}
          </div>
        </div>

        {/* Filters Bar */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
            <input
              type="text"
              placeholder="Search code or location name..."
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
                className="px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white text-slate-700"
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
              value={selectedType}
              onChange={(e) => {
                setSelectedType(e.target.value);
                setPage(1);
              }}
              className="px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white text-slate-700"
            >
              <option value="">All Types</option>
              {LOCATION_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>

            <select
              value={activeFilter}
              onChange={(e) => {
                setActiveFilter(e.target.value);
                setPage(1);
              }}
              className="px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white text-slate-700"
            >
              <option value="">All Statuses</option>
              <option value="true">Active Only</option>
              <option value="false">Inactive Only</option>
            </select>
          </div>
        </div>

        {/* Master-Detail Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Table / List (7 cols) */}
          <div className="lg:col-span-7 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            {loading ? (
              <div className="py-16 text-center space-y-3">
                <RefreshCw className="w-8 h-8 text-blue-600 animate-spin mx-auto" />
                <p className="text-sm text-slate-500">Loading storage locations...</p>
              </div>
            ) : error ? (
              <div className="py-12 text-center px-4">
                <AlertCircle className="w-10 h-10 text-red-500 mx-auto mb-2" />
                <p className="text-sm font-semibold text-slate-800">Failed to load locations</p>
                <p className="text-xs text-red-600 mt-1">{error}</p>
              </div>
            ) : locations.length === 0 ? (
              <div className="py-16 text-center px-4 space-y-3">
                <Boxes className="w-12 h-12 text-slate-300 mx-auto" />
                <h3 className="text-base font-semibold text-slate-800">No storage locations found</h3>
                <p className="text-sm text-slate-500 max-w-sm mx-auto">
                  Create buildings, rooms, cabinets, or storage boxes to organize records.
                </p>
                {canManage && (
                  <button
                    onClick={() => setShowCreateModal(true)}
                    className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700"
                  >
                    <Plus className="w-4 h-4 mr-2" />
                    Create First Location
                  </button>
                )}
              </div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-slate-200">
                    <thead className="bg-slate-50">
                      <tr>
                        <th className="px-5 py-3 text-left text-xs font-semibold text-slate-600 uppercase">
                          Location Code
                        </th>
                        <th className="px-5 py-3 text-left text-xs font-semibold text-slate-600 uppercase">
                          Name & Type
                        </th>
                        <th className="px-5 py-3 text-left text-xs font-semibold text-slate-600 uppercase">
                          Department
                        </th>
                        <th className="px-5 py-3 text-left text-xs font-semibold text-slate-600 uppercase">
                          Files
                        </th>
                        <th className="px-5 py-3 text-left text-xs font-semibold text-slate-600 uppercase">
                          Status
                        </th>
                        <th className="px-5 py-3 text-right text-xs font-semibold text-slate-600 uppercase">
                          Select
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-slate-200 text-sm">
                      {locations.map((loc) => {
                        const isSelected = selectedLocationId === loc.id;
                        return (
                          <tr
                            key={loc.id}
                            onClick={() => handleSelectLocation(loc.id)}
                            className={`cursor-pointer transition-colors ${
                              isSelected ? "bg-blue-50/70" : "hover:bg-slate-50/75"
                            }`}
                          >
                            <td className="px-5 py-3 whitespace-nowrap">
                              <span className="font-mono text-xs font-bold text-blue-700 bg-blue-100/60 px-2 py-0.5 rounded">
                                {loc.location_code}
                              </span>
                            </td>
                            <td className="px-5 py-3">
                              <div className="font-semibold text-slate-900">{loc.name}</div>
                              <div className="text-xs text-slate-500 capitalize">
                                {loc.location_type}
                                {loc.location_path && loc.location_path !== loc.name && (
                                  <span className="ml-1 text-slate-400 truncate block max-w-xs">
                                    {loc.location_path}
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="px-5 py-3 whitespace-nowrap text-slate-600 text-xs">
                              {loc.department}
                            </td>
                            <td className="px-5 py-3 whitespace-nowrap text-xs text-slate-700">
                              <span className="font-semibold">{loc.direct_file_count}</span>
                              {loc.max_capacity !== null && (
                                <span className="text-slate-400"> / {loc.max_capacity}</span>
                              )}
                            </td>
                            <td className="px-5 py-3 whitespace-nowrap">
                              <span
                                className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                                  loc.is_active
                                    ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                    : "bg-slate-100 text-slate-600 border border-slate-200"
                                }`}
                              >
                                {loc.is_active ? "Active" : "Inactive"}
                              </span>
                            </td>
                            <td className="px-5 py-3 whitespace-nowrap text-right">
                              <ChevronRight className="w-4 h-4 text-slate-400 inline" />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="px-5 py-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-600">
                  <div>
                    {locations.length} of {totalCount} locations
                  </div>
                  <div className="flex items-center space-x-2">
                    <button
                      disabled={page <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      className="p-1 border border-slate-300 rounded hover:bg-white disabled:opacity-40"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </button>
                    <span>
                      Page {page} of {totalPages}
                    </span>
                    <button
                      disabled={page >= totalPages}
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                      className="p-1 border border-slate-300 rounded hover:bg-white disabled:opacity-40"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Right Detail & Direct Contents Drawer (5 cols) */}
          <div className="lg:col-span-5 bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-6">
            {detailLoading ? (
              <div className="py-20 text-center space-y-2">
                <RefreshCw className="w-7 h-7 text-blue-600 animate-spin mx-auto" />
                <p className="text-xs text-slate-500">Loading location metadata...</p>
              </div>
            ) : detailError ? (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                {detailError}
              </div>
            ) : detailLocation ? (
              <>
                {/* Header Details */}
                <div className="border-b border-slate-200 pb-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded">
                      {detailLocation.location_code}
                    </span>
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                        detailLocation.is_active
                          ? "bg-emerald-50 text-emerald-700"
                          : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {detailLocation.is_active ? "Active" : "Inactive"}
                    </span>
                  </div>

                  <h2 className="text-xl font-bold text-slate-900">{detailLocation.name}</h2>
                  <p className="text-xs text-slate-500 capitalize">
                    Type: <span className="font-semibold text-slate-700">{detailLocation.location_type}</span> • Dept:{" "}
                    <span className="font-semibold text-slate-700">{detailLocation.department}</span>
                  </p>

                  {/* Hierarchical Breadcrumb */}
                  {detailLocation.breadcrumbs.length > 0 && (
                    <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-200 text-xs text-slate-600">
                      <span className="font-semibold text-slate-500 block mb-1">Hierarchy Path:</span>
                      <div className="flex flex-wrap items-center gap-1 font-medium text-slate-800">
                        {detailLocation.breadcrumbs.map((crumb, idx) => (
                          <React.Fragment key={crumb.id}>
                            <span className={idx === detailLocation.breadcrumbs.length - 1 ? "font-bold text-blue-600" : ""}>
                              {crumb.name}
                            </span>
                            {idx < detailLocation.breadcrumbs.length - 1 && (
                              <ChevronRight className="w-3 h-3 text-slate-400" />
                            )}
                          </React.Fragment>
                        ))}
                      </div>
                    </div>
                  )}

                  {detailLocation.description && (
                    <p className="text-xs text-slate-600 italic mt-1">
                      {detailLocation.description}
                    </p>
                  )}
                </div>

                {/* Capacity & Counts Indicator */}
                <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 rounded-xl border border-slate-200 text-center">
                  <div>
                    <span className="text-[11px] text-slate-500 uppercase font-semibold block">
                      Direct Files
                    </span>
                    <span className="text-lg font-bold text-slate-900">
                      {detailLocation.direct_file_count}
                    </span>
                    {detailLocation.max_capacity && (
                      <span className="text-xs text-slate-400 block">
                        of {detailLocation.max_capacity} max
                      </span>
                    )}
                  </div>
                  <div>
                    <span className="text-[11px] text-slate-500 uppercase font-semibold block">
                      Child Locations
                    </span>
                    <span className="text-lg font-bold text-slate-900">
                      {detailLocation.child_count}
                    </span>
                  </div>
                </div>

                {/* Action Buttons */}
                {canEditLoc(detailLocation.department) && (
                  <div className="flex items-center space-x-2 pt-1 border-b border-slate-200 pb-4">
                    <button
                      onClick={() => handleOpenEdit(detailLocation)}
                      className="flex-1 px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-sm"
                    >
                      <Edit2 className="w-3.5 h-3.5 mr-1.5 inline" />
                      Edit Metadata
                    </button>

                    <button
                      onClick={() => setStatusConfirmLoc(detailLocation)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold shadow-sm ${
                        detailLocation.is_active
                          ? "bg-amber-600 hover:bg-amber-700 text-white"
                          : "bg-emerald-600 hover:bg-emerald-700 text-white"
                      }`}
                    >
                      <Power className="w-3.5 h-3.5 mr-1.5 inline" />
                      {detailLocation.is_active ? "Deactivate" : "Activate"}
                    </button>
                  </div>
                )}

                {/* Direct Physical Files List */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                      Files at this location ({contentsTotal})
                    </h3>
                  </div>

                  {locationContents.length === 0 ? (
                    <div className="py-6 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-lg">
                      No physical files are directly stored in this location.
                    </div>
                  ) : (
                    <div className="divide-y divide-slate-100 max-h-64 overflow-y-auto border border-slate-200 rounded-lg">
                      {locationContents.map((f) => (
                        <div key={f.id} className="p-3 hover:bg-slate-50 flex items-center justify-between text-xs">
                          <div>
                            <span className="font-mono font-semibold text-blue-600">
                              {f.file_reference}
                            </span>
                            <p className="font-semibold text-slate-800 line-clamp-1">{f.title}</p>
                            <span className="text-[10px] text-slate-400 capitalize">
                              {f.record_type.replace("_", " ")}
                            </span>
                          </div>
                          <a
                            href={`/physical-files`}
                            className="text-blue-600 hover:underline text-[11px] font-medium"
                          >
                            View
                          </a>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="py-20 text-center space-y-3">
                <FolderTree className="w-10 h-10 text-slate-300 mx-auto" />
                <p className="text-sm font-semibold text-slate-700">No Location Selected</p>
                <p className="text-xs text-slate-400 max-w-xs mx-auto">
                  Select a storage location from the registry table on the left to inspect its details, hierarchy path, and stored files.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Create Location Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 max-w-lg w-full overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center space-x-2">
                <Boxes className="w-5 h-5 text-blue-600" />
                <h3 className="text-base font-bold text-slate-900">New Storage Location</h3>
              </div>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="p-6 space-y-4">
              {createError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                  {createError}
                </div>
              )}
              {createSuccessMsg && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-700">
                  {createSuccessMsg}
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Location Code <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. CAB-FIN-01"
                    value={createCode}
                    onChange={(e) => setCreateCode(e.target.value.toUpperCase())}
                    className="w-full px-3 py-2 text-sm font-mono border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 uppercase"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Location Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Finance Vault Cabinet A"
                    value={createName}
                    onChange={(e) => setCreateName(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Location Type <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={createType}
                    onChange={(e) => setCreateType(e.target.value as LocationType)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white"
                  >
                    {LOCATION_TYPES.map((t) => (
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
                      value={createDepartment}
                      className="w-full px-3 py-2 text-sm border border-slate-200 bg-slate-50 text-slate-500 rounded-lg"
                    />
                  ) : (
                    <select
                      value={createDepartment}
                      onChange={(e) => setCreateDepartment(e.target.value)}
                      className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white"
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
                    Parent Location
                  </label>
                  <SearchableLocationPicker
                    value={createParentId}
                    onChange={(id) => setCreateParentId(id)}
                    options={parentCandidates}
                    placeholder="Select containing location (optional)..."
                  />
                  <p className="text-[10px] text-slate-400 mt-1">
                    Select containing building, room, cabinet, or leave as root.
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Max Capacity (Files)
                  </label>
                  <input
                    type="number"
                    min="1"
                    placeholder="Optional max items limit"
                    value={createMaxCapacity}
                    onChange={(e) => setCreateMaxCapacity(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Description / Facility Notes
                </label>
                <textarea
                  rows={3}
                  placeholder="Security access codes, room location notes, keys custodian..."
                  value={createDescription}
                  onChange={(e) => setCreateDescription(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createSubmitting}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium shadow-sm disabled:opacity-50"
                >
                  {createSubmitting ? "Creating..." : "Create Location"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editLocation && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 max-w-lg w-full overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center space-x-2">
                <Edit2 className="w-5 h-5 text-indigo-600" />
                <h3 className="text-base font-bold text-slate-900">
                  Edit Location: {editLocation.location_code}
                </h3>
              </div>
              <button
                onClick={() => setEditLocation(null)}
                className="text-slate-400 hover:text-slate-600 p-1"
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
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Location Name
                </label>
                <input
                  type="text"
                  required
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Location Type
                  </label>
                  <select
                    value={editType}
                    onChange={(e) => setEditType(e.target.value as LocationType)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white"
                  >
                    {LOCATION_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Max Capacity
                  </label>
                  <input
                    type="number"
                    min="1"
                    disabled={editClearCapacity}
                    placeholder="Direct files limit"
                    value={editMaxCapacity}
                    onChange={(e) => setEditMaxCapacity(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
                  />
                  <label className="flex items-center space-x-2 mt-1 text-xs text-slate-500">
                    <input
                      type="checkbox"
                      checked={editClearCapacity}
                      onChange={(e) => setEditClearCapacity(e.target.checked)}
                      className="rounded border-slate-300 text-indigo-600"
                    />
                    <span>Remove capacity limit</span>
                  </label>
                </div>
              </div>

              {/* Hierarchy Parent Reassignment */}
              <div className="border-t border-slate-200 pt-3">
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Parent Location
                </label>
                <SearchableLocationPicker
                  value={editClearParent ? "" : editParentId}
                  onChange={(id) => {
                    if (!id) {
                      setEditParentId("");
                      setEditClearParent(true);
                    } else {
                      setEditParentId(id);
                      setEditClearParent(false);
                    }
                  }}
                  options={parentCandidates}
                  excludeId={editLocation.id}
                  disabled={editClearParent}
                  placeholder="Select containing location..."
                />
                <label className="flex items-center space-x-2 mt-2 text-xs text-slate-500">
                  <input
                    type="checkbox"
                    checked={editClearParent}
                    onChange={(e) => {
                      setEditClearParent(e.target.checked);
                      if (e.target.checked) {
                        setEditParentId("");
                      }
                    }}
                    className="rounded border-slate-300 text-indigo-600"
                  />
                  <span>Promote to top-level (remove parent)</span>
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
                  onClick={() => setEditLocation(null)}
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

      {/* Status Transition Confirmation Modal */}
      {statusConfirmLoc && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 max-w-md w-full overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center space-x-2">
                <AlertCircle className="w-5 h-5 text-amber-600" />
                <h3 className="text-base font-bold text-slate-900">
                  Confirm Status Change
                </h3>
              </div>
              <button
                onClick={() => setStatusConfirmLoc(null)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleStatusSubmit} className="p-6 space-y-4">
              {statusError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                  {statusError}
                </div>
              )}

              <p className="text-sm text-slate-600">
                Are you sure you want to{" "}
                <strong className={statusConfirmLoc.is_active ? "text-amber-700" : "text-emerald-700"}>
                  {statusConfirmLoc.is_active ? "deactivate" : "activate"}
                </strong>{" "}
                storage location{" "}
                <span className="font-mono font-bold text-slate-900">
                  {statusConfirmLoc.location_code} ({statusConfirmLoc.name})
                </span>
                ?
              </p>

              {statusConfirmLoc.is_active && (
                <p className="text-xs text-slate-500 bg-amber-50 p-2.5 rounded-lg border border-amber-200">
                  Note: Locations holding files or active child nodes cannot be deactivated.
                </p>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Reason / Notes
                </label>
                <textarea
                  rows={2}
                  placeholder="Justification for activation or deactivation..."
                  value={statusReason}
                  onChange={(e) => setStatusReason(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setStatusConfirmLoc(null)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={statusSubmitting}
                  className={`px-4 py-2 rounded-lg text-sm font-medium text-white shadow-sm disabled:opacity-50 ${
                    statusConfirmLoc.is_active
                      ? "bg-amber-600 hover:bg-amber-700"
                      : "bg-emerald-600 hover:bg-emerald-700"
                  }`}
                >
                  {statusSubmitting ? "Updating..." : "Confirm"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
