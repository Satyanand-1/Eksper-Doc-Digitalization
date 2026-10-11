"use client";

import React, { useState, useEffect } from "react";
import { DocumentWorkflowHistoryResponse, WorkflowHistoryAttempt } from "@/types/workflow";
import { api, ApiError } from "@/lib/api";
import {
  History,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  User,
  Calendar,
  MessageSquare,
  RefreshCw,
  AlertTriangle,
  RotateCcw,
} from "lucide-react";

interface WorkflowHistoryListProps {
  documentId: string;
  refreshTrigger?: number;
}

export function WorkflowHistoryList({ documentId, refreshTrigger }: WorkflowHistoryListProps) {
  const [history, setHistory] = useState<DocumentWorkflowHistoryResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function fetchHistory() {
      if (!documentId) return;
      setLoading(true);
      setError(null);
      try {
        const data = await api.getDocumentWorkflowHistory(documentId);
        if (isMounted) setHistory(data);
      } catch (err: any) {
        if (isMounted) {
          if (err instanceof ApiError && err.status === 404) {
            setError("Workflow history not found or access denied.");
          } else {
            setError(err.message || "Failed to load workflow history.");
          }
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchHistory();
    return () => {
      isMounted = false;
    };
  }, [documentId, refreshTrigger]);

  const getStateBadge = (state: string) => {
    switch (state) {
      case "pending":
        return {
          icon: <Clock className="w-3.5 h-3.5 text-amber-600" />,
          bg: "bg-amber-50 text-amber-700 border-amber-200",
          label: "Pending Review",
        };
      case "approved":
        return {
          icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />,
          bg: "bg-emerald-50 text-emerald-700 border-emerald-200",
          label: "Approved",
        };
      case "rejected":
        return {
          icon: <XCircle className="w-3.5 h-3.5 text-rose-600" />,
          bg: "bg-rose-50 text-rose-700 border-rose-200",
          label: "Rejected",
        };
      case "cancelled":
        return {
          icon: <AlertCircle className="w-3.5 h-3.5 text-slate-600" />,
          bg: "bg-slate-100 text-slate-700 border-slate-200",
          label: "Cancelled / Withdrawn",
        };
      default:
        return {
          icon: <Clock className="w-3.5 h-3.5 text-slate-600" />,
          bg: "bg-slate-50 text-slate-700 border-slate-200",
          label: state,
        };
    }
  };

  return (
    <div data-testid="workflow-history-section" className="bg-white rounded-xl border border-slate-200 shadow-2xs p-6">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
        <div className="flex items-center space-x-2">
          <History className="w-4 h-4 text-blue-600" />
          <h3 className="text-sm font-bold text-slate-900">Workflow Review History</h3>
        </div>
        {history && (
          <span className="text-xs text-slate-500 font-medium">
            {history.total_attempts} {history.total_attempts === 1 ? "attempt" : "attempts"}
          </span>
        )}
      </div>

      {/* Loading Skeleton */}
      {loading && (
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="p-4 rounded-lg border border-slate-100 bg-slate-50/50 animate-pulse space-y-2">
              <div className="h-4 bg-slate-200 rounded w-1/4" />
              <div className="h-3 bg-slate-200 rounded w-1/2" />
            </div>
          ))}
        </div>
      )}

      {/* Error state */}
      {error && (
        <div data-testid="workflow-history-error" className="p-3.5 bg-red-50 text-red-800 rounded-lg text-xs border border-red-200 flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && (!history || history.attempts.length === 0) && (
        <div data-testid="workflow-history-empty" className="p-8 text-center text-slate-400 text-xs">
          <History className="w-8 h-8 text-slate-300 mx-auto mb-2" />
          <p className="font-medium text-slate-600">No review attempts yet</p>
          <p className="text-[11px] text-slate-400 mt-0.5">
            When this document is submitted for review, submission and decision history will appear here.
          </p>
        </div>
      )}

      {/* History attempts list (chronological) */}
      {!loading && history && history.attempts.length > 0 && (
        <div className="space-y-4">
          {history.attempts.map((attempt, index) => {
            const badge = getStateBadge(attempt.state);
            const formattedSubmittedDate = new Date(attempt.submitted_at).toLocaleString(undefined, {
              dateStyle: "medium",
              timeStyle: "short",
            });

            return (
              <div
                key={attempt.workflow_id}
                data-testid={`history-attempt-${attempt.workflow_id}`}
                className="p-4 rounded-xl border border-slate-200/80 bg-slate-50/40 space-y-3"
              >
                {/* Attempt Header */}
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-xs text-slate-800">
                      Attempt #{index + 1}
                    </span>
                    <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded border ${badge.bg}`}>
                      {badge.icon}
                      <span>{badge.label}</span>
                    </span>
                  </div>
                  <span className="text-[11px] text-slate-400">
                    Submitted: {formattedSubmittedDate}
                  </span>
                </div>

                {/* Submitter Info */}
                <div className="flex items-center gap-2 text-xs text-slate-600">
                  <User className="w-3.5 h-3.5 text-slate-400" />
                  <span>Submitted by <strong>{attempt.submitter.full_name}</strong> ({attempt.submitter.email})</span>
                </div>

                {/* Submitter Comments */}
                {attempt.submission_comments && (
                  <div className="p-2.5 bg-white rounded border border-slate-200 text-xs text-slate-600">
                    <span className="font-semibold text-slate-700">Submission Note: </span>
                    <span className="italic">{attempt.submission_comments}</span>
                  </div>
                )}

                {/* Assignments & Decisions */}
                {attempt.assignments.length > 0 && (
                  <div className="pt-2 border-t border-slate-200/60 space-y-2">
                    <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">
                      Approver Assignments & Decisions
                    </span>
                    {attempt.assignments.map((assignment) => {
                      const decBadge = assignment.decision === "approved"
                        ? { bg: "text-emerald-700 bg-emerald-50 border-emerald-200", label: "Approved" }
                        : assignment.decision === "rejected"
                        ? { bg: "text-rose-700 bg-rose-50 border-rose-200", label: "Rejected" }
                        : { bg: "text-amber-700 bg-amber-50 border-amber-200", label: "Pending" };

                      return (
                        <div
                          key={assignment.id}
                          className="p-3 bg-white rounded-lg border border-slate-200 text-xs space-y-1.5"
                        >
                          <div className="flex items-center justify-between flex-wrap gap-2">
                            <div className="flex items-center gap-1.5 font-medium text-slate-800">
                              <span>{assignment.assigned_approver.full_name}</span>
                              <span className="text-slate-400">({assignment.assigned_approver.department || "Approver"})</span>
                            </div>
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${decBadge.bg}`}>
                              {decBadge.label}
                            </span>
                          </div>

                          {assignment.decided_at && (
                            <div className="text-[11px] text-slate-400 flex items-center gap-1">
                              <Calendar className="w-3 h-3 text-slate-400" />
                              <span>
                                Decided on {new Date(assignment.decided_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
                              </span>
                            </div>
                          )}

                          {assignment.decision_comments && (
                            <div className="mt-1 p-2 bg-slate-50 rounded border border-slate-100 text-xs text-slate-700">
                              <span className="font-semibold text-slate-800">Approver Comments: </span>
                              <span>{assignment.decision_comments}</span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Cancellation Details */}
                {attempt.cancelled_at && (
                  <div className="pt-2 border-t border-slate-200/60 text-xs text-slate-600 space-y-1">
                    <div className="flex items-center gap-1.5 text-slate-700">
                      <AlertCircle className="w-3.5 h-3.5 text-slate-500" />
                      <span>
                        Cancelled by <strong>{attempt.cancelled_by?.full_name || "Authorized User"}</strong> on{" "}
                        {new Date(attempt.cancelled_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
                      </span>
                    </div>
                    {attempt.cancellation_comments && (
                      <div className="p-2 bg-white rounded border border-slate-200 text-xs text-slate-600">
                        <span className="font-semibold text-slate-700">Reason: </span>
                        <span>{attempt.cancellation_comments}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
