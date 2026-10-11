"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { api, ApiError } from "@/lib/api";
import { AdminUser, UserRole, CreateUserPayload, UpdateUserPayload } from "@/types/user";
import {
  Users,
  UserPlus,
  Search,
  Filter,
  Shield,
  Building,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Edit2,
  Power,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  X,
  Lock,
} from "lucide-react";

const AVAILABLE_ROLES: { value: UserRole; label: string; description: string; requiresDept: boolean }[] = [
  { value: "admin", label: "Administrator", description: "Full system administration and user management", requiresDept: false },
  { value: "records_officer", label: "Records Officer", description: "Cross-department records management and retention", requiresDept: false },
  { value: "department_user", label: "Department User", description: "Standard contributor scoped to assigned department", requiresDept: true },
  { value: "approver", label: "Approver", description: "Review and approve/reject workflows in assigned department", requiresDept: true },
  { value: "auditor", label: "Auditor", description: "Read-only compliance auditing for assigned department", requiresDept: true },
  { value: "read_only", label: "Read-Only User", description: "View-only access for public departmental documents", requiresDept: true },
];

export default function AdminUsersPage() {
  const { user: currentUser, loading: authLoading } = useAuth();

  // Listing state
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [page, setPage] = useState<number>(1);
  const [pageSize] = useState<number>(10);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  // Filters
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [roleFilter, setRoleFilter] = useState<string>("");
  const [deptFilter, setDeptFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");

  // Modals state
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [statusConfirmUser, setStatusConfirmUser] = useState<AdminUser | null>(null);

  // Form states
  const [createForm, setCreateForm] = useState<CreateUserPayload>({
    full_name: "",
    email: "",
    role: "department_user",
    department: "",
    password: "",
  });
  const [createSubmitting, setCreateSubmitting] = useState<boolean>(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [editForm, setEditForm] = useState<UpdateUserPayload>({
    full_name: "",
    department: "",
    role: "department_user",
  });
  const [editSubmitting, setEditSubmitting] = useState<boolean>(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [statusSubmitting, setStatusSubmitting] = useState<boolean>(false);
  const [statusError, setStatusError] = useState<string | null>(null);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getUsers({
        page,
        page_size: pageSize,
        search: searchTerm.trim() || undefined,
        role: roleFilter || undefined,
        department: deptFilter.trim() || undefined,
        is_active: statusFilter === "" ? undefined : statusFilter === "active",
      });
      setUsers(res.items);
      setTotal(res.total);
      setTotalPages(res.total_pages);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 403) {
        setError("Access denied: Administrator privileges required.");
      } else {
        setError(err.message || "Failed to load user directory.");
      }
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, searchTerm, roleFilter, deptFilter, statusFilter]);

  useEffect(() => {
    if (!authLoading && currentUser && currentUser.role === "admin") {
      fetchUsers();
    }
  }, [authLoading, currentUser, fetchUsers]);

  // Handle Search Submit
  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchUsers();
  };

  // Create User Handler
  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError(null);

    const targetRoleSpec = AVAILABLE_ROLES.find((r) => r.value === createForm.role);
    if (targetRoleSpec?.requiresDept && (!createForm.department || !createForm.department.trim())) {
      setCreateError(`Department is required for role '${targetRoleSpec.label}'.`);
      return;
    }

    if (createForm.password.length < 8) {
      setCreateError("Initial password must be at least 8 characters long.");
      return;
    }

    setCreateSubmitting(true);
    try {
      await api.createUser({
        full_name: createForm.full_name.trim(),
        email: createForm.email.trim(),
        role: createForm.role,
        department: createForm.department?.trim() || null,
        password: createForm.password,
      });
      setShowCreateModal(false);
      setCreateForm({
        full_name: "",
        email: "",
        role: "department_user",
        department: "",
        password: "",
      });
      setSuccessBanner("User account created successfully.");
      setTimeout(() => setSuccessBanner(null), 4000);
      fetchUsers();
    } catch (err: any) {
      setCreateError(err.message || "Failed to create user account.");
    } finally {
      setCreateSubmitting(false);
    }
  };

  // Edit User Handler
  const openEditModal = (u: AdminUser) => {
    setEditingUser(u);
    setEditForm({
      full_name: u.full_name,
      department: u.department || "",
      role: u.role,
    });
    setEditError(null);
  };

  const handleUpdateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingUser) return;
    setEditError(null);

    const targetRoleSpec = AVAILABLE_ROLES.find((r) => r.value === editForm.role);
    if (targetRoleSpec?.requiresDept && (!editForm.department || !editForm.department.trim())) {
      setEditError(`Department is required for role '${targetRoleSpec.label}'.`);
      return;
    }

    setEditSubmitting(true);
    try {
      await api.updateUser(editingUser.id, {
        full_name: editForm.full_name?.trim(),
        department: editForm.department?.trim() || null,
        role: editForm.role,
      });
      setEditingUser(null);
      setSuccessBanner(`User profile for '${editingUser.email}' updated successfully.`);
      setTimeout(() => setSuccessBanner(null), 4000);
      fetchUsers();
    } catch (err: any) {
      setEditError(err.message || "Failed to update user profile.");
    } finally {
      setEditSubmitting(false);
    }
  };

  // Status Toggle Handler
  const handleToggleStatus = async () => {
    if (!statusConfirmUser) return;
    setStatusError(null);
    setStatusSubmitting(true);
    const newStatus = !statusConfirmUser.is_active;

    try {
      await api.updateUserStatus(statusConfirmUser.id, { is_active: newStatus });
      const verb = newStatus ? "activated" : "deactivated";
      setSuccessBanner(`User '${statusConfirmUser.email}' ${verb} successfully.`);
      setTimeout(() => setSuccessBanner(null), 4000);
      setStatusConfirmUser(null);
      fetchUsers();
    } catch (err: any) {
      setStatusError(err.message || "Failed to update user status.");
    } finally {
      setStatusSubmitting(false);
    }
  };

  // Unauthorized Access View
  if (!authLoading && (!currentUser || currentUser.role !== "admin")) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center">
        <div className="inline-flex p-3 rounded-full bg-red-100 text-red-600 mb-4">
          <Shield className="w-8 h-8" />
        </div>
        <h1 className="text-2xl font-bold text-slate-900 mb-2">Administrator Access Required</h1>
        <p className="text-slate-600 max-w-md mx-auto mb-6">
          You do not have administrative privileges to access User Administration. Only system administrators may manage user accounts.
        </p>
      </div>
    );
  }

  return (
    <div className="w-full px-4 sm:px-6 lg:px-8 py-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-6 border-b border-slate-200 mb-6 gap-4">
        <div>
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-blue-50 text-blue-600 rounded-lg">
              <Users className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">User Administration</h1>
              <p className="text-sm text-slate-500">
                Manage accounts, departments, security roles, and activation status
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <button
            type="button"
            onClick={fetchUsers}
            disabled={loading}
            className="inline-flex items-center px-3 py-2 text-xs font-medium text-slate-600 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <button
            type="button"
            onClick={() => {
              setShowCreateModal(true);
              setCreateError(null);
            }}
            className="inline-flex items-center px-4 py-2 text-sm font-semibold text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors shadow-sm"
          >
            <UserPlus className="w-4 h-4 mr-2" />
            Add User
          </button>
        </div>
      </div>

      {/* Success Notification Banner */}
      {successBanner && (
        <div className="mb-6 p-4 rounded-lg bg-green-50 border border-green-200 text-green-800 flex items-center justify-between text-sm animate-fade-in">
          <div className="flex items-center space-x-2">
            <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
            <span className="font-medium">{successBanner}</span>
          </div>
          <button onClick={() => setSuccessBanner(null)} className="text-green-600 hover:text-green-800">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="mb-6 p-4 rounded-lg bg-red-50 border border-red-200 text-red-800 flex items-center space-x-2 text-sm">
          <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0" />
          <span className="font-medium">{error}</span>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm mb-6 space-y-4">
        <form onSubmit={handleSearchSubmit} className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Search Input */}
          <div className="relative md:col-span-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
            <input
              type="text"
              placeholder="Search name or email..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Role Filter */}
          <div>
            <select
              value={roleFilter}
              onChange={(e) => {
                setRoleFilter(e.target.value);
                setPage(1);
              }}
              className="w-full py-2 px-3 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white"
            >
              <option value="">All Roles</option>
              {AVAILABLE_ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>

          {/* Department Filter */}
          <div>
            <input
              type="text"
              placeholder="Filter by department..."
              value={deptFilter}
              onChange={(e) => setDeptFilter(e.target.value)}
              className="w-full py-2 px-3 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Status Filter */}
          <div className="flex space-x-2">
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              className="w-full py-2 px-3 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white"
            >
              <option value="">All Statuses</option>
              <option value="active">Active Only</option>
              <option value="inactive">Inactive Only</option>
            </select>

            <button
              type="submit"
              className="px-4 py-2 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-900 transition-colors shadow-sm"
            >
              Search
            </button>
          </div>
        </form>
      </div>

      {/* Users Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-slate-600 font-semibold text-xs uppercase tracking-wider">
              <tr>
                <th scope="col" className="px-6 py-3.5">
                  User Details
                </th>
                <th scope="col" className="px-6 py-3.5">
                  Role
                </th>
                <th scope="col" className="px-6 py-3.5">
                  Department
                </th>
                <th scope="col" className="px-6 py-3.5">
                  Status
                </th>
                <th scope="col" className="px-6 py-3.5">
                  Created Date
                </th>
                <th scope="col" className="px-6 py-3.5 text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-slate-500">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-blue-600" />
                    <span>Loading users directory...</span>
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-slate-500">
                    <Users className="w-8 h-8 mx-auto mb-2 text-slate-300" />
                    <p className="font-semibold text-slate-700">No users found</p>
                    <p className="text-xs text-slate-500 mt-1">Try adjusting your filters or search terms.</p>
                  </td>
                </tr>
              ) : (
                users.map((u) => {
                  const isCurrent = currentUser?.id === u.id;
                  return (
                    <tr key={u.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center space-x-3">
                          <div className="w-8 h-8 rounded-full bg-slate-100 text-slate-700 font-bold flex items-center justify-center text-xs border border-slate-200">
                            {u.full_name.charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <div className="font-semibold text-slate-900 flex items-center space-x-1.5">
                              <span>{u.full_name}</span>
                              {isCurrent && (
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-800">
                                  You
                                </span>
                              )}
                            </div>
                            <div className="text-xs text-slate-500">{u.email}</div>
                          </div>
                        </div>
                      </td>

                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 text-slate-800 capitalize border border-slate-200">
                          {u.role.replace("_", " ")}
                        </span>
                      </td>

                      <td className="px-6 py-4 whitespace-nowrap text-slate-600">
                        {u.department ? (
                          <div className="flex items-center space-x-1.5">
                            <Building className="w-3.5 h-3.5 text-slate-400" />
                            <span>{u.department}</span>
                          </div>
                        ) : (
                          <span className="text-slate-400 italic text-xs">Unassigned</span>
                        )}
                      </td>

                      <td className="px-6 py-4 whitespace-nowrap">
                        {u.is_active ? (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5"></span>
                            Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-rose-500 mr-1.5"></span>
                            Inactive
                          </span>
                        )}
                      </td>

                      <td className="px-6 py-4 whitespace-nowrap text-xs text-slate-500">
                        {new Date(u.created_at).toLocaleDateString()}
                      </td>

                      <td className="px-6 py-4 whitespace-nowrap text-right text-xs font-medium">
                        <div className="flex items-center justify-end space-x-2">
                          <button
                            type="button"
                            onClick={() => openEditModal(u)}
                            className="inline-flex items-center p-1.5 text-slate-600 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                            title="Edit User Profile"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>

                          <button
                            type="button"
                            onClick={() => {
                              setStatusConfirmUser(u);
                              setStatusError(null);
                            }}
                            className={`inline-flex items-center p-1.5 rounded-lg transition-colors ${
                              u.is_active
                                ? "text-slate-600 hover:text-rose-600 hover:bg-rose-50"
                                : "text-slate-600 hover:text-emerald-600 hover:bg-emerald-50"
                            }`}
                            title={u.is_active ? "Deactivate User" : "Activate User"}
                          >
                            <Power className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        {!loading && totalPages > 1 && (
          <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between">
            <div className="text-xs text-slate-500">
              Showing page <span className="font-semibold text-slate-800">{page}</span> of{" "}
              <span className="font-semibold text-slate-800">{totalPages}</span> ({total} users total)
            </div>
            <div className="flex items-center space-x-2">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-slate-600 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 disabled:opacity-50 transition-colors shadow-sm"
              >
                <ChevronLeft className="w-3.5 h-3.5 mr-1" />
                Previous
              </button>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-slate-600 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 disabled:opacity-50 transition-colors shadow-sm"
              >
                Next
                <ChevronRight className="w-3.5 h-3.5 ml-1" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* CREATE USER MODAL */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-lg w-full p-6 shadow-2xl border border-slate-200 animate-scale-in">
            <div className="flex items-center justify-between pb-4 border-b border-slate-200">
              <div className="flex items-center space-x-2.5">
                <div className="p-2 bg-blue-50 text-blue-600 rounded-lg">
                  <UserPlus className="w-5 h-5" />
                </div>
                <h3 className="text-lg font-bold text-slate-900">Create New User Account</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {createError && (
              <div className="mt-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center space-x-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span>{createError}</span>
              </div>
            )}

            <form onSubmit={handleCreateUser} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Full Display Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Jane Doe"
                  value={createForm.full_name}
                  onChange={(e) => setCreateForm({ ...createForm, full_name: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Email Address <span className="text-red-500">*</span>
                </label>
                <input
                  type="email"
                  required
                  placeholder="e.g. jane.doe@example.com"
                  value={createForm.email}
                  onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Security Role <span className="text-red-500">*</span>
                </label>
                <select
                  value={createForm.role}
                  onChange={(e) => setCreateForm({ ...createForm, role: e.target.value as UserRole })}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  {AVAILABLE_ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-slate-500 mt-1">
                  {AVAILABLE_ROLES.find((r) => r.value === createForm.role)?.description}
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Department{" "}
                  {AVAILABLE_ROLES.find((r) => r.value === createForm.role)?.requiresDept && (
                    <span className="text-red-500">* (Required for this role)</span>
                  )}
                </label>
                <input
                  type="text"
                  placeholder="e.g. Legal, Finance, Operations"
                  value={createForm.department || ""}
                  onChange={(e) => setCreateForm({ ...createForm, department: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Initial Password <span className="text-red-500">*</span>
                </label>
                <input
                  type="password"
                  required
                  placeholder="Minimum 8 characters"
                  value={createForm.password}
                  onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-[11px] text-slate-500 mt-1 flex items-center">
                  <Lock className="w-3 h-3 mr-1 text-slate-400" />
                  Credentials are cryptographically hashed using Argon2id and never stored in plaintext.
                </p>
              </div>

              <div className="flex items-center justify-end space-x-3 pt-4 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  disabled={createSubmitting}
                  className="px-4 py-2 text-xs font-medium text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createSubmitting}
                  className="px-4 py-2 text-xs font-semibold text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
                >
                  {createSubmitting ? "Creating..." : "Create Account"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT USER MODAL */}
      {editingUser && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-lg w-full p-6 shadow-2xl border border-slate-200 animate-scale-in">
            <div className="flex items-center justify-between pb-4 border-b border-slate-200">
              <div className="flex items-center space-x-2.5">
                <div className="p-2 bg-blue-50 text-blue-600 rounded-lg">
                  <Edit2 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-900">Edit User Profile</h3>
                  <p className="text-xs text-slate-500">{editingUser.email}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setEditingUser(null)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {editError && (
              <div className="mt-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center space-x-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span>{editError}</span>
              </div>
            )}

            <form onSubmit={handleUpdateUser} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Full Display Name</label>
                <input
                  type="text"
                  required
                  value={editForm.full_name || ""}
                  onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Security Role</label>
                <select
                  value={editForm.role}
                  onChange={(e) => setEditForm({ ...editForm, role: e.target.value as UserRole })}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  {AVAILABLE_ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-slate-500 mt-1">
                  {AVAILABLE_ROLES.find((r) => r.value === editForm.role)?.description}
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Department{" "}
                  {AVAILABLE_ROLES.find((r) => r.value === editForm.role)?.requiresDept && (
                    <span className="text-red-500">* (Required for this role)</span>
                  )}
                </label>
                <input
                  type="text"
                  placeholder="e.g. Legal, Finance, Operations"
                  value={editForm.department || ""}
                  onChange={(e) => setEditForm({ ...editForm, department: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-4 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setEditingUser(null)}
                  disabled={editSubmitting}
                  className="px-4 py-2 text-xs font-medium text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editSubmitting}
                  className="px-4 py-2 text-xs font-semibold text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
                >
                  {editSubmitting ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* CONFIRM STATUS TOGGLE DIALOG */}
      {statusConfirmUser && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-2xl border border-slate-200 animate-scale-in">
            <div className="flex items-center space-x-3 text-slate-900 mb-4">
              <div
                className={`p-2.5 rounded-full ${
                  statusConfirmUser.is_active ? "bg-rose-100 text-rose-600" : "bg-emerald-100 text-emerald-600"
                }`}
              >
                <Power className="w-5 h-5" />
              </div>
              <h3 className="text-lg font-bold">
                {statusConfirmUser.is_active ? "Deactivate User Account?" : "Activate User Account?"}
              </h3>
            </div>

            <p className="text-xs text-slate-600 mb-4 leading-relaxed">
              {statusConfirmUser.is_active ? (
                <>
                  Are you sure you want to deactivate{" "}
                  <strong className="text-slate-900">{statusConfirmUser.full_name}</strong> (
                  {statusConfirmUser.email})? Deactivated users are immediately prevented from logging in or performing
                  protected actions. Document records and audit history remain preserved.
                </>
              ) : (
                <>
                  Are you sure you want to reactivate{" "}
                  <strong className="text-slate-900">{statusConfirmUser.full_name}</strong> (
                  {statusConfirmUser.email})? The user will regain access to their assigned role and department.
                </>
              )}
            </p>

            {statusError && (
              <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center space-x-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span>{statusError}</span>
              </div>
            )}

            <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-200">
              <button
                type="button"
                onClick={() => setStatusConfirmUser(null)}
                disabled={statusSubmitting}
                className="px-4 py-2 text-xs font-medium text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleToggleStatus}
                disabled={statusSubmitting}
                className={`px-4 py-2 text-xs font-semibold text-white rounded-lg transition-colors shadow-sm ${
                  statusConfirmUser.is_active
                    ? "bg-rose-600 hover:bg-rose-700"
                    : "bg-emerald-600 hover:bg-emerald-700"
                }`}
              >
                {statusSubmitting
                  ? "Processing..."
                  : statusConfirmUser.is_active
                  ? "Yes, Deactivate"
                  : "Yes, Activate"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
