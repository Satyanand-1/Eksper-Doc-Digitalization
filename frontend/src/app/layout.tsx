import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "EKSPER - Electronic Document & Records Management",
  description: "EKSPER Electronic Document and Records Management System",
};

import { AuthProvider } from "@/context/AuthContext";
import { NotificationProvider } from "@/context/NotificationContext";
import { Sidebar } from "@/components/Sidebar";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 antialiased text-slate-900">
        <AuthProvider>
          <NotificationProvider>
            <div className="min-h-screen flex flex-col md:flex-row">
              <Sidebar />
              <div className="flex-1 min-w-0 flex flex-col bg-slate-50 w-full overflow-x-hidden">
                {children}
              </div>
            </div>
          </NotificationProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
