"use client";

import React, { useState } from "react";
import { NotificationItem, NotificationType } from "@/types/notification";
import {
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ExternalLink,
  Check,
  FileText,
  RotateCcw,
} from "lucide-react";

interface NotificationCardProps {
  notification: NotificationItem;
  onMarkAsRead: (id: string) => Promise<void>;
  onNavigate?: (notification: NotificationItem) => void;
}

export function NotificationCard({
  notification,
  onMarkAsRead,
  onNavigate,
}: NotificationCardProps) {
  const [markingRead, setMarkingRead] = useState(false);

  const handleReadClick = async () => {
    if (notification.is_read || markingRead) return;
    setMarkingRead(true);
    try {
      await onMarkAsRead(notification.id);
    } finally {
      setMarkingRead(false);
    }
  };

  const getIconAndBadge = (type: NotificationType) => {
    switch (type) {
      case "workflow_submitted":
        return {
          icon: <Clock className="w-5 h-5 text-amber-600" />,
          bg: "bg-amber-50 text-amber-700 border-amber-200",
          label: "Review Required",
        };
      case "workflow_approved":
        return {
          icon: <CheckCircle2 className="w-5 h-5 text-emerald-600" />,
          bg: "bg-emerald-50 text-emerald-700 border-emerald-200",
          label: "Approved & Active",
        };
      case "workflow_rejected":
        return {
          icon: <XCircle className="w-5 h-5 text-rose-600" />,
          bg: "bg-rose-50 text-rose-700 border-rose-200",
          label: "Review Rejected",
        };
      case "workflow_cancelled":
        return {
          icon: <AlertCircle className="w-5 h-5 text-slate-600" />,
          bg: "bg-slate-100 text-slate-700 border-slate-200",
          label: "Review Withdrawn",
        };
      default:
        return {
          icon: <FileText className="w-5 h-5 text-blue-600" />,
          bg: "bg-blue-50 text-blue-700 border-blue-200",
          label: "Notification",
        };
    }
  };

  const badge = getIconAndBadge(notification.notification_type);
  const formattedDate = new Date(notification.created_at).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div
      data-testid={`notification-card-${notification.id}`}
      className={`p-4 sm:p-5 rounded-xl border transition-all duration-150 ${
        notification.is_read
          ? "bg-white border-slate-200/80 hover:border-slate-300"
          : "bg-blue-50/40 border-blue-200/70 shadow-sm"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        {/* Left icon & details */}
        <div className="flex items-start space-x-3.5">
          <div className="mt-0.5 p-2 rounded-lg bg-white shadow-xs border border-slate-100 flex-shrink-0">
            {badge.icon}
          </div>

          <div className="space-y-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold border ${badge.bg}`}>
                {badge.label}
              </span>
              <span className="text-xs text-slate-400 font-medium">
                {formattedDate}
              </span>
              {!notification.is_read && (
                <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-600 text-white">
                  NEW
                </span>
              )}
            </div>

            <h3 className="text-sm font-bold text-slate-900 tracking-tight">
              {notification.title}
            </h3>

            <p className="text-xs text-slate-600 leading-relaxed max-w-2xl">
              {notification.message}
            </p>

            {/* Reference IDs */}
            <div className="pt-1 flex items-center gap-3 text-[11px] text-slate-400 font-mono">
              {notification.document_id && (
                <span>Doc: {notification.document_id.slice(0, 8)}...</span>
              )}
              {notification.workflow_id && (
                <span>Workflow: {notification.workflow_id.slice(0, 8)}...</span>
              )}
            </div>
          </div>
        </div>

        {/* Right actions */}
        <div className="flex flex-col sm:flex-row items-end sm:items-center gap-2 flex-shrink-0">
          {!notification.is_read && (
            <button
              type="button"
              onClick={handleReadClick}
              disabled={markingRead}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-blue-700 bg-blue-100/60 hover:bg-blue-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 transition-colors disabled:opacity-50"
            >
              <Check className="w-3.5 h-3.5" />
              {markingRead ? "Marking..." : "Mark as read"}
            </button>
          )}

          {onNavigate && (notification.document_id || notification.workflow_id) && (
            <button
              type="button"
              onClick={() => onNavigate(notification)}
              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-slate-600 hover:text-slate-900 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-300 transition-colors shadow-2xs"
            >
              <span>View details</span>
              <ExternalLink className="w-3 h-3 text-slate-400" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
