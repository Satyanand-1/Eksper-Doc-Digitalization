import Link from "next/link";
import { FileQuestion, Home, ArrowLeft } from "lucide-react";

export default function NotFound() {
  return (
    <main className="min-h-[75vh] flex items-center justify-center px-4 py-16">
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8 sm:p-12 max-w-lg w-full text-center">
        <div className="h-16 w-16 bg-blue-50 text-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-6 border border-blue-100">
          <FileQuestion className="w-8 h-8" />
        </div>
        
        <span className="inline-block px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 mb-3">
          Error 404
        </span>
        
        <h1 className="text-2xl font-bold text-slate-900 mb-2">
          Page Not Found
        </h1>
        
        <p className="text-sm text-slate-500 mb-8 leading-relaxed">
          The requested page or record could not be found. It may have been moved, archived, or you may lack authorized credentials to view it.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link
            href="/"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 text-xs font-semibold text-white bg-blue-600 rounded-xl hover:bg-blue-700 transition-colors shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            <Home className="w-4 h-4" />
            Return to Dashboard
          </Link>
          <Link
            href="/documents"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 text-xs font-semibold text-slate-700 bg-white rounded-xl hover:bg-slate-50 border border-slate-300 transition-colors shadow-2xs focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2"
          >
            <ArrowLeft className="w-4 h-4" />
            Browse Documents
          </Link>
        </div>
      </div>
    </main>
  );
}
