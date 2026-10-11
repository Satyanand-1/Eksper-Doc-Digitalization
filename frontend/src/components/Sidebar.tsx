"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { useNotificationContext } from "@/context/NotificationContext";
import { NotificationBell } from "./NotificationBell";
import {
  LayoutDashboard,
  FileText,
  FolderArchive,
  Building2,
  Clock,
  Shield,
  Inbox,
  Users,
  Bell,
  Menu,
  X,
  LogIn,
  LogOut,
  User as UserIcon,
} from "lucide-react";

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: number;
}

interface NavSection {
  group: string;
  items: NavItem[];
}

export function Sidebar() {
  const pathname = usePathname();
  const { user, login, loginWithCredentials, logout, loading } = useAuth();
  const { unreadCount } = useNotificationContext();

  const [mobileOpen, setMobileOpen] = useState(false);

  // Sign In modal state
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [tokenInput, setTokenInput] = useState("");
  const [emailInput, setEmailInput] = useState("");
  const [passwordInput, setPasswordInput] = useState("");
  const [authMode, setAuthMode] = useState<"credentials" | "token">("credentials");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const DEMO_ACCOUNTS = [
    { label: "Admin", email: "admin@example.com", pass: "DevAdminPassword123!", role: "System Administrator" },
    { label: "Records Officer", email: "records.officer@example.com", pass: "DevRecordsPassword123!", role: "Governance & Archival" },
    { label: "Dept User (Finance)", email: "dept.user@example.com", pass: "DevDeptPassword123!", role: "Upload & Drafts" },
    { label: "Approver", email: "approver@example.com", pass: "DevApproverPassword123!", role: "Review & Decision" },
    { label: "Auditor", email: "auditor@example.com", pass: "DevAuditorPassword123!", role: "Compliance View" },
  ];

  const handleCredentialsLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!emailInput.trim() || !passwordInput.trim()) return;
    setLoginError(null);
    setSubmitting(true);
    try {
      await loginWithCredentials(emailInput.trim(), passwordInput.trim());
      setShowLoginModal(false);
      setEmailInput("");
      setPasswordInput("");
    } catch (err: any) {
      setLoginError(err.message || "Invalid credentials or unauthorized account.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleTokenLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!tokenInput.trim()) return;
    setLoginError(null);
    setSubmitting(true);
    try {
      await login(tokenInput.trim());
      setShowLoginModal(false);
      setTokenInput("");
    } catch (err: any) {
      setLoginError(err.message || "Failed to authenticate with token.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleFillDemo = (acc: typeof DEMO_ACCOUNTS[0]) => {
    setEmailInput(acc.email);
    setPasswordInput(acc.pass);
    setAuthMode("credentials");
    setLoginError(null);
  };

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  const canViewRetention =
    user &&
    ["admin", "records_officer", "department_user", "auditor"].includes(user.role);

  const canViewAuditLogs =
    user && ["admin", "records_officer"].includes(user.role);

  const canViewInbox =
    user && (user.role === "approver" || user.role === "admin");

  const canViewUsers = user && user.role === "admin";

  const navLinks: NavSection[] = [
    {
      group: "Overview",
      items: [
        { label: "Dashboard", href: "/", icon: LayoutDashboard },
      ],
    },
    {
      group: "Records Management",
      items: [
        { label: "Documents", href: "/documents", icon: FileText },
        { label: "Physical Files", href: "/physical-files", icon: FolderArchive },
        { label: "Storage Locations", href: "/storage-locations", icon: Building2 },
      ],
    },
    ...(canViewRetention || canViewAuditLogs
      ? [
          {
            group: "Governance",
            items: [
              ...(canViewRetention
                ? [{ label: "Retention & Disposal", href: "/retention", icon: Clock }]
                : []),
              ...(canViewAuditLogs
                ? [{ label: "Audit Logs", href: "/admin/audit-logs", icon: Shield }]
                : []),
            ],
          },
        ]
      : []),
    ...(canViewInbox || canViewUsers
      ? [
          {
            group: "Administration",
            items: [
              ...(canViewInbox
                ? [{ label: "Review Inbox", href: "/workflows/inbox", icon: Inbox }]
                : []),
              ...(canViewUsers
                ? [{ label: "User Management", href: "/admin/users", icon: Users }]
                : []),
            ],
          },
        ]
      : []),
    {
      group: "Communication",
      items: [
        {
          label: "Notifications",
          href: "/notifications",
          icon: Bell,
          badge: unreadCount > 0 ? unreadCount : undefined,
        },
      ],
    },
  ];

  const sidebarContent = (
    <div className="flex flex-col h-full bg-white text-slate-800">
      {/* Brand Header */}
      <div className="h-16 px-5 flex items-center justify-between border-b border-slate-200">
        <Link
          href="/"
          onClick={() => setMobileOpen(false)}
          className="flex items-center space-x-3 group"
        >
          <div className="h-9 w-9 rounded-xl bg-blue-600 flex items-center justify-center text-white font-bold text-lg shadow-sm group-hover:bg-blue-700 transition-colors">
            E
          </div>
          <div className="flex flex-col">
            <span className="text-base font-extrabold text-slate-900 tracking-tight leading-none">
              EKSPER
            </span>
            <span className="text-[10px] text-slate-500 font-medium tracking-wide mt-0.5">
              Document & Records
            </span>
          </div>
        </Link>
        {mobileOpen && (
          <button
            type="button"
            onClick={() => setMobileOpen(false)}
            className="md:hidden p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
          >
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Nav Menu */}
      <nav className="flex-1 px-3 py-4 space-y-6 overflow-y-auto">
        {navLinks.map((section, idx) => (
          <div key={idx} className="space-y-1">
            <div className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
              {section.group}
            </div>
            {section.items.map((item) => {
              const active = isActive(item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileOpen(false)}
                  className={`flex items-center justify-between px-3 py-2 text-xs rounded-xl font-medium transition-colors ${
                    active
                      ? "bg-blue-50 text-blue-700 font-semibold"
                      : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                  }`}
                >
                  <div className="flex items-center space-x-2.5">
                    <Icon
                      className={`w-4 h-4 ${
                        active ? "text-blue-600" : "text-slate-500"
                      }`}
                    />
                    <span>{item.label}</span>
                  </div>
                  {item.badge !== undefined && (
                    <span className="ml-auto inline-flex items-center justify-center px-1.5 py-0.5 text-[10px] font-bold leading-none text-white bg-blue-600 rounded-full">
                      {item.badge}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Footer / User Session Card */}
      <div className="p-3 border-t border-slate-200 bg-slate-50">
        {user ? (
          <div className="flex items-center justify-between bg-white p-2.5 rounded-xl border border-slate-200 shadow-2xs">
            <div className="flex items-center space-x-2.5 min-w-0">
              <div className="h-8 w-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold border border-blue-200 shrink-0">
                {user.full_name?.charAt(0).toUpperCase() || "U"}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-slate-800 truncate leading-tight">
                  {user.full_name}
                </p>
                <p className="text-[10px] text-slate-500 capitalize truncate mt-0.5">
                  {user.role.replace("_", " ")}
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-1 shrink-0 ml-1">
              <NotificationBell />
              <button
                type="button"
                onClick={logout}
                title="Sign Out"
                className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        ) : (
          !loading && (
            <button
              type="button"
              onClick={() => {
                setShowLoginModal(true);
                setMobileOpen(false);
              }}
              className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 text-xs font-semibold text-white bg-blue-600 rounded-xl hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 transition-colors shadow-sm"
            >
              <LogIn className="w-3.5 h-3.5" />
              Sign In to EKSPER
            </button>
          )
        )}
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Sticky Left Sidebar */}
      <aside className="hidden md:flex flex-col w-64 h-screen sticky top-0 shrink-0 border-r border-slate-200 z-30">
        {sidebarContent}
      </aside>

      {/* Mobile Top Header */}
      <header className="md:hidden flex items-center justify-between px-4 h-16 bg-white border-b border-slate-200 sticky top-0 z-30">
        <div className="flex items-center space-x-3">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            aria-label="Open Navigation Menu"
            className="p-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg"
          >
            <Menu className="w-5 h-5" />
          </button>
          <Link href="/" className="flex items-center space-x-2">
            <div className="h-7 w-7 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-sm">
              E
            </div>
            <span className="text-base font-bold text-slate-900">EKSPER</span>
          </Link>
        </div>
        <div className="flex items-center space-x-2">
          {user ? (
            <>
              <NotificationBell />
              <button
                type="button"
                onClick={logout}
                title="Logout"
                className="p-1.5 text-slate-500 hover:text-red-600 rounded-lg"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setShowLoginModal(true)}
              className="px-2.5 py-1 text-xs font-semibold text-white bg-blue-600 rounded-lg hover:bg-blue-700"
            >
              Sign In
            </button>
          )}
        </div>
      </header>

      {/* Mobile Drawer Overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex">
          <div
            className="fixed inset-0 bg-black/40 backdrop-blur-xs transition-opacity"
            onClick={() => setMobileOpen(false)}
          />
          <div className="relative w-72 max-w-[80vw] h-full shadow-2xl z-10">
            {sidebarContent}
          </div>
        </div>
      )}

      {/* Sign In & Demo Role Modal */}
      {showLoginModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full p-6 border border-slate-200">
            <div className="flex items-center justify-between pb-3 mb-4 border-b border-slate-100">
              <div className="flex items-center space-x-2 text-slate-900">
                <Shield className="w-5 h-5 text-blue-600" />
                <h3 className="text-base font-bold">Sign In to EKSPER</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowLoginModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg hover:bg-slate-100"
              >
                ✕
              </button>
            </div>

            {/* Quick Demo Account Selector (1-Click Fill) */}
            <div className="mb-5 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
              <p className="text-[11px] font-semibold text-slate-700 uppercase tracking-wider mb-2">
                Quick Demo Accounts (1-Click Fill)
              </p>
              <div className="flex flex-wrap gap-1.5">
                {DEMO_ACCOUNTS.map((acc) => (
                  <button
                    key={acc.label}
                    type="button"
                    onClick={() => handleFillDemo(acc)}
                    className="text-[11px] font-medium px-2.5 py-1 bg-white hover:bg-blue-50 text-slate-700 hover:text-blue-700 rounded-lg border border-slate-300 hover:border-blue-300 transition-colors shadow-2xs"
                  >
                    {acc.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Tabs for Credentials vs Token */}
            <div className="flex border-b border-slate-200 mb-4 text-xs font-medium">
              <button
                type="button"
                onClick={() => setAuthMode("credentials")}
                className={`pb-2 px-3 border-b-2 transition-colors ${
                  authMode === "credentials"
                    ? "border-blue-600 text-blue-600 font-semibold"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                Email & Password
              </button>
              <button
                type="button"
                onClick={() => setAuthMode("token")}
                className={`pb-2 px-3 border-b-2 transition-colors ${
                  authMode === "token"
                    ? "border-blue-600 text-blue-600 font-semibold"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                Raw JWT Token
              </button>
            </div>

            {authMode === "credentials" ? (
              <form onSubmit={handleCredentialsLogin} className="space-y-3.5">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Email Address
                  </label>
                  <input
                    type="email"
                    value={emailInput}
                    onChange={(e) => setEmailInput(e.target.value)}
                    placeholder="user@example.com"
                    className="w-full text-xs p-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Password
                  </label>
                  <input
                    type="password"
                    value={passwordInput}
                    onChange={(e) => setPasswordInput(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full text-xs p-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                    required
                  />
                </div>

                {loginError && (
                  <div className="p-3 bg-red-50 text-red-700 rounded-xl text-xs border border-red-200">
                    {loginError}
                  </div>
                )}

                <div className="flex justify-end space-x-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowLoginModal(false)}
                    className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-800 rounded-xl hover:bg-slate-100"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submitting}
                    className="px-5 py-2 text-xs font-semibold text-white bg-blue-600 rounded-xl hover:bg-blue-700 shadow-sm transition-colors disabled:opacity-50"
                  >
                    {submitting ? "Signing In..." : "Sign In"}
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleTokenLogin} className="space-y-3.5">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Bearer Access Token
                  </label>
                  <textarea
                    value={tokenInput}
                    onChange={(e) => setTokenInput(e.target.value)}
                    placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                    rows={4}
                    className="w-full text-xs font-mono p-2.5 border border-slate-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                    required
                  />
                </div>

                {loginError && (
                  <div className="p-3 bg-red-50 text-red-700 rounded-xl text-xs border border-red-200">
                    {loginError}
                  </div>
                )}

                <div className="flex justify-end space-x-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowLoginModal(false)}
                    className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-800 rounded-xl hover:bg-slate-100"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submitting}
                    className="px-5 py-2 text-xs font-semibold text-white bg-blue-600 rounded-xl hover:bg-blue-700 shadow-sm transition-colors disabled:opacity-50"
                  >
                    {submitting ? "Authenticating..." : "Authenticate"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  );
}
