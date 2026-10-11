"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { ReviewAssignmentItem, PaginatedAssignmentsResponse } from "@/types/workflow";
import {
  Inbox,
  Clock,
  User,
  Building,
  Tag,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  AlertTriangle,
  ShieldAlert,
  ArrowRight,
  FileCheck2,
  Calendar,
  MessageSquare,
} from "lucide-react";

export default function ApproverInboxPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();

  const [assignments, setAssignments] = useState<ReviewAssignmentItem[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAssignments = useCallback(
    async (page: number) => {
      if (!user || user.role !== "approver") return;
      setLoading(true);
      setError(null);
      try {
        const res: PaginatedAssignmentsResponse = await api.getMyAssignments(page, 10);
        setAssignments(res.items);
        setTotal(res.total);
        setTotalPages(res.total_pages || 1);
        setCurrentPage(res.page);
      } catch (err: any) {
        setError(err.message || "Failed to load review assignments.");
      } finally {
        setLoading(false);
      }
    },
    [user]
  );

  useEffect(() => {
    if (user && user.role === "approver") {
      fetchAssignments(currentPage);
    }
  }, [user, currentPage, fetchAssignments]);

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
            Please sign in to access your review assignments inbox.
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

  if (user.role !== "approver") {
    return (
      <main className="w-full px-4 sm:px-6 lg:px-8 py-12">
        <div className="bg-white rounded-xl shadow-sm border border-rose-200 p-8 text-center max-w-md mx-auto">
          <ShieldAlert className="w-12 h-12 text-rose-500 mx-auto mb-3" />
          <h2 className="text-lg font-bold text-slate-800 mb-1">Access Restricted</h2>
          <p className="text-xs text-slate-500 mb-6 leading-relaxed">
            Only users with the <span className="font-semibold text-rose-600">approver</span> role can access the review inbox. Your current role is <span className="font-semibold capitalize text-slate-700">{user.role.replace("_", " ")}</span>.
          </p>
          <Link
            href="/"
            className="inline-flex items-center justify-center px-4 py-2 text-xs font-semibold text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200 transition-colors"
          >
            Return to Dashboard
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="w-full px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6 pb-6 border-b border-slate-200">
        <div>
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Review Inbox</h1>
            <span
              data-testid="pending-count-badge"
              className="bg-amber-100 text-amber-800 text-xs px-2.5 py-0.5 rounded-full font-semibold border border-amber-200"
            >
              {total} pending {total === 1 ? "review" : "reviews"}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Documents explicitly assigned to you for review, approval, or rejection.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => fetchAssignments(currentPage)}
            title="Refresh assignments"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 rounded-lg border border-slate-300 transition-colors shadow-2xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error Notice */}
      {error && (
        <div className="mb-6 p-4 bg-red-50 text-red-800 text-xs rounded-xl border border-red-200 flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Loading Skeleton */}
      {loading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="p-6 rounded-xl border border-slate-200 bg-white animate-pulse">
              <div className="space-y-3">
                <div className="h-4 bg-slate-200 rounded w-1/3" />
                <div className="h-3 bg-slate-200 rounded w-2/3" />
                <div className="h-3 bg-slate-100 rounded w-1/2" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && assignments.length === 0 && (
        <div className="bg-white rounded-xl shadow-xs border border-slate-200 p-12 text-center">
          <Inbox className="w-12 h-12 text-slate-300 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-slate-800">No pending review assignments</h3>
          <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
            You do not have any documents assigned for review at this time. When a department user submits a document to you, it will appear here.
          </p>
        </div>
      )}

      {/* Assignment List */}
      {!loading && assignments.length > 0 && (
        <div className="space-y-4">
          {assignments.map((item) => {
            const formattedDate = new Date(item.submitted_at).toLocaleString(undefined, {
              year: "numeric",
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            });

            return (
              <div
                key={item.assignment_id}
                data-testid={`assignment-item-${item.workflow_id}`}
                className="p-5 sm:p-6 rounded-xl border border-slate-200 bg-white shadow-2xs hover:border-slate-300 transition-all duration-150"
              >
                <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                  {/* Left Metadata */}
                  <div className="space-y-2 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-xs font-bold text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded">
                        {item.document.document_reference}
                      </span>
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">
                        <Clock className="w-3 h-3" /> Pending Review
                      </span>
                      <span className="inline-flex items-center gap-1 text-[11px] text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                        <Building className="w-3 h-3 text-slate-400" />
                        {item.document.department}
                      </span>
                      <span className="inline-flex items-center gap-1 text-[11px] text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                        <Tag className="w-3 h-3 text-slate-400" />
                        {item.document.classification}
                      </span>
                    </div>

                    <h2 className="text-base font-bold text-slate-900 tracking-tight">
                      {item.document.title}
                    </h2>

                    {/* Submitter & Date */}
                    <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500 pt-1">
                      <div className="flex items-center gap-1.5">
                        <User className="w-3.5 h-3.5 text-slate-400" />
                        <span>Submitted by:</span>
                        <strong className="text-slate-700">{item.submitter.full_name}</strong>
                        <span className="text-slate-400">({item.submitter.email})</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5 text-slate-400" />
                        <span>{formattedDate}</span>
                      </div>
                    </div>

                    {/* Submitter Comments */}
                    {item.submission_comments && (
                      <div className="mt-3 p-3 bg-slate-50 rounded-lg border border-slate-100 text-xs text-slate-600 flex items-start gap-2">
                        <MessageSquare className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" />
                        <div>
                          <span className="font-semibold text-slate-700">Submission Note: </span>
                          <span className="italic">{item.submission_comments}</span>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Right Action */}
                  <div className="flex md:flex-col justify-end items-end gap-2 pt-2 md:pt-0">
                    <Link
                      href={`/workflows/${item.workflow_id}`}
                      className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 transition-colors shadow-sm"
                    >
                      <span>Open Review</span>
                      <ArrowRight className="w-3.5 h-3.5" />
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
    </main>
  );
}
