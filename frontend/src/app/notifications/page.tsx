"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { useNotificationContext } from "@/context/NotificationContext";
import { NotificationCard } from "@/components/NotificationCard";
import { NotificationItem, PaginatedNotificationsResponse } from "@/types/notification";
import { api } from "@/lib/api";
import {
  Bell,
  CheckCircle,
  Filter,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  Inbox,
  ShieldAlert,
} from "lucide-react";

export default function NotificationCenterPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const { refreshUnreadCount, decrementUnreadCount } = useNotificationContext();

  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [unreadOnly, setUnreadOnly] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [navNotice, setNavNotice] = useState<string | null>(null);

  const fetchNotifications = useCallback(
    async (page: number, unreadFilter: boolean) => {
      if (!user) return;
      setLoading(true);
      setError(null);
      try {
        const res: PaginatedNotificationsResponse = await api.getNotifications(page, 10, unreadFilter);
        setNotifications(res.items);
        setTotal(res.total);
        setUnreadCount(res.unread_count);
        setTotalPages(res.total_pages || 1);
        setCurrentPage(res.page);
      } catch (err: any) {
        setError(err.message || "An error occurred while fetching notifications.");
      } finally {
        setLoading(false);
      }
    },
    [user]
  );

  useEffect(() => {
    if (user) {
      fetchNotifications(currentPage, unreadOnly);
    }
  }, [user, currentPage, unreadOnly, fetchNotifications]);

  const handleMarkAsRead = async (id: string) => {
    try {
      await api.markNotificationAsRead(id);
      setNotifications((prev) =>
        prev.map((item) =>
          item.id === id ? { ...item, is_read: true, read_at: new Date().toISOString() } : item
        )
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
      decrementUnreadCount();
      setSuccessMsg("Notification marked as read.");
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err: any) {
      setError(err.message || "Failed to mark notification as read.");
    }
  };

  const handleNavigate = (notification: NotificationItem) => {
    if (notification.workflow_id) {
      router.push(`/workflows/${notification.workflow_id}`);
      return;
    }
    setNavNotice(
      `Notification references document ID: ${notification.document_id || "N/A"}. Backend authorization is enforced via /api/v1/documents.`
    );
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
            Please authenticate using the &quot;Sign In&quot; button in the header to view your Notification Center.
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
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6 pb-6 border-b border-slate-200">
        <div>
          <div className="flex items-center space-x-2.5">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Notification Center</h1>
            {unreadCount > 0 && (
              <span className="bg-blue-100 text-blue-700 text-xs px-2.5 py-0.5 rounded-full font-semibold">
                {unreadCount} unread
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Stay updated on review submissions, approvals, rejections, and workflow lifecycle changes.
          </p>
        </div>

        {/* Action controls */}
        <div className="flex items-center gap-2">
          {/* Unread Filter Toggle */}
          <button
            type="button"
            onClick={() => {
              setUnreadOnly(!unreadOnly);
              setCurrentPage(1);
            }}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
              unreadOnly
                ? "bg-blue-600 text-white border-blue-600 shadow-xs"
                : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
            }`}
          >
            <Filter className="w-3.5 h-3.5" />
            {unreadOnly ? "Showing Unread" : "All Notifications"}
          </button>

          {/* Refresh button */}
          <button
            type="button"
            onClick={() => {
              fetchNotifications(currentPage, unreadOnly);
              refreshUnreadCount();
            }}
            title="Refresh notifications"
            className="p-1.5 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg border border-slate-200 bg-white transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Feedback alerts */}
      {successMsg && (
        <div className="mb-4 p-3 bg-emerald-50 text-emerald-800 text-xs rounded-xl border border-emerald-200 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <CheckCircle className="w-4 h-4 text-emerald-600" />
            <span>{successMsg}</span>
          </div>
        </div>
      )}

      {error && (
        <div className="mb-4 p-3.5 bg-red-50 text-red-800 text-xs rounded-xl border border-red-200 flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {navNotice && (
        <div className="mb-4 p-3.5 bg-blue-50 text-blue-800 text-xs rounded-xl border border-blue-200 flex items-start justify-between">
          <div className="space-y-1">
            <p className="font-semibold">Document & Workflow Reference</p>
            <p className="text-[11px] leading-relaxed">{navNotice}</p>
          </div>
          <button
            type="button"
            onClick={() => setNavNotice(null)}
            className="text-xs text-blue-600 hover:text-blue-800 font-bold ml-2"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="p-5 rounded-xl border border-slate-200 bg-white animate-pulse">
              <div className="flex space-x-3">
                <div className="w-10 h-10 bg-slate-200 rounded-lg" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 bg-slate-200 rounded w-1/4" />
                  <div className="h-3 bg-slate-200 rounded w-3/4" />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty states */}
      {!loading && !error && notifications.length === 0 && (
        <div className="bg-white rounded-xl shadow-xs border border-slate-200 p-12 text-center">
          <Inbox className="w-12 h-12 text-slate-300 mx-auto mb-3" />
          <h3 className="text-base font-semibold text-slate-800">
            {unreadOnly ? "No unread notifications" : "No notifications yet"}
          </h3>
          <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
            {unreadOnly
              ? "You're all caught up! You can switch back to view all historical notifications."
              : "When a document is submitted for your review or your submission status updates, notifications will appear here."}
          </p>
          {unreadOnly && (
            <button
              type="button"
              onClick={() => {
                setUnreadOnly(false);
                setCurrentPage(1);
              }}
              className="mt-4 px-3 py-1.5 text-xs font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors"
            >
              Show all notifications
            </button>
          )}
        </div>
      )}

      {/* Notification Cards List */}
      {!loading && notifications.length > 0 && (
        <div className="space-y-3">
          {notifications.map((item) => (
            <NotificationCard
              key={item.id}
              notification={item}
              onMarkAsRead={handleMarkAsRead}
              onNavigate={handleNavigate}
            />
          ))}
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
