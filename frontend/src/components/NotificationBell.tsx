"use client";

import React, { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bell, CheckCircle2, Clock, AlertCircle, XCircle, ArrowRight, ExternalLink } from "lucide-react";
import { useNotificationContext } from "@/context/NotificationContext";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { NotificationItem } from "@/types/notification";

export function NotificationBell() {
  const router = useRouter();
  const { user } = useAuth();
  const { unreadCount, refreshUnreadCount, decrementUnreadCount } = useNotificationContext();
  const [isOpen, setIsOpen] = useState(false);
  const [quickList, setQuickList] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const toggleDropdown = async () => {
    if (!isOpen) {
      setIsOpen(true);
      setLoading(true);
      setError(null);
      try {
        const res = await api.getNotifications(1, 5, false);
        setQuickList(res.items);
      } catch (err: any) {
        setError(err.message || "Failed to load notifications");
      } finally {
        setLoading(false);
      }
    } else {
      setIsOpen(false);
    }
  };

  const handleMarkAsRead = async (e: React.MouseEvent, item: NotificationItem) => {
    e.stopPropagation();
    if (item.is_read) return;
    try {
      await api.markNotificationAsRead(item.id);
      setQuickList((prev) =>
        prev.map((n) => (n.id === item.id ? { ...n, is_read: true, read_at: new Date().toISOString() } : n))
      );
      decrementUnreadCount();
    } catch {
      // Ignore
    }
  };

  if (!user) return null;

  const badgeText = unreadCount > 99 ? "99+" : unreadCount > 0 ? unreadCount.toString() : null;
  const ariaLabel = unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications, none unread";

  return (
    <div className="relative inline-block text-left" ref={dropdownRef}>
      <button
        type="button"
        onClick={toggleDropdown}
        aria-label={ariaLabel}
        aria-expanded={isOpen}
        aria-haspopup="true"
        className="relative p-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
      >
        <Bell className="w-5 h-5" />
        {badgeText && (
          <span
            data-testid="unread-badge"
            className="absolute top-1 right-1 inline-flex items-center justify-center px-1.5 py-0.5 text-xs font-bold leading-none text-white transform translate-x-1/4 -translate-y-1/4 bg-blue-600 rounded-full ring-2 ring-white"
          >
            {badgeText}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          data-testid="notification-dropdown"
          className="origin-top-right absolute right-0 mt-2 w-80 sm:w-96 rounded-xl shadow-lg bg-white ring-1 ring-black ring-opacity-5 border border-slate-100 z-50 divide-y divide-slate-100 animate-in fade-in slide-in-from-top-2 duration-150"
        >
          <div className="p-4 flex items-center justify-between bg-slate-50/50 rounded-t-xl">
            <div className="flex items-center space-x-2">
              <span className="font-semibold text-slate-900 text-sm">Notifications</span>
              {unreadCount > 0 && (
                <span className="bg-blue-100 text-blue-700 text-xs px-2 py-0.5 rounded-full font-medium">
                  {unreadCount} unread
                </span>
              )}
            </div>
            <Link
              href="/notifications"
              onClick={() => setIsOpen(false)}
              className="text-xs font-medium text-blue-600 hover:text-blue-800 flex items-center gap-1"
            >
              View all <ArrowRight className="w-3 h-3" />
            </Link>
          </div>

          <div className="max-h-80 overflow-y-auto divide-y divide-slate-50">
            {loading && (
              <div className="p-6 text-center text-slate-400 text-xs animate-pulse">
                Loading notifications...
              </div>
            )}

            {error && (
              <div className="p-4 text-center text-red-600 text-xs bg-red-50/50">
                {error}
              </div>
            )}

            {!loading && !error && quickList.length === 0 && (
              <div className="p-8 text-center text-slate-400 text-xs">
                No notifications yet
              </div>
            )}

            {!loading &&
              quickList.map((item) => (
                <div
                  key={item.id}
                  onClick={() => {
                    setIsOpen(false);
                    if (item.workflow_id) {
                      router.push(`/workflows/${item.workflow_id}`);
                    } else {
                      router.push("/notifications");
                    }
                  }}
                  className={`p-3.5 hover:bg-slate-50 cursor-pointer transition-colors flex items-start space-x-3 text-left ${
                    !item.is_read ? "bg-blue-50/30" : ""
                  }`}
                >
                  <div className="mt-0.5 flex-shrink-0">
                    {item.notification_type === "workflow_submitted" && (
                      <Clock className="w-4 h-4 text-amber-500" />
                    )}
                    {item.notification_type === "workflow_approved" && (
                      <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                    )}
                    {item.notification_type === "workflow_rejected" && (
                      <XCircle className="w-4 h-4 text-rose-500" />
                    )}
                    {item.notification_type === "workflow_cancelled" && (
                      <AlertCircle className="w-4 h-4 text-slate-500" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`text-xs ${!item.is_read ? "font-semibold text-slate-900" : "font-medium text-slate-700"} truncate`}>
                      {item.title}
                    </p>
                    <p className="text-xs text-slate-500 line-clamp-2 mt-0.5">
                      {item.message}
                    </p>
                    <div className="flex items-center justify-between mt-1 text-[10px] text-slate-400">
                      <span>{new Date(item.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                      {!item.is_read && (
                        <button
                          type="button"
                          onClick={(e) => handleMarkAsRead(e, item)}
                          className="text-blue-600 hover:text-blue-800 font-medium"
                        >
                          Mark read
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
          </div>

          <div className="p-2.5 text-center bg-slate-50/50 rounded-b-xl">
            <Link
              href="/notifications"
              onClick={() => setIsOpen(false)}
              className="text-xs font-medium text-slate-600 hover:text-slate-900 block w-full py-1"
            >
              Open Notification Center
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
