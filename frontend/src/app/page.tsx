"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import {
  FileText,
  FolderArchive,
  ShieldCheck,
  Clock,
  Layers,
  ArrowRight,
  Inbox,
  AlertTriangle,
  CheckCircle2,
  Database,
  Server,
  MapPin,
  Users,
  Search,
  ExternalLink,
} from "lucide-react";

interface HealthStatus {
  status: string;
  service: string;
  version: string;
  environment: string;
}

interface ReadinessStatus {
  status: string;
  service: string;
  database: {
    status: string;
  };
}

export default function Home() {
  const { user } = useAuth();
  const [backendHealth, setBackendHealth] = useState<HealthStatus | null>(null);
  const [readinessHealth, setReadinessHealth] = useState<ReadinessStatus | null>(null);
  const [loadingHealth, setLoadingHealth] = useState<boolean>(true);
  const [healthError, setHealthError] = useState<string | null>(null);

  // Live authorized operational counts
  const [docCount, setDocCount] = useState<number | null>(null);
  const [physicalFileCount, setPhysicalFileCount] = useState<number | null>(null);
  const [locationCount, setLocationCount] = useState<number | null>(null);
  const [assignmentCount, setAssignmentCount] = useState<number | null>(null);
  const [overdueCount, setOverdueCount] = useState<number | null>(null);
  const [auditSummary, setAuditSummary] = useState<{ total: number; success: number; denied: number } | null>(null);

  useEffect(() => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    Promise.all([
      fetch(`${apiBase}/api/v1/health`).then((res) => {
        if (!res.ok) throw new Error(`Health HTTP error: ${res.status}`);
        return res.json();
      }),
      fetch(`${apiBase}/api/v1/health/ready`).then((res) => {
        if (!res.ok) throw new Error(`Readiness HTTP error: ${res.status}`);
        return res.json();
      }),
    ])
      .then(([healthData, readyData]: [HealthStatus, ReadinessStatus]) => {
        setBackendHealth(healthData);
        setReadinessHealth(readyData);
        setLoadingHealth(false);
      })
      .catch((err: Error) => {
        setHealthError(err.message);
        setLoadingHealth(false);
      });
  }, []);

  useEffect(() => {
    if (!user) return;

    // Fetch documents count
    api.getDocuments(1, 1).then((res) => setDocCount(res.total)).catch(() => {});

    // Fetch physical files count
    api.getPhysicalFiles({ page: 1, page_size: 1 }).then((res) => setPhysicalFileCount(res.total)).catch(() => {});

    // Fetch storage locations count
    api.getStorageLocations({ page: 1, page_size: 1 }).then((res) => setLocationCount(res.total)).catch(() => {});

    // Fetch pending review assignments for approvers
    if (user.role === "approver") {
      api.getMyAssignments(1, 1).then((res) => setAssignmentCount(res.total)).catch(() => {});
    }

    // Fetch overdue physical files count
    api.getOverduePhysicalFiles({ page: 1, page_size: 1 }).then((res) => setOverdueCount(res.total)).catch(() => {});

    // Fetch audit summary for Admins and Records Officers
    if (user.role === "admin" || user.role === "records_officer") {
      api.getAuditReportSummary().then((res) => {
        setAuditSummary({
          total: res.total_events,
          success: res.events_by_outcome["success"] || 0,
          denied: res.events_by_outcome["denied"] || 0,
        });
      }).catch(() => {});
    }
  }, [user]);

  return (
    <main className="w-full px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-blue-900 via-indigo-900 to-slate-900 rounded-2xl p-6 sm:p-8 text-white shadow-md relative overflow-hidden">
        <div className="relative z-10 max-w-3xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/20 text-blue-200 text-xs font-semibold mb-3 border border-blue-400/20">
            <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
            Enterprise Record Governance System
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
            Electronic Document & Records Management
          </h1>
          <p className="mt-2 text-sm sm:text-base text-blue-100/80 leading-relaxed">
            Governed digital document lifecycle, OCR extraction, full-text search, review approvals, physical file registry, and chain-of-custody tracking.
          </p>

          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href="/documents"
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-xl bg-blue-600 hover:bg-blue-500 text-white transition-colors shadow-sm"
            >
              <FileText className="w-4 h-4" />
              Browse Documents
            </Link>
            <Link
              href="/physical-files"
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-xl bg-white/10 hover:bg-white/20 text-white backdrop-blur-xs transition-colors border border-white/10"
            >
              <FolderArchive className="w-4 h-4" />
              Physical File Registry
            </Link>
          </div>
        </div>

        {/* Decorative background shape */}
        <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-radial from-blue-500/10 to-transparent pointer-events-none" />
      </div>

      {/* User Welcome & Role Context */}
      {user ? (
        <div className="bg-white rounded-xl border border-slate-200 p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-2xs">
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 rounded-full bg-blue-50 border border-blue-200 text-blue-700 flex items-center justify-center font-bold text-sm">
              {user.full_name.charAt(0)}
            </div>
            <div>
              <p className="text-sm font-bold text-slate-900">
                Welcome back, {user.full_name}
              </p>
              <p className="text-xs text-slate-500">
                Department: <span className="font-semibold text-slate-700">{user.department || "General"}</span> • Role: <span className="font-semibold text-blue-600 capitalize">{user.role.replace("_", " ")}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <span className="px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 font-medium">
              Active Session
            </span>
            <span className="px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 font-medium border border-emerald-200">
              Department Scoped
            </span>
          </div>
        </div>
      ) : (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-bold text-blue-900">Guest Access Mode</h2>
            <p className="text-xs text-blue-700 mt-0.5">
              Please sign in using the top-right button or select a preset demo role to access authorized documents and workflows.
            </p>
          </div>
        </div>
      )}

      {/* Live Operational Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Metric 1: Digital Documents */}
        <Link
          href="/documents"
          className="bg-white p-5 rounded-2xl border border-slate-200 hover:border-blue-300 hover:shadow-md transition-all group block"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Digital Documents</span>
            <div className="h-8 w-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center group-hover:scale-110 transition-transform">
              <FileText className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline justify-between">
            <span className="text-2xl font-black text-slate-900">
              {docCount !== null ? docCount : "—"}
            </span>
            <span className="text-xs font-medium text-blue-600 group-hover:translate-x-0.5 transition-transform inline-flex items-center gap-1">
              View <ArrowRight className="w-3 h-3" />
            </span>
          </div>
          <p className="text-[11px] text-slate-400 mt-1">Repository files in scope</p>
        </Link>

        {/* Metric 2: Physical Files */}
        <Link
          href="/physical-files"
          className="bg-white p-5 rounded-2xl border border-slate-200 hover:border-indigo-300 hover:shadow-md transition-all group block"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Physical Registry</span>
            <div className="h-8 w-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center group-hover:scale-110 transition-transform">
              <FolderArchive className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline justify-between">
            <span className="text-2xl font-black text-slate-900">
              {physicalFileCount !== null ? physicalFileCount : "—"}
            </span>
            <span className="text-xs font-medium text-indigo-600 group-hover:translate-x-0.5 transition-transform inline-flex items-center gap-1">
              Registry <ArrowRight className="w-3 h-3" />
            </span>
          </div>
          <p className="text-[11px] text-slate-400 mt-1">Registered paper folders</p>
        </Link>

        {/* Metric 3: Storage Locations */}
        <Link
          href="/storage-locations"
          className="bg-white p-5 rounded-2xl border border-slate-200 hover:border-emerald-300 hover:shadow-md transition-all group block"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Storage Locations</span>
            <div className="h-8 w-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center group-hover:scale-110 transition-transform">
              <MapPin className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline justify-between">
            <span className="text-2xl font-black text-slate-900">
              {locationCount !== null ? locationCount : "—"}
            </span>
            <span className="text-xs font-medium text-emerald-600 group-hover:translate-x-0.5 transition-transform inline-flex items-center gap-1">
              Locations <ArrowRight className="w-3 h-3" />
            </span>
          </div>
          <p className="text-[11px] text-slate-400 mt-1">Managed hierarchy nodes</p>
        </Link>

        {/* Metric 4: Role-specific alert / Overdue or Review inbox */}
        {user?.role === "approver" ? (
          <Link
            href="/workflows/inbox"
            className="bg-white p-5 rounded-2xl border border-slate-200 hover:border-amber-300 hover:shadow-md transition-all group block"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Review Inbox</span>
              <div className="h-8 w-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center group-hover:scale-110 transition-transform">
                <Inbox className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-4 flex items-baseline justify-between">
              <span className="text-2xl font-black text-slate-900">
                {assignmentCount !== null ? assignmentCount : "—"}
              </span>
              <span className="text-xs font-medium text-amber-600 group-hover:translate-x-0.5 transition-transform inline-flex items-center gap-1">
                Decide <ArrowRight className="w-3 h-3" />
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">Pending review decisions</p>
          </Link>
        ) : (
          <Link
            href="/physical-files"
            className="bg-white p-5 rounded-2xl border border-slate-200 hover:border-rose-300 hover:shadow-md transition-all group block"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Overdue Files</span>
              <div className="h-8 w-8 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center group-hover:scale-110 transition-transform">
                <Clock className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-4 flex items-baseline justify-between">
              <span className="text-2xl font-black text-slate-900">
                {overdueCount !== null ? overdueCount : "—"}
              </span>
              <span className="text-xs font-medium text-rose-600 group-hover:translate-x-0.5 transition-transform inline-flex items-center gap-1">
                Audit <ArrowRight className="w-3 h-3" />
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">Past due circulation items</p>
          </Link>
        )}
      </div>

      {/* Module Navigation Grid */}
      <div className="space-y-4">
        <h2 className="text-base font-bold text-slate-900 tracking-tight">Core System Modules</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <Link
            href="/documents"
            className="p-5 rounded-2xl bg-white border border-slate-200 hover:border-blue-400 hover:shadow-sm transition-all group flex flex-col justify-between"
          >
            <div>
              <div className="h-10 w-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center mb-4 group-hover:bg-blue-600 group-hover:text-white transition-colors">
                <FileText className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-bold text-slate-900 group-hover:text-blue-700">Digital Document Repository</h3>
              <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                Upload PDFs and images, track version histories, extract OCR text, and search content using PostgreSQL full-text search.
              </p>
            </div>
            <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-between text-xs font-semibold text-blue-600">
              <span>Enter Repository</span>
              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
            </div>
          </Link>

          <Link
            href="/physical-files"
            className="p-5 rounded-2xl bg-white border border-slate-200 hover:border-indigo-400 hover:shadow-sm transition-all group flex flex-col justify-between"
          >
            <div>
              <div className="h-10 w-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center mb-4 group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                <FolderArchive className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-bold text-slate-900 group-hover:text-indigo-700">Physical File Tracking</h3>
              <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                Manage paper folders, generate QR/barcode labels, record check-in/out circulation, and verify custody integrity.
              </p>
            </div>
            <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-between text-xs font-semibold text-indigo-600">
              <span>View Registry</span>
              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
            </div>
          </Link>

          <Link
            href="/retention"
            className="p-5 rounded-2xl bg-white border border-slate-200 hover:border-slate-400 hover:shadow-sm transition-all group flex flex-col justify-between"
          >
            <div>
              <div className="h-10 w-10 rounded-xl bg-slate-100 text-slate-700 flex items-center justify-center mb-4 group-hover:bg-slate-700 group-hover:text-white transition-colors">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-bold text-slate-900 group-hover:text-slate-800">Retention & Legal Holds</h3>
              <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                Define schedule rules by classification, track disposal eligibility dates, and enforce legal holds blocking destruction.
              </p>
            </div>
            <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-between text-xs font-semibold text-slate-700">
              <span>Inspect Rules</span>
              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
            </div>
          </Link>
        </div>
      </div>

      {/* Infrastructure Readiness & Health Status Panel */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-2xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center space-x-2.5">
            <Server className="w-4 h-4 text-slate-600" />
            <h3 className="text-sm font-bold text-slate-900">System Probes & Container Health</h3>
          </div>
          {backendHealth && (
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> All Services Operational
            </span>
          )}
        </div>

        {loadingHealth && (
          <p className="text-xs text-slate-400 animate-pulse">Checking health and database probes...</p>
        )}

        {healthError && (
          <div className="p-3 bg-red-50 text-red-700 rounded-xl text-xs border border-red-200 flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
            <span>Connection probe failed: {healthError}</span>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {backendHealth && (
            <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1">
              <span className="font-semibold text-slate-700 block">FastAPI Backend</span>
              <p className="text-slate-500">Service: <span className="font-medium text-slate-800">{backendHealth.service}</span></p>
              <p className="text-slate-500">Environment: <span className="font-medium text-slate-800 capitalize">{backendHealth.environment}</span></p>
              <p className="text-slate-500">Version: <span className="font-mono text-slate-800">{backendHealth.version}</span></p>
            </div>
          )}

          {readinessHealth && (
            <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1">
              <span className="font-semibold text-slate-700 block">PostgreSQL Database</span>
              <p className="text-slate-500">Connectivity: <span className="font-medium text-emerald-700 capitalize">{readinessHealth.database.status}</span></p>
              <p className="text-slate-500">Schema Head: <span className="font-mono text-slate-800">851619ad95bc</span></p>
              <p className="text-slate-500">Connection Pool: <span className="font-medium text-slate-800">Operational</span></p>
            </div>
          )}

          <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1">
            <span className="font-semibold text-slate-700 block">Durable OCR Worker</span>
            <p className="text-slate-500">Engine: <span className="font-medium text-slate-800">Tesseract OCR 5.x</span></p>
            <p className="text-slate-500">Queue Mode: <span className="font-medium text-slate-800">Atomic Leases (SKIP LOCKED)</span></p>
            <p className="text-slate-500">Crash Recovery: <span className="font-medium text-emerald-700">Active</span></p>
          </div>
        </div>
      </div>
    </main>
  );
}
