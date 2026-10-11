"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { NotificationBell } from "./NotificationBell";
import { LogIn, LogOut, User as UserIcon, Shield, FileText } from "lucide-react";

export function Header() {
  const { user, login, loginWithCredentials, logout, loading } = useAuth();
  const [tokenInput, setTokenInput] = useState("");
  const [emailInput, setEmailInput] = useState("");
  const [passwordInput, setPasswordInput] = useState("");
  const [authMode, setAuthMode] = useState<"credentials" | "token">("credentials");
  const [showLoginModal, setShowLoginModal] = useState(false);
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

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16 items-center">
          {/* Logo / Title */}
          <div className="flex items-center space-x-3">
            <Link href="/" className="flex items-center space-x-3 group">
              <div className="h-9 w-9 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-lg shadow-sm group-hover:bg-blue-700 transition-colors">
                E
              </div>
              <div>
                <span className="text-base font-bold text-slate-900 tracking-tight">EKSPER</span>
                <span className="hidden sm:inline-block ml-2 text-xs text-slate-500 font-normal border-l border-slate-200 pl-2">
                  Document & Records Management
                </span>
              </div>
            </Link>
          </div>

          {/* Right Action Items */}
          <div className="flex items-center space-x-3">
            {user ? (
              <>
                <Link
                  href="/documents"
                  className="hidden md:inline-flex items-center text-xs font-medium text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  Documents
                </Link>

                {user.role === "approver" && (
                  <Link
                    href="/workflows/inbox"
                    className="hidden md:inline-flex items-center text-xs font-medium text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-lg hover:bg-slate-50 transition-colors"
                  >
                    Review Inbox
                  </Link>
                )}

                {user.role === "admin" && (
                  <Link
                    href="/admin/users"
                    className="hidden md:inline-flex items-center text-xs font-medium text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-lg hover:bg-slate-50 transition-colors"
                  >
                    User Management
                  </Link>
                )}

                {(user.role === "admin" || user.role === "records_officer") && (
                  <Link
                    href="/admin/audit-logs"
                    className="hidden md:inline-flex items-center text-xs font-medium text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-lg hover:bg-slate-50 transition-colors"
                  >
                    Audit Logs
                  </Link>
                )}

                {(user.role === "admin" || user.role === "records_officer" || user.role === "department_user" || user.role === "auditor") && (
                  <Link
                    href="/retention"
                    className="hidden md:inline-flex items-center text-xs font-medium text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-lg hover:bg-slate-50 transition-colors"
                  >
                    Retention
                  </Link>
                )}

                <Link
                  href="/physical-files"
                  className="hidden md:inline-flex items-center text-xs font-medium text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  Physical Files
                </Link>

                <Link
                  href="/storage-locations"
                  className="hidden md:inline-flex items-center text-xs font-medium text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  Storage Locations
                </Link>

                <Link
                  href="/notifications"
                  className="hidden md:inline-flex items-center text-xs font-medium text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  Notification Center
                </Link>

                {/* Notification Bell */}
                <NotificationBell />

                {/* User Profile Pill */}
                <div className="hidden sm:flex items-center space-x-2 pl-2 border-l border-slate-200">
                  <div className="h-8 w-8 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-600">
                    <UserIcon className="w-4 h-4" />
                  </div>
                  <div className="text-left text-xs">
                    <p className="font-semibold text-slate-800 leading-tight">{user.full_name}</p>
                    <p className="text-[10px] text-slate-500 capitalize">{user.role.replace("_", " ")}</p>
                  </div>
                </div>

                {/* Logout Button */}
                <button
                  type="button"
                  onClick={logout}
                  title="Logout"
                  className="p-2 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-lg focus:outline-none transition-colors"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </>
            ) : (
              !loading && (
                <button
                  type="button"
                  onClick={() => setShowLoginModal(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 transition-colors shadow-sm"
                >
                  <LogIn className="w-3.5 h-3.5" />
                  Sign In
                </button>
              )
            )}
          </div>
        </div>
      </div>

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

            {/* Quick Demo Account Selector (Development and Demo mode only; strictly excluded in production) */}
            {process.env.NEXT_PUBLIC_ENVIRONMENT !== "production" && process.env.NODE_ENV !== "production" && (
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
            )}

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
    </header>
  );
}
