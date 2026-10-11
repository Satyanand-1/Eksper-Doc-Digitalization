"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { api, ApiError } from "@/lib/api";
import { AuditLogSummary, AuditLogDetail, AuditReportSummary } from "@/types/audit";
import {
  ShieldAlert,
  Search,
  Filter,
  Calendar,
  Eye,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  X,
  Activity,
  FileText,
  UserCheck,
  Building,
} from "lucide-react";

export default function AuditLogsPage() {
  const { user: currentUser, loading: authLoading } = useAuth();

  // Audit Logs State
  const [logs, setLogs] = useState<AuditLogSummary[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [page, setPage] = useState<number>(1);
  const [pageSize] = useState<number>(15);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [actionFilter, setActionFilter] = useState<string>("");
  const [resourceTypeFilter, setResourceTypeFilter] = useState<string>("");
  const [outcomeFilter, setOutcomeFilter] = useState<string>("");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");

  // Report Metrics Summary
  const [reportSummary, setReportSummary] = useState<AuditReportSummary | null>(null);
  const [reportLoading, setReportLoading] = useState<boolean>(false);

  // Detail Modal State
  const [selectedLogId, setSelectedLogId] = useState<string | null>(null);
  const [detailLog, setDetailLog] = useState<AuditLogDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const isAuthorized =
    currentUser && (currentUser.role === "admin" || currentUser.role === "records_officer");

  const fetchLogs = useCallback(async () => {
    if (!isAuthorized) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.getAuditLogs({
        page,
        page_size: pageSize,
        search: searchTerm.trim() || undefined,
        action: actionFilter || undefined,
        resource_type: resourceTypeFilter || undefined,
        outcome: outcomeFilter || undefined,
        start_date: startDate ? new Date(startDate).toISOString() : undefined,
        end_date: endDate ? new Date(endDate).toISOString() : undefined,
      });
      setLogs(res.items);
      setTotal(res.total);
      setTotalPages(res.total_pages);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 403) {
        setError("Access denied: You do not have permission to view audit logs.");
      } else {
        setError(err.message || "Failed to load audit logs.");
      }
    } finally {
      setLoading(false);
    }
  }, [isAuthorized, page, pageSize, searchTerm, actionFilter, resourceTypeFilter, outcomeFilter, startDate, endDate]);

  const fetchReportSummary = useCallback(async () => {
    if (!isAuthorized) return;
    setReportLoading(true);
    try {
      const res = await api.getAuditReportSummary({
        start_date: startDate ? new Date(startDate).toISOString() : undefined,
        end_date: endDate ? new Date(endDate).toISOString() : undefined,
      });
      setReportSummary(res);
    } catch {
      // Non-fatal if report summary fails
    } finally {
      setReportLoading(false);
    }
  }, [isAuthorized, startDate, endDate]);

  useEffect(() => {
    if (!authLoading && isAuthorized) {
      fetchLogs();
      fetchReportSummary();
    }
  }, [authLoading, isAuthorized, fetchLogs, fetchReportSummary]);

  const handleFilterSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (startDate && endDate && new Date(startDate) > new Date(endDate)) {
      setError("Start date cannot be after end date.");
      return;
    }
    setPage(1);
    fetchLogs();
    fetchReportSummary();
  };

  const handleOpenDetail = async (id: string) => {
    setSelectedLogId(id);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const detail = await api.getAuditLogDetail(id);
      setDetailLog(detail);
    } catch (err: any) {
      setDetailError(err.message || "Failed to retrieve audit log details.");
    } finally {
      setDetailLoading(false);
    }
  };

  const handleCloseDetail = () => {
    setSelectedLogId(null);
    setDetailLog(null);
    setDetailError(null);
  };

  // Unauthorized Access View
  if (!authLoading && !isAuthorized) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center">
        <div className="inline-flex p-3 rounded-full bg-red-100 text-red-600 mb-4">
          <ShieldAlert className="w-8 h-8" />
        </div>
        <h1 className="text-2xl font-bold text-slate-900 mb-2">Audit Access Denied</h1>
        <p className="text-slate-600 max-w-md mx-auto mb-6">
          Access to audit logs and governance activity reports is restricted to Administrators and Records Officers.
        </p>
      </div>
    );
  }

  return (
    <div className="w-full px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-6 border-b border-slate-200 mb-6 gap-4">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-indigo-50 text-indigo-600 rounded-lg">
            <Activity className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Audit Log Viewer</h1>
            <p className="text-sm text-slate-500">
              Immutable traceability of document operations, review decisions, cancellations, and administration events
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <button
            type="button"
            onClick={() => {
              fetchLogs();
              fetchReportSummary();
            }}
            disabled={loading}
            className="inline-flex items-center px-3 py-2 text-xs font-medium text-slate-600 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Aggregate Report Cards */}
      {reportSummary && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <div className="text-xs font-medium text-slate-500 mb-1">Total Audited Events</div>
            <div className="text-2xl font-bold text-slate-900">{reportSummary.total_events}</div>
          </div>
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <div className="text-xs font-medium text-slate-500 mb-1">Successful Outcomes</div>
            <div className="text-2xl font-bold text-emerald-600">
              {reportSummary.events_by_outcome["success"] || 0}
            </div>
          </div>
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <div className="text-xs font-medium text-slate-500 mb-1">Access Denials / Failures</div>
            <div className="text-2xl font-bold text-rose-600">
              {(reportSummary.events_by_outcome["denied"] || 0) + (reportSummary.events_by_outcome["failed"] || 0)}
            </div>
          </div>
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <div className="text-xs font-medium text-slate-500 mb-1">Security / Admin Events</div>
            <div className="text-2xl font-bold text-indigo-600">
              {reportSummary.recent_security_events.length}
            </div>
          </div>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="mb-6 p-4 rounded-lg bg-red-50 border border-red-200 text-red-800 flex items-center space-x-2 text-sm">
          <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0" />
          <span className="font-medium">{error}</span>
        </div>
      )}

      {/* Filter and Search Panel */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm mb-6 space-y-4">
        <form onSubmit={handleFilterSubmit} className="grid grid-cols-1 md:grid-cols-6 gap-3">
          {/* Keyword Search */}
          <div className="md:col-span-2 relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
            <input
              type="text"
              placeholder="Search action, resource, IP..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          {/* Action Filter */}
          <div>
            <select
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              className="w-full py-2 px-3 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
            >
              <option value="">All Actions</option>
              <option value="document.upload">document.upload</option>
              <option value="document.version_upload">document.version_upload</option>
              <option value="document.download">document.download</option>
              <option value="document.preview">document.preview</option>
              <option value="workflow.submit_for_review">workflow.submit_for_review</option>
              <option value="workflow.approved">workflow.approved</option>
              <option value="workflow.rejected">workflow.rejected</option>
              <option value="workflow.cancelled">workflow.cancelled</option>
              <option value="user.create">user.create</option>
              <option value="user.update">user.update</option>
              <option value="user.activate">user.activate</option>
              <option value="user.deactivate">user.deactivate</option>
            </select>
          </div>

          {/* Outcome Filter */}
          <div>
            <select
              value={outcomeFilter}
              onChange={(e) => setOutcomeFilter(e.target.value)}
              className="w-full py-2 px-3 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
            >
              <option value="">All Outcomes</option>
              <option value="success">Success</option>
              <option value="denied">Denied</option>
              <option value="failed">Failed</option>
            </select>
          </div>

          {/* Start Date */}
          <div>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full py-2 px-3 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
            />
          </div>

          {/* End Date */}
          <div className="flex space-x-2">
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full py-2 px-3 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
            />
            <button
              type="submit"
              className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors shadow-sm"
            >
              Filter
            </button>
          </div>
        </form>
      </div>

      {/* Audit Logs Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-slate-600 font-semibold text-xs uppercase tracking-wider">
              <tr>
                <th scope="col" className="px-6 py-3.5">Timestamp</th>
                <th scope="col" className="px-6 py-3.5">Action</th>
                <th scope="col" className="px-6 py-3.5">Resource</th>
                <th scope="col" className="px-6 py-3.5">Actor</th>
                <th scope="col" className="px-6 py-3.5">Outcome</th>
                <th scope="col" className="px-6 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-slate-500">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-600" />
                    <span>Loading audit records...</span>
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-slate-500">
                    <Activity className="w-8 h-8 mx-auto mb-2 text-slate-300" />
                    <p className="font-semibold text-slate-700">No audit events found</p>
                    <p className="text-xs text-slate-500 mt-1">Try adjusting your date range or filters.</p>
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap text-xs text-slate-600">
                      {new Date(log.created_at).toLocaleString()}
                    </td>

                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="font-mono text-xs font-semibold text-slate-900 bg-slate-100 px-2 py-1 rounded">
                        {log.action}
                      </span>
                    </td>

                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-xs">
                        <span className="font-medium text-slate-800 capitalize">{log.resource_type}</span>
                        {log.resource_id && (
                          <div className="font-mono text-[11px] text-slate-400">
                            {log.resource_id.substring(0, 8)}...
                          </div>
                        )}
                      </div>
                    </td>

                    <td className="px-6 py-4 whitespace-nowrap">
                      {log.actor ? (
                        <div>
                          <div className="text-xs font-semibold text-slate-800">{log.actor.full_name}</div>
                          <div className="text-[11px] text-slate-400">{log.actor.email}</div>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400 italic">System / Unauthenticated</span>
                      )}
                    </td>

                    <td className="px-6 py-4 whitespace-nowrap">
                      {log.outcome === "success" ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <CheckCircle2 className="w-3.5 h-3.5 mr-1 text-emerald-600" />
                          Success
                        </span>
                      ) : log.outcome === "denied" ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200">
                          <XCircle className="w-3.5 h-3.5 mr-1 text-rose-600" />
                          Denied
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
                          <AlertTriangle className="w-3.5 h-3.5 mr-1 text-amber-600" />
                          Failed
                        </span>
                      )}
                    </td>

                    <td className="px-6 py-4 whitespace-nowrap text-right text-xs font-medium">
                      <button
                        type="button"
                        onClick={() => handleOpenDetail(log.id)}
                        className="inline-flex items-center px-2.5 py-1.5 text-xs text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 rounded-lg transition-colors"
                        title="View Event Details"
                      >
                        <Eye className="w-3.5 h-3.5 mr-1" />
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        {!loading && totalPages > 1 && (
          <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between">
            <div className="text-xs text-slate-500">
              Showing page <span className="font-semibold text-slate-800">{page}</span> of{" "}
              <span className="font-semibold text-slate-800">{totalPages}</span> ({total} events total)
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

      {/* DETAIL DRAWER / MODAL */}
      {selectedLogId && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-2xl w-full p-6 shadow-2xl border border-slate-200 animate-scale-in max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-4 border-b border-slate-200">
              <div className="flex items-center space-x-2.5">
                <div className="p-2 bg-indigo-50 text-indigo-600 rounded-lg">
                  <Activity className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-900">Audit Event Details</h3>
                  <p className="font-mono text-xs text-slate-400">{selectedLogId}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={handleCloseDetail}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {detailLoading ? (
              <div className="py-12 text-center text-slate-500">
                <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-600" />
                <span>Loading event details...</span>
              </div>
            ) : detailError ? (
              <div className="mt-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center space-x-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span>{detailError}</span>
              </div>
            ) : detailLog ? (
              <div className="mt-4 space-y-4 text-xs">
                {/* Event Summary Grid */}
                <div className="grid grid-cols-2 gap-4 bg-slate-50 p-3.5 rounded-lg border border-slate-200">
                  <div>
                    <span className="text-slate-500 block mb-0.5">Action Name</span>
                    <span className="font-mono font-semibold text-slate-900">{detailLog.action}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block mb-0.5">Timestamp (UTC)</span>
                    <span className="text-slate-800">{new Date(detailLog.created_at).toUTCString()}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block mb-0.5">Outcome</span>
                    <span className="capitalize font-semibold text-slate-800">{detailLog.outcome}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block mb-0.5">Resource</span>
                    <span className="text-slate-800 font-mono">
                      {detailLog.resource_type}: {detailLog.resource_id || "N/A"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block mb-0.5">Actor</span>
                    <span className="text-slate-800">
                      {detailLog.actor ? `${detailLog.actor.full_name} (${detailLog.actor.email})` : "System / Anonymous"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block mb-0.5">Client IP</span>
                    <span className="font-mono text-slate-800">{detailLog.client_ip || "N/A"}</span>
                  </div>
                </div>

                {/* Structured Sanitized Context Payload */}
                <div>
                  <h4 className="font-bold text-slate-800 mb-2">Sanitized Context Metadata</h4>
                  {detailLog.details && Object.keys(detailLog.details).length > 0 ? (
                    <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg font-mono text-[11px] overflow-x-auto leading-relaxed border border-slate-800">
                      {JSON.stringify(detailLog.details, null, 2)}
                    </pre>
                  ) : (
                    <div className="p-4 bg-slate-50 rounded-lg text-slate-400 italic text-center border border-slate-200">
                      No additional contextual metadata recorded for this event.
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-end pt-4 border-t border-slate-200">
                  <button
                    type="button"
                    onClick={handleCloseDetail}
                    className="px-4 py-2 text-xs font-semibold text-white bg-slate-800 hover:bg-slate-900 rounded-lg transition-colors shadow-sm"
                  >
                    Close
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
