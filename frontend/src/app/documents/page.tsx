"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { useNotificationContext } from "@/context/NotificationContext";
import { api } from "@/lib/api";
import {
  DocumentSummaryResponse,
  PaginatedDocumentResponse,
  WorkflowSubmissionResponse,
} from "@/types/document";
import { SubmitForReviewModal } from "@/components/SubmitForReviewModal";
import {
  FileText,
  Search,
  Filter,
  Building,
  Tag,
  Clock,
  CheckCircle2,
  Calendar,
  Layers,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Send,
  ShieldAlert,
  ArrowRight,
  Inbox,
  AlertTriangle,
  Upload,
  X,
} from "lucide-react";

export default function DocumentsPage() {
  const { user, loading: authLoading } = useAuth();
  const { refreshUnreadCount } = useNotificationContext();

  const [documents, setDocuments] = useState<DocumentSummaryResponse[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Upload modal state
  const [showUploadModal, setShowUploadModal] = useState<boolean>(false);
  const [uploadTitle, setUploadTitle] = useState<string>("");
  const [uploadSubject, setUploadSubject] = useState<string>("");
  const [uploadClassification, setUploadClassification] = useState<string>("General");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Quick submit modal state
  const [submittingDoc, setSubmittingDoc] = useState<DocumentSummaryResponse | null>(null);

  const fetchDocuments = useCallback(
    async (page: number, search: string, status: string) => {
      if (!user) return;
      setLoading(true);
      setError(null);
      try {
        const res: PaginatedDocumentResponse = await api.getDocuments(
          page,
          10,
          search || undefined,
          status || undefined
        );
        setDocuments(res.items);
        setTotal(res.total);
        setTotalPages(res.total_pages || 1);
        setCurrentPage(res.page);
      } catch (err: any) {
        setError(err.message || "Failed to load documents repository.");
      } finally {
        setLoading(false);
      }
    },
    [user]
  );

  useEffect(() => {
    if (user) {
      fetchDocuments(currentPage, searchTerm, statusFilter);
    }
  }, [user, currentPage, searchTerm, statusFilter, fetchDocuments]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setCurrentPage(1);
    fetchDocuments(1, searchTerm, statusFilter);
  };

  const handleSubmissionSuccess = (result: WorkflowSubmissionResponse) => {
    refreshUnreadCount();
    setSuccessMsg(
      `Document '${result.document_reference}' submitted for review. Status transitioned to '${result.document_status}'.`
    );
    setTimeout(() => setSuccessMsg(null), 4000);
    fetchDocuments(currentPage, searchTerm, statusFilter);
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
            Please sign in to access the document repository.
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

  const isUserEligibleForSubmission = (doc: DocumentSummaryResponse): boolean => {
    if (doc.status !== "draft") return false;
    if (user.role === "admin" || user.role === "records_officer") return true;
    if (user.role === "department_user") {
      const userDept = (user.department || "").trim().toLowerCase();
      const docDept = (doc.department || "").trim().toLowerCase();
      return !!userDept && userDept === docDept;
    }
    return false;
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadTitle.trim() || !uploadFile) {
      setUploadError("Please provide a title and select a valid document file.");
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const formData = new FormData();
      formData.append("title", uploadTitle.trim());
      if (uploadSubject.trim()) formData.append("subject", uploadSubject.trim());
      formData.append("classification", uploadClassification);
      formData.append("file", uploadFile);

      const res = await api.uploadDocument(formData);
      setShowUploadModal(false);
      setUploadTitle("");
      setUploadSubject("");
      setUploadFile(null);
      setSuccessMsg(`Document '${res.document_reference}' created successfully with Version 1.`);
      setTimeout(() => setSuccessMsg(null), 5000);
      fetchDocuments(1, searchTerm, statusFilter);
    } catch (err: any) {
      setUploadError(err.message || "Document upload failed. Ensure the format is PDF, JPEG, PNG, or TIFF (≤25MB).");
    } finally {
      setUploading(false);
    }
  };

  return (
    <main className="w-full px-4 sm:px-6 lg:px-8 py-8">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6 pb-6 border-b border-slate-200">
        <div>
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Documents Repository</h1>
            <span className="bg-blue-100 text-blue-700 text-xs px-2.5 py-0.5 rounded-full font-semibold">
              {total} {total === 1 ? "document" : "documents"}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Browse, manage, and submit repository documents for workflow review.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowUploadModal(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-xl transition-colors shadow-sm"
          >
            <Upload className="w-3.5 h-3.5" />
            Upload Document
          </button>
          <button
            type="button"
            onClick={() => fetchDocuments(currentPage, searchTerm, statusFilter)}
            title="Refresh repository"
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 rounded-xl border border-slate-300 transition-colors shadow-2xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Success Banner */}
      {successMsg && (
        <div className="mb-6 p-4 bg-emerald-50 text-emerald-800 text-xs rounded-xl border border-emerald-200 flex items-center space-x-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 text-red-800 text-xs rounded-xl border border-red-200 flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Filters & Search */}
      <div className="mb-6 flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
        <form onSubmit={handleSearchSubmit} className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by title, reference, or subject..."
            className="w-full pl-9 pr-4 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none bg-white"
          />
        </form>

        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setCurrentPage(1);
            }}
            className="text-xs border border-slate-300 rounded-lg py-2 px-3 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none bg-white text-slate-700"
          >
            <option value="">All Statuses</option>
            <option value="draft">Draft</option>
            <option value="under_review">Under Review</option>
            <option value="active">Active</option>
            <option value="archived">Archived</option>
          </select>
        </div>
      </div>

      {/* Loading Skeleton */}
      {loading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="p-6 rounded-xl border border-slate-200 bg-white animate-pulse">
              <div className="space-y-3">
                <div className="h-4 bg-slate-200 rounded w-1/4" />
                <div className="h-3 bg-slate-200 rounded w-1/2" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && documents.length === 0 && (
        <div className="bg-white rounded-xl shadow-xs border border-slate-200 p-12 text-center">
          <Inbox className="w-12 h-12 text-slate-300 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-slate-800">No documents found</h3>
          <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
            {searchTerm || statusFilter
              ? "No documents match the specified search query or status filter."
              : "No documents are currently registered in your department or access scope."}
          </p>
        </div>
      )}

      {/* Documents List */}
      {!loading && documents.length > 0 && (
        <div className="space-y-4">
          {documents.map((doc) => {
            const isEligible = isUserEligibleForSubmission(doc);

            return (
              <div
                key={doc.id}
                data-testid={`document-item-${doc.id}`}
                className="p-5 sm:p-6 rounded-xl border border-slate-200 bg-white shadow-2xs hover:border-slate-300 transition-all duration-150"
              >
                <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                  {/* Left Metadata */}
                  <div className="space-y-2 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-xs font-bold text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded">
                        {doc.document_reference}
                      </span>
                      <span
                        className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded border capitalize ${
                          doc.status === "draft"
                            ? "bg-slate-100 text-slate-700 border-slate-200"
                            : doc.status === "under_review"
                            ? "bg-amber-50 text-amber-700 border-amber-200"
                            : doc.status === "active"
                            ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                            : "bg-slate-100 text-slate-600 border-slate-200"
                        }`}
                      >
                        {doc.status === "under_review" && <Clock className="w-3 h-3 text-amber-600" />}
                        {doc.status === "active" && <CheckCircle2 className="w-3 h-3 text-emerald-600" />}
                        {doc.status === "draft" && <FileText className="w-3 h-3 text-slate-500" />}
                        <span>{doc.status.replace("_", " ")}</span>
                      </span>
                      <span className="inline-flex items-center gap-1 text-[11px] text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                        <Building className="w-3 h-3 text-slate-400" />
                        {doc.department}
                      </span>
                      <span className="inline-flex items-center gap-1 text-[11px] text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                        <Tag className="w-3 h-3 text-slate-400" />
                        {doc.classification}
                      </span>
                    </div>

                    <h2 className="text-base font-bold text-slate-900 tracking-tight">
                      {doc.title}
                    </h2>

                    {doc.subject && (
                      <p className="text-xs text-slate-600 line-clamp-2">{doc.subject}</p>
                    )}

                    <div className="flex items-center gap-4 text-xs text-slate-400 pt-1">
                      <div className="flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5 text-slate-400" />
                        <span>{new Date(doc.created_at).toLocaleDateString()}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Layers className="w-3.5 h-3.5 text-slate-400" />
                        <span>{doc.version_count} {doc.version_count === 1 ? "version" : "versions"}</span>
                      </div>
                    </div>
                  </div>

                  {/* Right Actions */}
                  <div className="flex items-center gap-2 pt-2 md:pt-0">
                    {isEligible && (
                      <button
                        type="button"
                        data-testid={`quick-submit-btn-${doc.id}`}
                        onClick={() => setSubmittingDoc(doc)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors"
                      >
                        <Send className="w-3 h-3" />
                        Submit for Review
                      </button>
                    )}

                    <Link
                      href={`/documents/${doc.id}`}
                      className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 rounded-lg transition-colors shadow-2xs"
                    >
                      <span>View Details</span>
                      <ArrowRight className="w-3 h-3 text-slate-400" />
                    </Link>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination Footer */}
      {!loading && totalPages > 1 && (
        <div className="mt-6 flex items-center justify-between border-t border-slate-200 pt-4 text-xs text-slate-500">
          <span>
            Showing page <strong className="text-slate-800">{currentPage}</strong> of{" "}
            <strong className="text-slate-800">{totalPages}</strong> ({total} total)
          </span>

          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage <= 1}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-3.5 h-3.5" /> Previous
            </button>
            <button
              type="button"
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage >= totalPages}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Next <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Document Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full p-6 border border-slate-200">
            <div className="flex items-center justify-between pb-3 mb-4 border-b border-slate-100">
              <div className="flex items-center space-x-2 text-slate-900">
                <Upload className="w-5 h-5 text-blue-600" />
                <h3 className="text-base font-bold">Upload New Document</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowUploadModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg hover:bg-slate-100"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleUploadSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Document Title <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  placeholder="e.g. Master Services Agreement 2026"
                  className="w-full text-xs p-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Subject / Summary
                </label>
                <input
                  type="text"
                  value={uploadSubject}
                  onChange={(e) => setUploadSubject(e.target.value)}
                  placeholder="Brief description or record summary"
                  className="w-full text-xs p-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Classification Category
                </label>
                <select
                  value={uploadClassification}
                  onChange={(e) => setUploadClassification(e.target.value)}
                  className="w-full text-xs p-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none bg-white text-slate-700"
                >
                  <option value="General">General</option>
                  <option value="Contract">Contract</option>
                  <option value="Policy">Policy</option>
                  <option value="Invoice">Invoice</option>
                  <option value="Personnel">Personnel</option>
                  <option value="Financial">Financial</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  File Binary <span className="text-rose-500">*</span>
                </label>
                <input
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg,.tiff"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  className="w-full text-xs p-2 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                  required
                />
                <p className="text-[11px] text-slate-400 mt-1">
                  Supported formats: PDF, JPEG, PNG, TIFF. Max file size: 25 MiB. Magic bytes validated.
                </p>
              </div>

              {uploadError && (
                <div className="p-3 bg-red-50 text-red-700 rounded-xl text-xs border border-red-200">
                  {uploadError}
                </div>
              )}

              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowUploadModal(false)}
                  className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-800 rounded-xl hover:bg-slate-100"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={uploading}
                  className="px-5 py-2 text-xs font-semibold text-white bg-blue-600 rounded-xl hover:bg-blue-700 shadow-sm transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
                >
                  <Upload className="w-3.5 h-3.5" />
                  {uploading ? "Uploading & Staging..." : "Upload Document"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Quick Submit Modal */}
      {submittingDoc && (
        <SubmitForReviewModal
          isOpen={!!submittingDoc}
          onClose={() => setSubmittingDoc(null)}
          document={submittingDoc}
          onSuccess={handleSubmissionSuccess}
        />
      )}
    </main>
  );
}
