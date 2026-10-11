"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { api, ApiError } from "@/lib/api";
import {
  RetentionRule,
  DisposalEligibilityItem,
  LegalHold,
  DocumentRetentionInfo,
  RetentionPeriodUnit,
  RetentionTriggerEvent,
  DisposalEligibilityStatus,
} from "@/types/retention";
import {
  ShieldAlert,
  Clock,
  FileCheck,
  AlertTriangle,
  Plus,
  Search,
  Filter,
  CheckCircle,
  XCircle,
  Lock,
  Unlock,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Info,
  Calendar,
  Layers,
  FileText,
} from "lucide-react";

export default function RetentionManagementPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<"eligibility" | "rules">("eligibility");

  // Disposal Eligibility State
  const [eligibilityItems, setEligibilityItems] = useState<DisposalEligibilityItem[]>([]);
  const [eligibilityLoading, setEligibilityLoading] = useState(true);
  const [eligibilityError, setEligibilityError] = useState<string | null>(null);
  const [eligibilityPage, setEligibilityPage] = useState(1);
  const [eligibilityTotalPages, setEligibilityTotalPages] = useState(1);
  const [eligibilityTotal, setEligibilityTotal] = useState(0);

  // Eligibility Filters
  const [filterDepartment, setFilterDepartment] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("");
  const [searchDocQuery, setSearchDocQuery] = useState("");

  // Retention Rules State
  const [rules, setRules] = useState<RetentionRule[]>([]);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [rulesError, setRulesError] = useState<string | null>(null);
  const [rulesPage, setRulesPage] = useState(1);
  const [rulesTotalPages, setRulesTotalPages] = useState(1);
  const [rulesTotal, setRulesTotal] = useState(0);
  const [searchRuleQuery, setSearchRuleQuery] = useState("");

  // Modals & Drawers
  const [showCreateRuleModal, setShowCreateRuleModal] = useState(false);
  const [selectedDocForHold, setSelectedDocForHold] = useState<DisposalEligibilityItem | null>(null);
  const [docHolds, setDocHolds] = useState<LegalHold[]>([]);
  const [loadingHolds, setLoadingHolds] = useState(false);
  const [newHoldReason, setNewHoldReason] = useState("");
  const [releaseHoldTarget, setReleaseHoldTarget] = useState<LegalHold | null>(null);
  const [releaseReason, setReleaseReason] = useState("");
  const [selectedRuleToAssign, setSelectedRuleToAssign] = useState<string>("");
  const [assigningRule, setAssigningRule] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // New Rule Form State
  const [ruleName, setRuleName] = useState("");
  const [ruleDescription, setRuleDescription] = useState("");
  const [ruleClassification, setRuleClassification] = useState("");
  const [rulePeriodUnit, setRulePeriodUnit] = useState<RetentionPeriodUnit>("years");
  const [rulePeriodValue, setRulePeriodValue] = useState<number>(5);
  const [ruleTriggerEvent, setRuleTriggerEvent] = useState<RetentionTriggerEvent>("creation");
  const [savingRule, setSavingRule] = useState(false);

  // Role checks
  const canManageRules = user?.role === "admin" || user?.role === "records_officer";
  const canManageHolds = user?.role === "admin" || user?.role === "records_officer";
  const canViewModule =
    user?.role === "admin" ||
    user?.role === "records_officer" ||
    user?.role === "department_user" ||
    user?.role === "auditor";

  // Fetch Eligibility Data
  const fetchEligibility = async () => {
    setEligibilityLoading(true);
    setEligibilityError(null);
    try {
      const res = await api.getDisposalEligibility({
        page: eligibilityPage,
        page_size: 15,
        department: filterDepartment || undefined,
        eligibility_status: filterStatus || undefined,
        q: searchDocQuery || undefined,
      });
      setEligibilityItems(res.items);
      setEligibilityTotal(res.total);
      setEligibilityTotalPages(res.total_pages);
    } catch (err: any) {
      setEligibilityError(err.message || "Failed to load disposal eligibility assessments.");
    } finally {
      setEligibilityLoading(false);
    }
  };

  // Fetch Rules Data
  const fetchRules = async () => {
    setRulesLoading(true);
    setRulesError(null);
    try {
      const res = await api.listRetentionRules({
        page: rulesPage,
        page_size: 15,
        q: searchRuleQuery || undefined,
      });
      setRules(res.items);
      setRulesTotal(res.total);
      setRulesTotalPages(res.total_pages);
    } catch (err: any) {
      setRulesError(err.message || "Failed to load retention rules.");
    } finally {
      setRulesLoading(false);
    }
  };

  useEffect(() => {
    if (canViewModule) {
      fetchEligibility();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eligibilityPage, filterDepartment, filterStatus, canViewModule]);

  useEffect(() => {
    if (activeTab === "rules" && canViewModule) {
      fetchRules();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, rulesPage, canViewModule]);

  // Open Legal Hold & Retention Governance Drawer for Document
  const handleOpenHoldModal = async (doc: DisposalEligibilityItem) => {
    setSelectedDocForHold(doc);
    setSelectedRuleToAssign(doc.retention_rule_id || "");
    setActionError(null);
    setActionSuccess(null);
    setNewHoldReason("");
    setReleaseHoldTarget(null);
    setReleaseReason("");
    setLoadingHolds(true);
    if (rules.length === 0) {
      fetchRules();
    }
    try {
      const holds = await api.listDocumentLegalHolds(doc.document_id);
      setDocHolds(holds);
    } catch (err: any) {
      setActionError(err.message || "Failed to load legal holds.");
    } finally {
      setLoadingHolds(false);
    }
  };

  // Assign Retention Rule to Document
  const handleAssignRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDocForHold || !selectedRuleToAssign) return;
    setActionError(null);
    setActionSuccess(null);
    setAssigningRule(true);
    try {
      const info = await api.assignRetentionRule(selectedDocForHold.document_id, {
        retention_rule_id: selectedRuleToAssign,
      });
      setActionSuccess("Retention schedule successfully assigned to document.");
      setSelectedDocForHold((prev) =>
        prev
          ? {
              ...prev,
              retention_rule_id: info.retention_rule?.id || null,
              retention_rule_name: info.retention_rule?.name || null,
              retention_end_date: info.retention_end_date,
              eligibility_status: info.eligibility_status,
              eligibility_explanation: info.eligibility_explanation,
            }
          : null
      );
      fetchEligibility();
    } catch (err: any) {
      setActionError(err.message || "Failed to assign retention schedule.");
    } finally {
      setAssigningRule(false);
    }
  };

  // Place Legal Hold
  const handlePlaceHold = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDocForHold || !newHoldReason.trim()) return;
    setActionError(null);
    try {
      await api.placeLegalHold(selectedDocForHold.document_id, {
        hold_reason: newHoldReason.trim(),
      });
      setActionSuccess("Legal hold successfully placed on document.");
      setNewHoldReason("");
      const updated = await api.listDocumentLegalHolds(selectedDocForHold.document_id);
      setDocHolds(updated);
      fetchEligibility();
    } catch (err: any) {
      setActionError(err.message || "Failed to place legal hold.");
    }
  };

  // Release Legal Hold
  const handleReleaseHold = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!releaseHoldTarget || !releaseReason.trim()) return;
    setActionError(null);
    try {
      await api.releaseLegalHold(releaseHoldTarget.id, {
        release_reason: releaseReason.trim(),
      });
      setActionSuccess("Legal hold released successfully.");
      setReleaseHoldTarget(null);
      setReleaseReason("");
      if (selectedDocForHold) {
        const updated = await api.listDocumentLegalHolds(selectedDocForHold.document_id);
        setDocHolds(updated);
      }
      fetchEligibility();
    } catch (err: any) {
      setActionError(err.message || "Failed to release legal hold.");
    }
  };

  // Toggle Rule Status
  const handleToggleRuleStatus = async (rule: RetentionRule) => {
    setActionError(null);
    try {
      await api.setRetentionRuleStatus(rule.id, !rule.is_active);
      fetchRules();
    } catch (err: any) {
      setActionError(err.message || "Failed to change retention rule status.");
    }
  };

  // Create Retention Rule
  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ruleName.trim()) return;
    setSavingRule(true);
    setActionError(null);
    try {
      await api.createRetentionRule({
        name: ruleName.trim(),
        description: ruleDescription.trim() || undefined,
        classification: ruleClassification.trim() || undefined,
        retention_period_unit: rulePeriodUnit,
        retention_period_value: Number(rulePeriodValue),
        trigger_event: ruleTriggerEvent,
      });
      setShowCreateRuleModal(false);
      setRuleName("");
      setRuleDescription("");
      setRuleClassification("");
      setRulePeriodValue(5);
      fetchRules();
    } catch (err: any) {
      setActionError(err.message || "Failed to create retention rule.");
    } finally {
      setSavingRule(false);
    }
  };

  if (!canViewModule) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12">
        <div className="bg-red-50 border border-red-200 rounded-xl p-8 text-center max-w-lg mx-auto">
          <ShieldAlert className="w-12 h-12 text-red-600 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-red-900 mb-2">Access Denied</h2>
          <p className="text-sm text-red-700">
            Records retention management and disposal eligibility review are restricted to authorized administrators, records officers, and departmental compliance staff.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-200 pb-5">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Records Retention Governance</h1>
          <p className="text-sm text-slate-500 mt-1">
            Governed retention schedules, legal-hold protections, and disposal eligibility review.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex bg-slate-100 p-1 rounded-lg border border-slate-200">
            <button
              onClick={() => setActiveTab("eligibility")}
              className={`px-4 py-2 text-xs font-semibold rounded-md transition-colors ${
                activeTab === "eligibility"
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Disposal Eligibility
            </button>
            <button
              onClick={() => setActiveTab("rules")}
              className={`px-4 py-2 text-xs font-semibold rounded-md transition-colors ${
                activeTab === "rules"
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Retention Schedules
            </button>
          </div>
        </div>
      </div>

      {/* Global Alerts */}
      {actionError && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between text-sm text-red-700">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 flex-shrink-0" />
            <span>{actionError}</span>
          </div>
          <button onClick={() => setActionError(null)} className="text-xs font-bold underline">
            Dismiss
          </button>
        </div>
      )}

      {actionSuccess && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-lg flex items-center justify-between text-sm text-emerald-800">
          <div className="flex items-center gap-2">
            <CheckCircle className="w-5 h-5 flex-shrink-0" />
            <span>{actionSuccess}</span>
          </div>
          <button onClick={() => setActionSuccess(null)} className="text-xs font-bold underline">
            Dismiss
          </button>
        </div>
      )}

      {/* ------------------------------------------------------------------------- */}
      {/* TAB 1: DISPOSAL ELIGIBILITY REVIEW */}
      {/* ------------------------------------------------------------------------- */}
      {activeTab === "eligibility" && (
        <div className="space-y-6">
          {/* Info Banner */}
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-start gap-3">
            <Info className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
            <div className="text-xs text-blue-900 leading-relaxed">
              <p className="font-semibold mb-1">Disposal Review & Custody Notice</p>
              Records marked <span className="font-semibold text-amber-700">Eligible for Review</span> have reached their configured retention period and possess no active legal holds. Eligibility indicates readiness for formal disposition approval—no permanent deletion or destruction occurs in this phase.
            </div>
          </div>

          {/* Search & Filters */}
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-4 justify-between items-center">
            <div className="flex flex-1 flex-col sm:flex-row gap-3 w-full">
              <div className="relative flex-1">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="text"
                  placeholder="Search reference or title..."
                  value={searchDocQuery}
                  onChange={(e) => setSearchDocQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && fetchEligibility()}
                  className="w-full pl-9 pr-4 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className="px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">All Eligibility States</option>
                <option value="retained">Retained (Active Custody)</option>
                <option value="eligible_for_review">Eligible for Review</option>
                <option value="on_hold">On Hold (Legal Hold Active)</option>
                <option value="needs_attention">Needs Attention (Missing Dates)</option>
              </select>

              <input
                type="text"
                placeholder="Filter department..."
                value={filterDepartment}
                onChange={(e) => setFilterDepartment(e.target.value)}
                className="px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <button
              onClick={fetchEligibility}
              className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Refresh
            </button>
          </div>

          {/* Eligibility Table */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            {eligibilityLoading ? (
              <div className="p-12 text-center text-slate-500">
                <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-3 text-blue-600" />
                <p className="text-sm">Assessing records retention and disposal eligibility...</p>
              </div>
            ) : eligibilityError ? (
              <div className="p-8 text-center text-red-600">
                <AlertTriangle className="w-8 h-8 mx-auto mb-2" />
                <p className="text-sm font-semibold">{eligibilityError}</p>
              </div>
            ) : eligibilityItems.length === 0 ? (
              <div className="p-12 text-center text-slate-500">
                <FileCheck className="w-10 h-10 mx-auto mb-3 text-slate-400" />
                <p className="text-base font-semibold text-slate-800">No records found</p>
                <p className="text-xs text-slate-500 mt-1">No documents match the current retention eligibility filters.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider text-[11px]">
                    <tr>
                      <th className="py-3 px-4">Document</th>
                      <th className="py-3 px-4">Department</th>
                      <th className="py-3 px-4">Retention Schedule</th>
                      <th className="py-3 px-4">Retention End Date</th>
                      <th className="py-3 px-4">Eligibility Status</th>
                      <th className="py-3 px-4">Legal Holds</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {eligibilityItems.map((item) => (
                      <tr key={item.document_id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="py-3 px-4">
                          <p className="font-semibold text-slate-900">{item.title}</p>
                          <p className="text-[11px] text-slate-500 font-mono mt-0.5">{item.document_reference}</p>
                        </td>
                        <td className="py-3 px-4">
                          <span className="inline-block px-2 py-0.5 bg-slate-100 rounded text-slate-700">
                            {item.department}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          {item.retention_rule_name ? (
                            <span className="font-medium text-slate-800">{item.retention_rule_name}</span>
                          ) : (
                            <span className="text-amber-600 italic">No rule assigned</span>
                          )}
                        </td>
                        <td className="py-3 px-4 font-mono">
                          {item.retention_end_date ? (
                            <span>{new Date(item.retention_end_date).toLocaleDateString()}</span>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          {item.eligibility_status === "retained" && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-blue-50 text-blue-700 rounded-full font-medium">
                              <Clock className="w-3.5 h-3.5" />
                              Retained
                            </span>
                          )}
                          {item.eligibility_status === "eligible_for_review" && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-amber-50 text-amber-700 rounded-full font-medium">
                              <AlertTriangle className="w-3.5 h-3.5" />
                              Eligible for Review
                            </span>
                          )}
                          {item.eligibility_status === "on_hold" && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-purple-50 text-purple-700 rounded-full font-medium">
                              <Lock className="w-3.5 h-3.5" />
                              Legal Hold
                            </span>
                          )}
                          {item.eligibility_status === "needs_attention" && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-rose-50 text-rose-700 rounded-full font-medium">
                              <AlertTriangle className="w-3.5 h-3.5" />
                              Needs Attention
                            </span>
                          )}
                          <p className="text-[10px] text-slate-500 mt-1 max-w-xs">{item.eligibility_explanation}</p>
                        </td>
                        <td className="py-3 px-4">
                          {item.has_active_hold ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-100 text-purple-800 rounded font-semibold text-[11px]">
                              <Lock className="w-3 h-3" />
                              {item.active_hold_count} Active
                            </span>
                          ) : (
                            <span className="text-slate-400 text-[11px]">None</span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={() => handleOpenHoldModal(item)}
                            className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-md font-medium text-xs transition-colors"
                          >
                            Holds & Governance
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Pagination Bar */}
            {eligibilityTotalPages > 1 && (
              <div className="p-4 border-t border-slate-200 flex justify-between items-center text-xs text-slate-600">
                <span>
                  Showing page {eligibilityPage} of {eligibilityTotalPages} ({eligibilityTotal} total records)
                </span>
                <div className="flex gap-2">
                  <button
                    disabled={eligibilityPage <= 1}
                    onClick={() => setEligibilityPage((p) => Math.max(1, p - 1))}
                    className="p-1.5 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    disabled={eligibilityPage >= eligibilityTotalPages}
                    onClick={() => setEligibilityPage((p) => p + 1)}
                    className="p-1.5 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------------- */}
      {/* TAB 2: RETENTION SCHEDULES & RULES */}
      {/* ------------------------------------------------------------------------- */}
      {activeTab === "rules" && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="text"
                placeholder="Search schedule name..."
                value={searchRuleQuery}
                onChange={(e) => setSearchRuleQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && fetchRules()}
                className="w-full pl-9 pr-4 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {canManageRules && (
              <button
                onClick={() => setShowCreateRuleModal(true)}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold flex items-center gap-2 shadow-sm transition-colors"
              >
                <Plus className="w-4 h-4" />
                New Retention Schedule
              </button>
            )}
          </div>

          {/* Rules List */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            {rulesLoading ? (
              <div className="p-12 text-center text-slate-500">
                <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-3 text-blue-600" />
                <p className="text-sm">Loading retention schedules...</p>
              </div>
            ) : rulesError ? (
              <div className="p-8 text-center text-red-600">
                <AlertTriangle className="w-8 h-8 mx-auto mb-2" />
                <p className="text-sm font-semibold">{rulesError}</p>
              </div>
            ) : rules.length === 0 ? (
              <div className="p-12 text-center text-slate-500">
                <Clock className="w-10 h-10 mx-auto mb-3 text-slate-400" />
                <p className="text-base font-semibold text-slate-800">No retention rules configured</p>
                <p className="text-xs text-slate-500 mt-1">Configure retention schedules to govern custody periods.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider text-[11px]">
                    <tr>
                      <th className="py-3 px-4">Rule Name</th>
                      <th className="py-3 px-4">Classification</th>
                      <th className="py-3 px-4">Retention Period</th>
                      <th className="py-3 px-4">Trigger Event</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    {rules.map((rule) => (
                      <tr key={rule.id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="py-3 px-4">
                          <p className="font-semibold text-slate-900">{rule.name}</p>
                          {rule.description && (
                            <p className="text-[11px] text-slate-500 mt-0.5 line-clamp-1">{rule.description}</p>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          <span className="inline-block px-2 py-0.5 bg-slate-100 rounded text-slate-700">
                            {rule.classification || "All Classifications"}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-semibold text-slate-800">
                          {rule.retention_period_value} {rule.retention_period_unit}
                        </td>
                        <td className="py-3 px-4 capitalize text-slate-700">
                          On {rule.trigger_event}
                        </td>
                        <td className="py-3 px-4">
                          {rule.is_active ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-emerald-50 text-emerald-700 rounded-full font-semibold">
                              <CheckCircle className="w-3 h-3" />
                              Active
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-slate-100 text-slate-600 rounded-full font-semibold">
                              <XCircle className="w-3 h-3" />
                              Inactive
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right">
                          {canManageRules && (
                            <button
                              onClick={() => handleToggleRuleStatus(rule)}
                              className={`px-3 py-1 rounded text-xs font-semibold transition-colors ${
                                rule.is_active
                                  ? "bg-amber-50 hover:bg-amber-100 text-amber-800"
                                  : "bg-emerald-50 hover:bg-emerald-100 text-emerald-800"
                              }`}
                            >
                              {rule.is_active ? "Deactivate" : "Activate"}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------------- */}
      {/* MODAL: CREATE RETENTION RULE */}
      {/* ------------------------------------------------------------------------- */}
      {showCreateRuleModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-100 space-y-4">
            <div className="flex justify-between items-center border-b border-slate-100 pb-3">
              <h3 className="text-base font-bold text-slate-900">Create Retention Schedule</h3>
              <button
                onClick={() => setShowCreateRuleModal(false)}
                className="text-slate-400 hover:text-slate-600 text-sm font-semibold"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateRule} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Schedule Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g., Financial Audit Records (7 Years)"
                  value={ruleName}
                  onChange={(e) => setRuleName(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Description</label>
                <textarea
                  rows={2}
                  placeholder="Policy context and legal basis..."
                  value={ruleDescription}
                  onChange={(e) => setRuleDescription(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Duration Count *</label>
                  <input
                    type="number"
                    min="1"
                    required
                    value={rulePeriodValue}
                    onChange={(e) => setRulePeriodValue(Number(e.target.value))}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Time Unit *</label>
                  <select
                    value={rulePeriodUnit}
                    onChange={(e) => setRulePeriodUnit(e.target.value as RetentionPeriodUnit)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="days">Days</option>
                    <option value="months">Months</option>
                    <option value="years">Years</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Lifecycle Trigger *</label>
                  <select
                    value={ruleTriggerEvent}
                    onChange={(e) => setRuleTriggerEvent(e.target.value as RetentionTriggerEvent)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="creation">Document Creation</option>
                    <option value="approval">Document Approval</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Classification Target</label>
                  <input
                    type="text"
                    placeholder="e.g. Contract, Audit"
                    value={ruleClassification}
                    onChange={(e) => setRuleClassification(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowCreateRuleModal(false)}
                  className="px-4 py-2 border border-slate-200 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingRule}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg text-xs font-semibold hover:bg-blue-700 disabled:opacity-50"
                >
                  {savingRule ? "Creating..." : "Save Retention Rule"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------------- */}
      {/* DRAWER / MODAL: LEGAL HOLDS & DOCUMENT GOVERNANCE */}
      {/* ------------------------------------------------------------------------- */}
      {selectedDocForHold && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl border border-slate-100 space-y-5 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-start border-b border-slate-100 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-900">Retention & Legal Holds Governance</h3>
                <p className="text-xs text-slate-500 font-mono mt-0.5">
                  {selectedDocForHold.title} ({selectedDocForHold.document_reference})
                </p>
              </div>
              <button
                onClick={() => setSelectedDocForHold(null)}
                className="text-slate-400 hover:text-slate-600 text-sm font-semibold"
              >
                ✕
              </button>
            </div>

            {/* Modal Feedback Alerts */}
            {actionSuccess && (
              <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>{actionSuccess}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setActionSuccess(null)}
                  className="text-emerald-700 font-bold hover:text-emerald-900"
                >
                  ✕
                </button>
              </div>
            )}

            {actionError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
                  <span>{actionError}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setActionError(null)}
                  className="text-rose-700 font-bold hover:text-rose-900"
                >
                  ✕
                </button>
              </div>
            )}

            {/* SECTION 1: RETENTION SCHEDULE ASSIGNMENT */}
            <div className="p-4 bg-blue-50/50 border border-blue-200 rounded-xl space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-blue-900 font-semibold text-xs">
                  <Clock className="w-4 h-4 text-blue-700" />
                  <span>Retention Schedule</span>
                </div>
                <span
                  className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                    selectedDocForHold.retention_rule_name
                      ? "bg-blue-100 text-blue-800"
                      : "bg-amber-100 text-amber-800"
                  }`}
                >
                  {selectedDocForHold.retention_rule_name || "No rule assigned"}
                </span>
              </div>

              {selectedDocForHold.retention_end_date ? (
                <div className="text-[11px] text-slate-600 flex items-center gap-2">
                  <span>Scheduled Retention End Date:</span>
                  <span className="font-semibold text-slate-900">
                    {new Date(selectedDocForHold.retention_end_date).toLocaleDateString()}
                  </span>
                </div>
              ) : (
                <p className="text-[11px] text-slate-500">
                  Assign an active retention schedule below to calculate and govern when this document becomes eligible for review or disposal.
                </p>
              )}

              {canManageRules && (
                <form
                  onSubmit={handleAssignRule}
                  className="pt-2 border-t border-blue-100 flex flex-col sm:flex-row gap-2 items-stretch sm:items-center"
                >
                  <select
                    value={selectedRuleToAssign}
                    onChange={(e) => setSelectedRuleToAssign(e.target.value)}
                    className="flex-1 px-3 py-1.5 border border-blue-300 rounded-lg text-xs bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Select Retention Schedule to assign...</option>
                    {rules
                      .filter((r) => r.is_active)
                      .map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.name} ({r.retention_period_value} {r.retention_period_unit})
                        </option>
                      ))}
                  </select>
                  <button
                    type="submit"
                    disabled={!selectedRuleToAssign || assigningRule}
                    className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors disabled:opacity-50 shrink-0"
                  >
                    {assigningRule ? "Assigning..." : "Assign Schedule"}
                  </button>
                </form>
              )}
            </div>

            {/* SECTION 2: PLACE NEW LEGAL HOLD */}
            {canManageHolds && (
              <form onSubmit={handlePlaceHold} className="p-4 bg-purple-50/50 border border-purple-200 rounded-xl space-y-3">
                <div className="flex items-center gap-2 text-purple-900 font-semibold text-xs">
                  <Lock className="w-4 h-4 text-purple-700" />
                  <span>Place New Legal Hold</span>
                </div>
                <textarea
                  rows={2}
                  required
                  placeholder="Specify legal or regulatory reason for suspending disposal eligibility..."
                  value={newHoldReason}
                  onChange={(e) => setNewHoldReason(e.target.value)}
                  className="w-full px-3 py-2 border border-purple-200 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-purple-500 bg-white"
                />
                <div className="flex justify-end">
                  <button
                    type="submit"
                    className="px-4 py-1.5 bg-purple-700 hover:bg-purple-800 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors"
                  >
                    Apply Legal Hold
                  </button>
                </div>
              </form>
            )}

            {/* Release Hold Confirmation Section */}
            {releaseHoldTarget && (
              <form onSubmit={handleReleaseHold} className="p-4 bg-amber-50 border border-amber-200 rounded-xl space-y-3">
                <div className="flex items-center gap-2 text-amber-900 font-semibold text-xs">
                  <Unlock className="w-4 h-4 text-amber-700" />
                  <span>Confirm Release of Legal Hold</span>
                </div>
                <p className="text-[11px] text-amber-800">
                  Releasing this hold will allow the document to be assessed according to its standard retention schedule. A release comment is mandatory.
                </p>
                <textarea
                  rows={2}
                  required
                  placeholder="Enter reason for releasing evidentiary hold..."
                  value={releaseReason}
                  onChange={(e) => setReleaseReason(e.target.value)}
                  className="w-full px-3 py-2 border border-amber-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-amber-500 bg-white"
                />
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setReleaseHoldTarget(null)}
                    className="px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-semibold hover:bg-white text-slate-700"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-1.5 bg-amber-700 hover:bg-amber-800 text-white rounded-lg text-xs font-semibold"
                  >
                    Confirm Release
                  </button>
                </div>
              </form>
            )}

            {/* Existing Holds History */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">Legal Holds History</h4>
              {loadingHolds ? (
                <div className="p-6 text-center text-xs text-slate-500">Loading holds...</div>
              ) : docHolds.length === 0 ? (
                <p className="text-xs text-slate-500 italic p-3 bg-slate-50 rounded-lg text-center">
                  No legal holds have been recorded for this document.
                </p>
              ) : (
                <div className="space-y-2">
                  {docHolds.map((h) => (
                    <div
                      key={h.id}
                      className={`p-3 rounded-lg border text-xs flex justify-between items-start ${
                        h.status === "active"
                          ? "bg-purple-50/40 border-purple-200 text-purple-950"
                          : "bg-slate-50 border-slate-200 text-slate-600"
                      }`}
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span
                            className={`px-2 py-0.5 rounded font-bold text-[10px] uppercase ${
                              h.status === "active" ? "bg-purple-600 text-white" : "bg-slate-200 text-slate-700"
                            }`}
                          >
                            {h.status}
                          </span>
                          <span className="text-[11px] text-slate-500">
                            Placed {new Date(h.placed_at).toLocaleDateString()}
                          </span>
                        </div>
                        <p className="font-medium text-slate-800 mt-1">{h.hold_reason}</p>
                        {h.released_at && (
                          <p className="text-[11px] text-slate-500 italic mt-1">
                            Released on {new Date(h.released_at).toLocaleDateString()}: &ldquo;{h.release_reason}&rdquo;
                          </p>
                        )}
                      </div>

                      {h.status === "active" && canManageHolds && !releaseHoldTarget && (
                        <button
                          onClick={() => setReleaseHoldTarget(h)}
                          className="px-2.5 py-1 bg-white border border-purple-300 hover:bg-purple-50 text-purple-800 rounded font-semibold text-[11px] shadow-sm ml-3 flex-shrink-0"
                        >
                          Release Hold
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="pt-3 border-t border-slate-100 flex justify-end">
              <button
                onClick={() => setSelectedDocForHold(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
