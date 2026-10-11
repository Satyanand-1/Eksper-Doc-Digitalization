"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { useNotificationContext } from "@/context/NotificationContext";
import { api, ApiError, getStoredToken } from "@/lib/api";
import {
  DocumentDetailResponse,
  DocumentVersionResponse,
  WorkflowSubmissionResponse,
} from "@/types/document";
import { SubmitForReviewModal } from "@/components/SubmitForReviewModal";
import { WorkflowHistoryList } from "@/components/WorkflowHistoryList";
import {
  FileText,
  Building,
  Tag,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  RefreshCw,
  Send,
  ShieldAlert,
  User,
  Calendar,
  Lock,
  Layers,
  Check,
  X,
  Eye,
  Download,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

function formatBytes(bytes?: number): string {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

export default function DocumentDetailPage() {
  const params = useParams();
  const documentId = params?.documentId as string;

  const { user, loading: authLoading } = useAuth();
  const { refreshUnreadCount } = useNotificationContext();

  const [document, setDocument] = useState<DocumentDetailResponse | null>(null);
  const [latestVersion, setLatestVersion] = useState<DocumentVersionResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Submission modal state
  const [isSubmitModalOpen, setIsSubmitModalOpen] = useState<boolean>(false);
  const [historyRefreshKey, setHistoryRefreshKey] = useState<number>(0);
  const [showOcrText, setShowOcrText] = useState<boolean>(true);

  const fetchDocumentData = useCallback(async () => {
    if (!documentId) return;
    setLoading(true);
    setError(null);
    try {
      const [docData, versionsData] = await Promise.all([
        api.getDocument(documentId),
        api.getDocumentVersions(documentId).catch(() => []),
      ]);
      setDocument(docData);
      if (versionsData.length > 0) {
        // Find latest version by version_number
        const sorted = [...versionsData].sort((a, b) => b.version_number - a.version_number);
        setLatestVersion(sorted[0]);
      }
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 404) {
        setError("Document not found or you are not authorized to view its metadata.");
      } else {
        setError(err.message || "Failed to load document details.");
      }
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    if (user && documentId) {
      fetchDocumentData();
    }
  }, [user, documentId, fetchDocumentData]);

  const handleSubmissionSuccess = (result: WorkflowSubmissionResponse) => {
    // 1. Optimistically or freshly update document status
    setDocument((prev) => (prev ? { ...prev, status: result.document_status } : null));

    // 2. Refresh unread notifications
    refreshUnreadCount();

    // 3. Trigger history reload
    setHistoryRefreshKey((prev) => prev + 1);

    // 4. Show success message
    setActionSuccess(
      `Document '${result.document_reference}' has been successfully submitted for review. Current status is now '${result.document_status}'.`
    );

    // 5. Refetch document data
    fetchDocumentData();
  };

  // Evaluate submission eligibility based on backend authorization rules
  const canUserSubmit = (): { allowed: boolean; reason: string } => {
    if (!user) {
      return { allowed: false, reason: "Authentication required to submit documents." };
    }
    if (!document) {
      return { allowed: false, reason: "Document details not loaded." };
    }
    if (document.status !== "draft") {
      return {
        allowed: false,
        reason: `Document is in '${document.status}' status. Only draft documents can be submitted for review.`,
      };
    }

    const userRole = user.role;
    if (userRole === "admin" || userRole === "records_officer") {
      return { allowed: true, reason: "Administrative submission permitted." };
    }

    if (userRole === "department_user") {
      const userDept = (user.department || "").trim().toLowerCase();
      const docDept = (document.department || "").trim().toLowerCase();
      if (userDept && userDept === docDept) {
        return { allowed: true, reason: "Department user submission permitted." };
      }
      return {
        allowed: false,
        reason: `Department users in '${user.department || "unassigned"}' cannot submit documents for '${document.department}'.`,
      };
    }

    return {
      allowed: false,
      reason: `Role '${userRole.replace("_", " ")}' does not have document review submission rights.`,
    };
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
            Please sign in to inspect document metadata and submission options.
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

  const submissionEligibility = canUserSubmit();

  return (
    <main className="w-full px-4 sm:px-6 lg:px-8 py-8">
      {/* Breadcrumb Navigation */}
      <div className="mb-6 flex items-center justify-between">
        <Link
          href="/documents"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Documents
        </Link>

        {document && (
          <button
            type="button"
            onClick={fetchDocumentData}
            title="Refresh document detail"
            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs text-slate-600 hover:text-slate-900 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} /> Refresh
          </button>
        )}
      </div>

      {/* Global Feedback Banners */}
      {actionSuccess && (
        <div
          data-testid="submission-success-banner"
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
          data-testid="document-error-banner"
          className="mb-6 p-6 bg-red-50 text-red-900 rounded-xl border border-red-200 text-center max-w-lg mx-auto"
        >
          <AlertTriangle className="w-10 h-10 text-red-500 mx-auto mb-2" />
          <h2 className="text-sm font-bold mb-1">Document Unavailable</h2>
          <p className="text-xs text-red-700 mb-4">{error}</p>
          <Link
            href="/documents"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors"
          >
            Return to Documents Repository
          </Link>
        </div>
      )}

      {/* Loading Skeleton */}
      {loading && !document && (
        <div className="space-y-6">
          <div className="p-6 bg-white rounded-xl border border-slate-200 animate-pulse space-y-4">
            <div className="h-6 bg-slate-200 rounded w-1/4" />
            <div className="h-4 bg-slate-200 rounded w-1/2" />
            <div className="h-24 bg-slate-100 rounded" />
          </div>
        </div>
      )}

      {/* Main Document Details & Actions */}
      {document && (
        <div className="space-y-6">
          {/* Document Header Card */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-2xs p-6">
            <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4 border-b border-slate-100 pb-5">
              <div className="space-y-2 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-xs font-bold text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded">
                    {document.document_reference}
                  </span>
                  <span
                    data-testid="document-status-pill"
                    className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full border capitalize ${
                      document.status === "draft"
                        ? "bg-slate-100 text-slate-700 border-slate-200"
                        : document.status === "under_review"
                        ? "bg-amber-50 text-amber-700 border-amber-200"
                        : document.status === "active"
                        ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                        : "bg-slate-100 text-slate-600 border-slate-200"
                    }`}
                  >
                    {document.status === "under_review" && <Clock className="w-3 h-3 text-amber-600" />}
                    {document.status === "active" && <CheckCircle2 className="w-3 h-3 text-emerald-600" />}
                    {document.status === "draft" && <FileText className="w-3 h-3 text-slate-500" />}
                    <span>{document.status.replace("_", " ")}</span>
                  </span>
                  <span className="inline-flex items-center gap-1 text-[11px] text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                    <Building className="w-3 h-3 text-slate-400" />
                    {document.department}
                  </span>
                  <span className="inline-flex items-center gap-1 text-[11px] text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                    <Tag className="w-3 h-3 text-slate-400" />
                    {document.classification}
                  </span>
                </div>

                <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                  {document.title}
                </h1>

                {document.subject && (
                  <p className="text-xs text-slate-600 leading-relaxed max-w-2xl">
                    {document.subject}
                  </p>
                )}
              </div>

              {/* Action Area: Submit for Review */}
              <div className="flex flex-col items-end gap-2 pt-2 md:pt-0">
                {submissionEligibility.allowed ? (
                  <button
                    type="button"
                    data-testid="submit-for-review-button"
                    onClick={() => setIsSubmitModalOpen(true)}
                    className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 transition-colors shadow-sm"
                  >
                    <Send className="w-3.5 h-3.5" />
                    Submit for Review
                  </button>
                ) : (
                  <div
                    data-testid="submission-ineligible-notice"
                    className="p-3 bg-slate-50 rounded-lg border border-slate-200 text-right max-w-xs"
                  >
                    <div className="flex items-center justify-end gap-1 text-[11px] font-semibold text-slate-600">
                      <Lock className="w-3 h-3 text-slate-400" />
                      <span>Submission Unavailable</span>
                    </div>
                    <p className="text-[10px] text-slate-500 mt-1 leading-snug">
                      {submissionEligibility.reason}
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Document Metadata Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 pt-5 text-xs">
              <div className="space-y-1">
                <span className="text-slate-400 font-medium">Author / Creator</span>
                <div className="flex items-center space-x-2 text-slate-700">
                  <User className="w-3.5 h-3.5 text-slate-400" />
                  <span>{document.creator?.full_name || "System Record"}</span>
                  {document.creator?.email && (
                    <span className="text-slate-400">({document.creator.email})</span>
                  )}
                </div>
              </div>

              <div className="space-y-1">
                <span className="text-slate-400 font-medium">Created Timestamp</span>
                <div className="flex items-center space-x-1.5 text-slate-700">
                  <Calendar className="w-3.5 h-3.5 text-slate-400" />
                  <span>
                    {new Date(document.created_at).toLocaleString(undefined, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                  </span>
                </div>
              </div>

              <div className="space-y-1">
                <span className="text-slate-400 font-medium">Registered Versions</span>
                <div className="flex items-center space-x-1.5 text-slate-700">
                  <Layers className="w-3.5 h-3.5 text-slate-400" />
                  <span>{document.version_count} registered {document.version_count === 1 ? "version" : "versions"}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Current Version Card */}
          {latestVersion && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-2xs p-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3 mb-4">
                <div className="flex items-center space-x-2">
                  <FileText className="w-4 h-4 text-blue-600" />
                  <h3 className="text-sm font-bold text-slate-900">Current Version (v{latestVersion.version_number})</h3>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <a
                    href={`http://localhost:8000/api/v1/documents/${document.id}/versions/${latestVersion.version_number}/preview${getStoredToken() ? `?token=${encodeURIComponent(getStoredToken()!)}` : ""}`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 rounded-lg transition-colors shadow-2xs"
                    title="Preview file in browser"
                  >
                    <Eye className="w-3.5 h-3.5 text-slate-500" /> Preview PDF
                  </a>
                  <a
                    href={`http://localhost:8000/api/v1/documents/${document.id}/versions/${latestVersion.version_number}/download${getStoredToken() ? `?token=${encodeURIComponent(getStoredToken()!)}` : ""}`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 rounded-lg transition-colors shadow-2xs"
                    title="Download original file"
                  >
                    <Download className="w-3.5 h-3.5 text-slate-500" /> Download
                  </a>
                  <span className="text-xs font-mono text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                    {latestVersion.mime_type}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
                <div>
                  <span className="text-slate-400 block mb-0.5">Filename</span>
                  <span className="font-medium text-slate-800 break-all font-mono">
                    {latestVersion.original_filename}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block mb-0.5">File Size</span>
                  <span className="font-medium text-slate-800">
                    {formatBytes(latestVersion.file_size_bytes)}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block mb-0.5">OCR Extraction</span>
                  <span className="inline-flex items-center gap-1 font-medium capitalize text-slate-700">
                    {latestVersion.extraction_status === "completed" && (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                    )}
                    {latestVersion.extraction_status === "processing" && (
                      <Clock className="w-3.5 h-3.5 text-blue-500" />
                    )}
                    {latestVersion.extraction_status === "failed" && (
                      <XCircle className="w-3.5 h-3.5 text-rose-500" />
                    )}
                    {latestVersion.extraction_status}
                  </span>
                </div>
              </div>

              {/* OCR Extracted Text Inspector */}
              <div className="mt-5 pt-4 border-t border-slate-100">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                    <FileText className="w-3.5 h-3.5 text-blue-600" />
                    OCR Extracted Text & Content
                  </span>
                  {latestVersion.extracted_text && (
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

                {latestVersion.extracted_text ? (
                  showOcrText && (
                    <div className="mt-2 p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs font-mono text-slate-700 max-h-60 overflow-y-auto whitespace-pre-wrap leading-relaxed select-text">
                      {latestVersion.extracted_text}
                    </div>
                  )
                ) : (
                  <p className="text-xs text-slate-400 italic">
                    {latestVersion.extraction_status === "completed"
                      ? "No text content detected in this file."
                      : `OCR text extraction is currently ${latestVersion.extraction_status}.`}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Workflow Review History Section */}
          <WorkflowHistoryList
            documentId={document.id}
            refreshTrigger={historyRefreshKey}
          />

          {/* Submission Modal */}
          <SubmitForReviewModal
            isOpen={isSubmitModalOpen}
            onClose={() => setIsSubmitModalOpen(false)}
            document={document}
            versionInfo={
              latestVersion
                ? {
                    version_number: latestVersion.version_number,
                    original_filename: latestVersion.original_filename,
                    file_size_bytes: latestVersion.file_size_bytes,
                    mime_type: latestVersion.mime_type,
                  }
                : null
            }
            onSuccess={handleSubmissionSuccess}
          />
        </div>
      )}
    </main>
  );
}
