"use client";

import React, { useState, useEffect } from "react";
import { api, ApiError } from "@/lib/api";
import { DocumentDetailResponse, DocumentSummaryResponse, WorkflowSubmissionResponse } from "@/types/document";
import { EligibleApprover } from "@/types/user";
import {
  FileText,
  Send,
  X,
  AlertCircle,
  AlertTriangle,
  Building,
  Tag,
  ShieldAlert,
  Clock,
  RefreshCw,
  CheckCircle2,
  Search,
  UserCheck,
  UserX,
  User,
} from "lucide-react";

interface SubmitForReviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  document: DocumentDetailResponse | DocumentSummaryResponse;
  versionInfo?: {
    version_number: number;
    original_filename: string;
    file_size_bytes?: number;
    mime_type?: string;
  } | null;
  onSuccess: (result: WorkflowSubmissionResponse) => void;
}

function formatBytes(bytes?: number): string {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

export function SubmitForReviewModal({
  isOpen,
  onClose,
  document,
  versionInfo,
  onSuccess,
}: SubmitForReviewModalProps) {
  const [approvers, setApprovers] = useState<EligibleApprover[]>([]);
  const [selectedApprover, setSelectedApprover] = useState<EligibleApprover | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [loadingApprovers, setLoadingApprovers] = useState<boolean>(false);
  const [directoryError, setDirectoryError] = useState<string | null>(null);

  const [comments, setComments] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  // Clear selections when document changes or modal opens
  useEffect(() => {
    if (isOpen) {
      setSelectedApprover(null);
      setSearchQuery("");
      setValidationError(null);
      setApiError(null);
      setComments("");
    }
  }, [isOpen, document?.id]);

  // Fetch approvers with debounced search query and stale request protection
  useEffect(() => {
    if (!isOpen || !document?.id) return;

    let isCurrent = true;
    setLoadingApprovers(true);
    setDirectoryError(null);

    const timer = setTimeout(async () => {
      try {
        const data = await api.getEligibleApprovers({
          document_id: document.id,
          q: searchQuery.trim() || undefined,
        });
        if (isCurrent) {
          setApprovers(data);
        }
      } catch (err: any) {
        if (isCurrent) {
          if (err instanceof ApiError && err.status === 403) {
            setDirectoryError("You are not authorized to query the approver directory.");
          } else if (err instanceof ApiError && err.status === 404) {
            setDirectoryError("Document not found or access denied.");
          } else {
            setDirectoryError(err.message || "Failed to load eligible approvers.");
          }
        }
      } finally {
        if (isCurrent) {
          setLoadingApprovers(false);
        }
      }
    }, 200);

    return () => {
      isCurrent = false;
      clearTimeout(timer);
    };
  }, [isOpen, document?.id, searchQuery]);

  if (!isOpen) return null;

  const handleClose = () => {
    if (submitting) return; // Prevent closing while in flight
    setSelectedApprover(null);
    setSearchQuery("");
    setComments("");
    setValidationError(null);
    setApiError(null);
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setValidationError(null);
    setApiError(null);

    if (!selectedApprover) {
      setValidationError("Please select an eligible approver from the directory before submitting.");
      return;
    }

    const cleanComments = comments.trim();
    if (cleanComments.length > 1000) {
      setValidationError("Submission comments cannot exceed 1000 characters.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await api.submitForReview(document.id, {
        approver_id: selectedApprover.id,
        comments: cleanComments || null,
      });

      handleClose();
      onSuccess(response);
    } catch (err: any) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setApiError(
            err.message ||
              "Document is no longer eligible for submission or an active review workflow already exists."
          );
        } else if (err.status === 400) {
          setApiError(
            err.message ||
              "Invalid approver: Ensure approver holds 'approver' role in the same department and is not the submitter."
          );
        } else if (err.status === 403) {
          setApiError(err.message || "You are not authorized to submit this document for review.");
        } else if (err.status === 404) {
          setApiError("Document not found or access denied.");
        } else if (err.status === 422) {
          setApiError(err.message || "Invalid submission request format.");
        } else {
          setApiError(err.message || `Server error (${err.status})`);
        }
      } else {
        setApiError(err.message || "Failed to submit document for review.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      data-testid="submit-for-review-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 animate-in fade-in duration-150"
    >
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6 border border-slate-200 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center space-x-2 text-slate-900">
            <Send className="w-5 h-5 text-blue-600" />
            <h3 className="text-base font-bold">Submit Document for Review</h3>
          </div>
          <button
            type="button"
            onClick={handleClose}
            disabled={submitting}
            className="text-slate-400 hover:text-slate-600 disabled:opacity-50"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Document Metadata Summary Box */}
        <div className="mt-4 p-3.5 bg-slate-50 border border-slate-200/80 rounded-lg space-y-2 text-xs">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono font-bold text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded">
              {document.document_reference}
            </span>
            <span className="font-semibold capitalize text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">
              Status: {document.status}
            </span>
            <span className="inline-flex items-center gap-1 text-slate-600 bg-white border border-slate-200 px-2 py-0.5 rounded">
              <Building className="w-3 h-3 text-slate-400" />
              {document.department}
            </span>
            <span className="inline-flex items-center gap-1 text-slate-600 bg-white border border-slate-200 px-2 py-0.5 rounded">
              <Tag className="w-3 h-3 text-slate-400" />
              {document.classification}
            </span>
          </div>

          <h4 className="font-bold text-slate-800 text-sm tracking-tight">{document.title}</h4>

          {versionInfo && (
            <div className="text-[11px] text-slate-500 pt-1 border-t border-slate-200/60 flex items-center justify-between">
              <span>Version: <strong>v{versionInfo.version_number}</strong> ({versionInfo.original_filename})</span>
              {versionInfo.file_size_bytes && <span>{formatBytes(versionInfo.file_size_bytes)}</span>}
            </div>
          )}
        </div>

        <p className="mt-3 text-xs text-slate-600 leading-relaxed">
          Select an active, authorized approver from the directory below to review this document.
        </p>

        {/* Submission Form */}
        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          {/* Searchable Approver Selector */}
          <div className="space-y-1.5">
            <label className="block text-xs font-semibold text-slate-700">
              Select Eligible Approver <span className="text-red-500">*</span>
            </label>

            {/* Search Input */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-3" />
              <input
                type="text"
                data-testid="approver-search-input"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search approvers by name or email..."
                disabled={submitting}
                className="w-full pl-9 pr-3 py-2 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none bg-white"
              />
            </div>

            {/* Directory Error */}
            {directoryError && (
              <div
                data-testid="approver-directory-error"
                className="p-3 bg-red-50 text-red-800 rounded-lg text-xs border border-red-200 flex items-center space-x-2"
              >
                <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
                <span>{directoryError}</span>
              </div>
            )}

            {/* Approvers List Box */}
            <div
              data-testid="approver-selector-list"
              className="border border-slate-200 rounded-lg max-h-44 overflow-y-auto divide-y divide-slate-100 bg-white"
              role="radiogroup"
              aria-label="Eligible Approvers"
            >
              {loadingApprovers && (
                <div
                  data-testid="approver-loading-indicator"
                  className="p-4 text-center text-xs text-slate-400 flex items-center justify-center gap-2"
                >
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-blue-600" />
                  <span>Loading eligible approvers...</span>
                </div>
              )}

              {!loadingApprovers && !directoryError && approvers.length === 0 && (
                <div
                  data-testid="approver-empty-state"
                  className="p-5 text-center text-xs text-slate-400"
                >
                  <UserX className="w-6 h-6 text-slate-300 mx-auto mb-1.5" />
                  <p className="font-semibold text-slate-600">No eligible approvers found</p>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    No active approvers match your criteria in {document.department}.
                  </p>
                </div>
              )}

              {!loadingApprovers &&
                approvers.map((appr) => {
                  const isSelected = selectedApprover?.id === appr.id;

                  return (
                    <div
                      key={appr.id}
                      data-testid={`approver-option-${appr.id}`}
                      role="radio"
                      aria-checked={isSelected}
                      tabIndex={0}
                      onClick={() => !submitting && setSelectedApprover(appr)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          if (!submitting) setSelectedApprover(appr);
                        }
                      }}
                      className={`p-3 flex items-center justify-between cursor-pointer transition-colors text-xs ${
                        isSelected
                          ? "bg-blue-50/70 border-l-4 border-blue-600 pl-2.5"
                          : "hover:bg-slate-50 text-slate-700"
                      }`}
                    >
                      <div className="flex items-center space-x-2.5 min-w-0">
                        <div
                          className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-semibold ${
                            isSelected
                              ? "bg-blue-600 text-white"
                              : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          <User className="w-3.5 h-3.5" />
                        </div>
                        <div className="min-w-0">
                          <p className="font-semibold text-slate-900 truncate">
                            {appr.full_name}
                          </p>
                          <p className="text-[11px] text-slate-400 truncate">{appr.email}</p>
                        </div>
                      </div>

                      <div className="flex items-center space-x-2 flex-shrink-0">
                        <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
                          {appr.department}
                        </span>
                        {isSelected && (
                          <CheckCircle2
                            data-testid="selected-check-icon"
                            className="w-4 h-4 text-blue-600"
                          />
                        )}
                      </div>
                    </div>
                  );
                })}
            </div>

            {/* Selected Approver Pill */}
            {selectedApprover && (
              <div
                data-testid="selected-approver-display"
                className="p-2.5 bg-blue-50/50 border border-blue-200 rounded-lg text-xs flex items-center justify-between"
              >
                <div className="flex items-center space-x-2">
                  <UserCheck className="w-4 h-4 text-blue-600" />
                  <span className="text-slate-700">
                    Selected Approver: <strong>{selectedApprover.full_name}</strong> ({selectedApprover.department})
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedApprover(null)}
                  disabled={submitting}
                  className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                >
                  Change
                </button>
              </div>
            )}
          </div>

          {/* Submission Comments */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Submission Comments / Instructions (Optional)
            </label>
            <textarea
              data-testid="submission-comments-input"
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Provide context, revision notes, or review instructions for the selected approver..."
              rows={3}
              maxLength={1000}
              disabled={submitting}
              className="w-full text-xs p-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
            />
            <div className="flex justify-end text-[10px] text-slate-400 mt-1">
              {comments.length} / 1000 characters
            </div>
          </div>

          {/* Validation Error */}
          {validationError && (
            <div
              data-testid="submission-validation-error"
              className="p-3 bg-rose-50 text-rose-800 rounded-lg text-xs border border-rose-200 flex items-center space-x-2"
            >
              <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
              <span>{validationError}</span>
            </div>
          )}

          {/* API Error */}
          {apiError && (
            <div
              data-testid="submission-api-error"
              className="p-3 bg-red-50 text-red-800 rounded-lg text-xs border border-red-200 flex items-center space-x-2"
            >
              <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
              <span>{apiError}</span>
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end space-x-2.5 pt-2 border-t border-slate-100">
            <button
              type="button"
              onClick={handleClose}
              disabled={submitting}
              className="px-3.5 py-1.5 text-xs text-slate-600 hover:text-slate-800 rounded-lg hover:bg-slate-100 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              data-testid="confirm-submit-button"
              disabled={submitting}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors disabled:opacity-50"
            >
              {submitting ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  Submitting...
                </>
              ) : (
                <>
                  <Send className="w-3.5 h-3.5" />
                  Confirm & Submit
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
