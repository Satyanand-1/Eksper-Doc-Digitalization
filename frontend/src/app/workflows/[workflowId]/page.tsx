"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { useNotificationContext } from "@/context/NotificationContext";
import { api, ApiError, getStoredToken } from "@/lib/api";
import {
  WorkflowDetailResponse,
  WorkflowDecisionResponse,
  ReviewDecision,
} from "@/types/workflow";
import {
  FileText,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  AlertTriangle,
  Building,
  Tag,
  User,
  Calendar,
  FileCheck2,
  FileCode,
  ArrowLeft,
  RefreshCw,
  ShieldAlert,
  MessageSquare,
  HelpCircle,
  Send,
  X,
  Download,
  Eye,
  ExternalLink,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

export default function WorkflowReviewPage() {
  const params = useParams();
  const router = useRouter();
  const workflowId = params?.workflowId as string;

  const { user, loading: authLoading } = useAuth();
  const { refreshUnreadCount } = useNotificationContext();

  const [workflow, setWorkflow] = useState<WorkflowDetailResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [showOcrText, setShowOcrText] = useState<boolean>(true);

  // Decision Modal State
  const [modalOpen, setModalOpen] = useState<boolean>(false);
  const [modalDecision, setModalDecision] = useState<ReviewDecision>("approved");
  const [commentsInput, setCommentsInput] = useState<string>("");
  const [modalValidationError, setModalValidationError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [modalApiError, setModalApiError] = useState<string | null>(null);

  const fetchWorkflow = useCallback(async () => {
    if (!workflowId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getWorkflowDetail(workflowId);
      setWorkflow(data);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 404) {
        setError("Review workflow not found or you are not authorized to view this document.");
      } else {
        setError(err.message || "Failed to load workflow details.");
      }
    } finally {
      setLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    if (user && workflowId) {
      fetchWorkflow();
    }
  }, [user, workflowId, fetchWorkflow]);

  const openDecisionModal = (decision: ReviewDecision) => {
    setModalDecision(decision);
    setCommentsInput("");
    setModalValidationError(null);
    setModalApiError(null);
    setModalOpen(true);
  };

  const closeDecisionModal = () => {
    if (submitting) return; // Prevent closing while in flight
    setModalOpen(false);
    setCommentsInput("");
    setModalValidationError(null);
    setModalApiError(null);
  };

  const handleSubmitDecision = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalValidationError(null);
    setModalApiError(null);

    const trimmedComments = commentsInput.trim();

    // Client-side validation: Rejection strictly requires comments
    if (modalDecision === "rejected" && !trimmedComments) {
      setModalValidationError("A comment is mandatory when rejecting a document to explain required revisions.");
      return;
    }

    if (trimmedComments.length > 1000) {
      setModalValidationError("Comments cannot exceed 1000 characters.");
      return;
    }

    setSubmitting(true);
    try {
      const response: WorkflowDecisionResponse = await api.submitWorkflowDecision(workflowId, {
        decision: modalDecision,
        comments: trimmedComments || null,
      });

      // Update unread notifications count
      refreshUnreadCount();

      // Close modal & set success notification
      setModalOpen(false);
      setActionSuccess(
        `Workflow successfully ${response.decision}. Document '${response.document_reference}' status is now '${response.document_status}'.`
      );

      // Refresh workflow data
      await fetchWorkflow();
    } catch (err: any) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setModalApiError("This review workflow has already been decided or cancelled by another session.");
        } else if (err.status === 403) {
          setModalApiError("You are not authorized to record a decision on this workflow.");
        } else if (err.status === 422) {
          setModalApiError(err.message || "Invalid review decision submission.");
        } else {
          setModalApiError(err.message || `API error (${err.status})`);
        }
      } else {
        setModalApiError(err.message || "Failed to record review decision.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading) {
    return (
      <main className="w-full px-4 sm:px-6 lg:px-8 py-12">
        <div className="p-8 text-center text-slate-400 text-sm animate-pulse">
          Loading authentication profile...
        </div>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="w-full px-4 sm:px-6 lg:px-8 py-12">
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 text-center max-w-md mx-auto">
          <ShieldAlert className="w-12 h-12 text-slate-400 mx-auto mb-3" />
          <h2 className="text-lg font-bold text-slate-800 mb-1">Authentication Required</h2>
          <p className="text-xs text-slate-500 mb-6">
            Please sign in to inspect this document review workflow.
          </p>
          <Link
            href="/"
            className="inline-flex items-center justify-center px-4 py-2 text-xs font-semibold text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors shadow-sm"
          >
            Return to Dashboard
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="w-full px-4 sm:px-6 lg:px-8 py-8">
      {/* Top Breadcrumb Navigation */}
      <div className="mb-6 flex items-center justify-between">
        <Link
          href="/workflows/inbox"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Review Inbox
        </Link>

        {workflow && (
          <button
            type="button"
            onClick={fetchWorkflow}
            title="Refresh workflow detail"
            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs text-slate-600 hover:text-slate-900 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} /> Refresh
          </button>
        )}
      </div>

      {/* Global feedback alerts */}
      {actionSuccess && (
        <div
          data-testid="decision-success-banner"
          className="mb-6 p-4 bg-emerald-50 text-emerald-800 text-xs rounded-xl border border-emerald-200 flex items-center justify-between"
        >
          <div className="flex items-center space-x-2.5">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
            <span className="font-medium">{actionSuccess}</span>
          </div>
          <button
            type="button"
            onClick={() => setActionSuccess(null)}
            className="text-emerald-700 hover:text-emerald-900 font-bold ml-2"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {error && (
        <div
          data-testid="workflow-error-banner"
          className="mb-6 p-6 bg-red-50 text-red-900 rounded-xl border border-red-200 text-center max-w-lg mx-auto"
        >
          <AlertTriangle className="w-10 h-10 text-red-500 mx-auto mb-2" />
          <h2 className="text-sm font-bold mb-1">Workflow Access Error</h2>
          <p className="text-xs text-red-700 mb-4">{error}</p>
          <Link
            href="/workflows/inbox"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors"
          >
            Return to Review Inbox
          </Link>
        </div>
      )}

      {/* Loading Skeleton */}
      {loading && !workflow && (
        <div className="space-y-6">
          <div className="p-6 bg-white rounded-xl border border-slate-200 animate-pulse space-y-4">
            <div className="h-6 bg-slate-200 rounded w-1/4" />
            <div className="h-4 bg-slate-200 rounded w-1/2" />
            <div className="h-20 bg-slate-100 rounded" />
          </div>
        </div>
      )}

      {/* Workflow Content */}
      {workflow && (
        <div className="space-y-6">
          {/* Workflow Header Banner */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-2xs p-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-100 pb-5">
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-xs font-bold text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded">
                    {workflow.document.document_reference}
                  </span>
                  <span
                    data-testid="workflow-state-badge"
                    className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full border ${
                      workflow.state === "pending"
                        ? "bg-amber-50 text-amber-700 border-amber-200"
                        : workflow.state === "approved"
                        ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                        : workflow.state === "rejected"
                        ? "bg-rose-50 text-rose-700 border-rose-200"
                        : "bg-slate-100 text-slate-700 border-slate-200"
                    }`}
                  >
                    {workflow.state === "pending" && <Clock className="w-3 h-3" />}
                    {workflow.state === "approved" && <CheckCircle2 className="w-3 h-3" />}
                    {workflow.state === "rejected" && <XCircle className="w-3 h-3" />}
                    {workflow.state === "cancelled" && <AlertCircle className="w-3 h-3" />}
                    <span className="capitalize">{workflow.state}</span>
                  </span>
                  <span className="inline-flex items-center gap-1 text-[11px] text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                    <Building className="w-3 h-3 text-slate-400" />
                    {workflow.document.department}
                  </span>
                  <span className="inline-flex items-center gap-1 text-[11px] text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                    <Tag className="w-3 h-3 text-slate-400" />
                    {workflow.document.classification}
                  </span>
                </div>
                <h1 className="text-xl font-bold text-slate-900 tracking-tight pt-1">
                  {workflow.document.title}
                </h1>
                {workflow.document.subject && (
                  <p className="text-xs text-slate-600 mt-1">{workflow.document.subject}</p>
                )}
              </div>

              {/* Document Lifecycle Badge */}
              <div className="flex sm:flex-col items-start sm:items-end justify-between text-xs text-slate-500">
                <span>Document Status</span>
                <span
                  data-testid="document-status-pill"
                  className="font-semibold capitalize text-slate-800 bg-slate-100 px-2.5 py-1 rounded-md mt-0.5"
                >
                  {workflow.document.status.replace("_", " ")}
                </span>
              </div>
            </div>

            {/* Submitter & Submission Info */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-5 text-xs">
              <div className="space-y-1">
                <span className="text-slate-400 font-medium">Submitted By</span>
                <div className="flex items-center space-x-2">
                  <div className="h-6 w-6 rounded-full bg-slate-100 flex items-center justify-center text-slate-600">
                    <User className="w-3.5 h-3.5" />
                  </div>
                  <div>
                    <span className="font-semibold text-slate-800">
                      {workflow.submitter.full_name}
                    </span>
                    <span className="text-slate-400 ml-1.5">({workflow.submitter.email})</span>
                  </div>
                </div>
              </div>

              <div className="space-y-1">
                <span className="text-slate-400 font-medium">Submitted At</span>
                <div className="flex items-center space-x-1.5 text-slate-700">
                  <Calendar className="w-3.5 h-3.5 text-slate-400" />
                  <span>
                    {new Date(workflow.submitted_at).toLocaleString(undefined, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                  </span>
                </div>
              </div>
            </div>

            {/* Submitter Note */}
            {workflow.submission_comments && (
              <div className="mt-4 p-3.5 bg-slate-50 border border-slate-200/80 rounded-lg text-xs text-slate-700 flex items-start gap-2.5">
                <MessageSquare className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" />
                <div>
                  <span className="font-semibold text-slate-800">Submission Comments: </span>
                  <span className="italic">{workflow.submission_comments}</span>
                </div>
              </div>
            )}
          </div>

          {/* Current Document Version Summary */}
          {workflow.document.current_version && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-2xs p-6">
              <div className="flex flex-wrap items-center justify-between border-b border-slate-100 pb-3 mb-4 gap-2">
                <div className="flex items-center space-x-2">
                  <FileText className="w-4 h-4 text-blue-600" />
                  <h3 className="text-sm font-bold text-slate-900">Document Version Details</h3>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    href={`/documents/${workflow.document_id}`}
                    target="_blank"
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors border border-blue-200"
                    title="Open full document details in new tab"
                  >
                    <ExternalLink className="w-3.5 h-3.5" /> Full Record View
                  </Link>
                  <a
                    href={`http://localhost:8000/api/v1/documents/${workflow.document_id}/versions/${workflow.document.current_version.version_number}/preview${getStoredToken() ? `?token=${encodeURIComponent(getStoredToken()!)}` : ""}`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 rounded-lg transition-colors shadow-2xs"
                    title="Preview file in browser"
                  >
                    <Eye className="w-3.5 h-3.5 text-slate-500" /> Preview
                  </a>
                  <a
                    href={`http://localhost:8000/api/v1/documents/${workflow.document_id}/versions/${workflow.document.current_version.version_number}/download${getStoredToken() ? `?token=${encodeURIComponent(getStoredToken()!)}` : ""}`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 rounded-lg transition-colors shadow-2xs"
                    title="Download original file"
                  >
                    <Download className="w-3.5 h-3.5 text-slate-500" /> Download
                  </a>
                  <span className="text-xs font-mono font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                    Version {workflow.document.current_version.version_number}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                <div>
                  <span className="text-slate-400 block mb-0.5">Filename</span>
                  <span className="font-medium text-slate-800 break-all font-mono">
                    {workflow.document.current_version.original_filename}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block mb-0.5">File Size</span>
                  <span className="font-medium text-slate-800">
                    {formatBytes(workflow.document.current_version.file_size_bytes)}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block mb-0.5">MIME Type</span>
                  <span className="font-medium text-slate-800 font-mono">
                    {workflow.document.current_version.mime_type}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block mb-0.5">OCR Extraction</span>
                  <span className="inline-flex items-center gap-1 font-medium capitalize text-slate-700">
                    {workflow.document.current_version.extraction_status === "completed" && (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                    )}
                    {workflow.document.current_version.extraction_status === "processing" && (
                      <Clock className="w-3.5 h-3.5 text-blue-500" />
                    )}
                    {workflow.document.current_version.extraction_status === "failed" && (
                      <XCircle className="w-3.5 h-3.5 text-rose-500" />
                    )}
                    {workflow.document.current_version.extraction_status}
                  </span>
                </div>
              </div>

              {/* OCR Extracted Text Inspector for Approver */}
              <div className="mt-5 pt-4 border-t border-slate-100">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                    <FileText className="w-3.5 h-3.5 text-blue-600" />
                    OCR Extracted Text & Content
                  </span>
                  {workflow.document.current_version.extracted_text && (
                    <button
                      type="button"
                      onClick={() => setShowOcrText(!showOcrText)}
                      className="text-xs text-blue-600 hover:text-blue-800 font-semibold inline-flex items-center gap-1"
                    >
                      {showOcrText ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                      {showOcrText ? "Collapse Text" : "Expand Text"}
                    </button>
                  )}
                </div>

                {workflow.document.current_version.extracted_text ? (
                  showOcrText && (
                    <div className="bg-slate-50 border border-slate-200 rounded-lg p-3.5 max-h-64 overflow-y-auto font-mono text-xs text-slate-800 whitespace-pre-wrap leading-relaxed shadow-inner">
                      {workflow.document.current_version.extracted_text}
                    </div>
                  )
                ) : (
                  <p className="text-xs text-slate-400 italic">
                    No extracted text available for this version yet.
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Approver Decision Section */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-2xs p-6">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
              <div className="flex items-center space-x-2">
                <FileCheck2 className="w-4 h-4 text-blue-600" />
                <h3 className="text-sm font-bold text-slate-900">Review Decision</h3>
              </div>
            </div>

            {/* Check if pending and current user is the assigned approver */}
            {workflow.state === "pending" ? (
              <div className="space-y-4">
                <div className="bg-amber-50/60 border border-amber-200/70 rounded-lg p-4 text-xs text-amber-900 flex items-start gap-3">
                  <Clock className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="font-semibold">Review Pending</p>
                    <p className="text-amber-700 mt-0.5">
                      This document is waiting for your review decision. Approving will transition the document to <strong className="text-emerald-700">active</strong> status. Rejecting will return the document to <strong className="text-rose-700">draft</strong> and requires written justification.
                    </p>
                  </div>
                </div>

                {user.role === "approver" ? (
                  <div className="flex items-center gap-3 pt-2">
                    <button
                      type="button"
                      data-testid="approve-button"
                      onClick={() => openDecisionModal("approved")}
                      className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-1 transition-colors shadow-sm"
                    >
                      <CheckCircle2 className="w-4 h-4" />
                      Approve Document
                    </button>

                    <button
                      type="button"
                      data-testid="reject-button"
                      onClick={() => openDecisionModal("rejected")}
                      className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-500 focus:ring-offset-1 transition-colors shadow-sm"
                    >
                      <XCircle className="w-4 h-4" />
                      Reject Document
                    </button>
                  </div>
                ) : (
                  <p className="text-xs text-slate-500 italic">
                    You do not have the approver role to record decisions on this review.
                  </p>
                )}
              </div>
            ) : (
              /* Already decided / closed workflow */
              <div className="space-y-4">
                <div
                  data-testid="workflow-decided-banner"
                  className={`p-4 rounded-lg border text-xs ${
                    workflow.state === "approved"
                      ? "bg-emerald-50 border-emerald-200 text-emerald-900"
                      : workflow.state === "rejected"
                      ? "bg-rose-50 border-rose-200 text-rose-900"
                      : "bg-slate-50 border-slate-200 text-slate-800"
                  }`}
                >
                  <div className="flex items-start gap-2.5">
                    {workflow.state === "approved" && (
                      <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 flex-shrink-0" />
                    )}
                    {workflow.state === "rejected" && (
                      <XCircle className="w-4 h-4 text-rose-600 mt-0.5 flex-shrink-0" />
                    )}
                    {workflow.state === "cancelled" && (
                      <AlertCircle className="w-4 h-4 text-slate-500 mt-0.5 flex-shrink-0" />
                    )}
                    <div className="space-y-1">
                      <p className="font-semibold capitalize">
                        Workflow {workflow.state}
                      </p>
                      {/* Check assignments for decided comments */}
                      {workflow.assignments.map((assignment) => (
                        <div key={assignment.id} className="pt-1 text-slate-700">
                          {assignment.decided_at && (
                            <p className="text-[11px] text-slate-500">
                              Decided on:{" "}
                              {new Date(assignment.decided_at).toLocaleString(undefined, {
                                dateStyle: "medium",
                                timeStyle: "short",
                              })}
                            </p>
                          )}
                          {assignment.decision_comments && (
                            <div className="mt-2 p-2.5 bg-white/80 rounded border border-slate-200 text-xs">
                              <span className="font-medium text-slate-800">Decision comments: </span>
                              <span>{assignment.decision_comments}</span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Decision Confirmation Modal */}
      {modalOpen && (
        <div
          data-testid="decision-modal"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 animate-in fade-in duration-150"
        >
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6 border border-slate-200">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center space-x-2">
                {modalDecision === "approved" ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                ) : (
                  <XCircle className="w-5 h-5 text-rose-600" />
                )}
                <h3 className="text-base font-bold text-slate-900 capitalize">
                  {modalDecision === "approved" ? "Approve Document" : "Reject Document"}
                </h3>
              </div>
              <button
                type="button"
                onClick={closeDecisionModal}
                disabled={submitting}
                className="text-slate-400 hover:text-slate-600 disabled:opacity-50"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSubmitDecision} className="mt-4 space-y-4">
              <p className="text-xs text-slate-600 leading-relaxed">
                {modalDecision === "approved"
                  ? "Are you sure you want to approve this document? This will activate the document and make it active in the repository."
                  : "Are you sure you want to reject this document? This will return the document to draft status so the author can address your feedback. A comment is mandatory."}
              </p>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {modalDecision === "approved" ? "Review Comments (Optional)" : "Rejection Reason (Required)"}
                </label>
                <textarea
                  data-testid="decision-comments-input"
                  value={commentsInput}
                  onChange={(e) => setCommentsInput(e.target.value)}
                  placeholder={
                    modalDecision === "approved"
                      ? "Add any optional notes or feedback regarding this approval..."
                      : "Explain why this document is rejected and what changes are required before resubmission..."
                  }
                  rows={4}
                  maxLength={1000}
                  className="w-full text-xs p-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                  disabled={submitting}
                />
                <div className="flex justify-end text-[10px] text-slate-400 mt-1">
                  {commentsInput.length} / 1000 characters
                </div>
              </div>

              {/* Validation Error */}
              {modalValidationError && (
                <div
                  data-testid="modal-validation-error"
                  className="p-3 bg-rose-50 text-rose-800 rounded-lg text-xs border border-rose-200 flex items-center space-x-2"
                >
                  <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                  <span>{modalValidationError}</span>
                </div>
              )}

              {/* API Error */}
              {modalApiError && (
                <div
                  data-testid="modal-api-error"
                  className="p-3 bg-red-50 text-red-800 rounded-lg text-xs border border-red-200 flex items-center space-x-2"
                >
                  <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
                  <span>{modalApiError}</span>
                </div>
              )}

              {/* Buttons */}
              <div className="flex justify-end space-x-2.5 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={closeDecisionModal}
                  disabled={submitting}
                  className="px-3.5 py-1.5 text-xs text-slate-600 hover:text-slate-800 rounded-lg hover:bg-slate-100 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  data-testid="submit-decision-button"
                  disabled={submitting}
                  className={`inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white rounded-lg shadow-sm transition-colors disabled:opacity-50 ${
                    modalDecision === "approved"
                      ? "bg-emerald-600 hover:bg-emerald-700"
                      : "bg-rose-600 hover:bg-rose-700"
                  }`}
                >
                  {submitting ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      Submitting...
                    </>
                  ) : modalDecision === "approved" ? (
                    "Confirm Approval"
                  ) : (
                    "Confirm Rejection"
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
