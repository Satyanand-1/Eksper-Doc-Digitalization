"use client";

import React, { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import JsBarcode from "jsbarcode";
import { PhysicalFileDetail, PhysicalFileSummary } from "@/types/physical_file";
import { api } from "@/lib/api";
import { Printer, X, CheckCircle, AlertCircle, Copy, Check } from "lucide-react";

interface PrintLabelModalProps {
  file: PhysicalFileDetail | PhysicalFileSummary;
  onClose: () => void;
}

export function PrintLabelModal({ file, onClose }: PrintLabelModalProps) {
  const [qrDataUrl, setQrDataUrl] = useState<string>("");
  const [qrError, setQrError] = useState<string | null>(null);
  const [auditStatus, setAuditStatus] = useState<"idle" | "logging" | "logged" | "failed">("idle");
  const [copied, setCopied] = useState<boolean>(false);
  const barcodeSvgRef = useRef<SVGSVGElement | null>(null);

  // Generate QR and Barcode on mount
  useEffect(() => {
    // 1. Generate QR Code containing reference (or deep-link payload)
    // We encode the clean file reference string: PHY-YYYY-XXXXXXXX
    QRCode.toDataURL(
      file.file_reference,
      {
        width: 160,
        margin: 1,
        color: {
          dark: "#000000",
          light: "#ffffff",
        },
      },
      (err, url) => {
        if (err) {
          console.error("Failed to generate QR code:", err);
          setQrError("Failed to render QR Code.");
        } else {
          setQrDataUrl(url);
        }
      }
    );

    // 2. Generate Code 128 Barcode via JsBarcode
    if (barcodeSvgRef.current) {
      try {
        JsBarcode(barcodeSvgRef.current, file.file_reference, {
          format: "CODE128",
          width: 1.8,
          height: 48,
          displayValue: true,
          font: "monospace",
          fontSize: 12,
          textMargin: 3,
          margin: 4,
        });
      } catch (err) {
        console.error("Failed to generate barcode:", err);
      }
    }
  }, [file.file_reference]);

  // Handle Print Action with Audit Logging
  const handlePrint = async () => {
    setAuditStatus("logging");
    try {
      await api.recordLabelPrint({
        file_ids: [file.id],
        label_format: "standard_badge",
      });
      setAuditStatus("logged");
    } catch (err) {
      console.warn("Could not log print audit:", err);
      setAuditStatus("failed");
    }

    // Trigger browser print dialog
    window.print();
  };

  const handleCopyRef = () => {
    navigator.clipboard.writeText(file.file_reference);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
      {/* Modal Container */}
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 max-w-xl w-full overflow-hidden flex flex-col max-h-[92vh]">
        {/* Modal Header - hidden during print */}
        <div className="print:hidden flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
          <div className="flex items-center space-x-2">
            <Printer className="w-5 h-5 text-blue-600" />
            <h3 className="text-base font-bold text-slate-900">
              Print Physical File Label
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg transition-colors"
            aria-label="Close label preview"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body / Label Preview */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1 bg-slate-100 flex flex-col items-center">
          <p className="print:hidden text-xs text-slate-500 text-center max-w-md">
            Below is the print preview formatted for standard adhesive label stickers or index cards.
            Click <strong>Print Label</strong> to open the printer dialog.
          </p>

          {/* Printable Label Badge */}
          <div
            id="printable-label"
            className="bg-white border-2 border-slate-800 rounded-xl p-5 shadow-md w-full max-w-[420px] text-slate-900 print:shadow-none print:border-black print:m-0 print:w-full print:max-w-none"
          >
            {/* Header: EKSPER Identification Header */}
            <div className="flex items-center justify-between border-b-2 border-slate-800 pb-2 mb-3">
              <div>
                <span className="text-[10px] uppercase tracking-wider font-extrabold text-slate-500 block leading-tight">
                  EKSPER Archive Registry
                </span>
                <span className="text-xs font-bold text-slate-900">
                  {file.department}
                </span>
              </div>
              <div className="text-right">
                <span className="text-[10px] uppercase tracking-wider font-semibold text-slate-500 block leading-tight">
                  Class
                </span>
                <span className="text-xs font-bold text-slate-800 uppercase px-1.5 py-0.5 bg-slate-100 border border-slate-300 rounded">
                  {file.classification || "INTERNAL"}
                </span>
              </div>
            </div>

            {/* Core Reference & Title */}
            <div className="mb-3">
              <div className="flex items-baseline justify-between gap-2">
                <h4 className="text-base font-black font-mono tracking-tight text-blue-900 print:text-black">
                  {file.file_reference}
                </h4>
                <button
                  type="button"
                  onClick={handleCopyRef}
                  className="print:hidden text-[11px] text-slate-400 hover:text-slate-700 flex items-center gap-1"
                  title="Copy reference"
                >
                  {copied ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
              <p className="text-sm font-semibold text-slate-800 line-clamp-2 mt-0.5">
                {file.title}
              </p>
              <div className="text-xs text-slate-600 capitalize mt-0.5 flex items-center gap-2">
                <span>Type: {file.record_type.replace("_", " ")}</span>
                {file.external_reference && (
                  <span className="font-mono text-[11px] text-slate-500">
                    • Ext: {file.external_reference}
                  </span>
                )}
              </div>
            </div>

            {/* Codes: QR Code + Barcode 128 */}
            <div className="pt-2 border-t border-slate-300 grid grid-cols-5 gap-3 items-center">
              {/* QR Code Container (2 cols) */}
              <div className="col-span-2 flex flex-col items-center justify-center p-1 bg-white border border-slate-200 rounded">
                {qrDataUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={qrDataUrl}
                    alt={`QR Code for ${file.file_reference}`}
                    className="w-24 h-24 object-contain"
                  />
                ) : qrError ? (
                  <span className="text-[10px] text-red-500">{qrError}</span>
                ) : (
                  <div className="w-24 h-24 bg-slate-100 animate-pulse rounded" />
                )}
                <span className="text-[9px] font-mono text-slate-500 mt-1 uppercase">Scan QR</span>
              </div>

              {/* Barcode 128 SVG Container (3 cols) */}
              <div className="col-span-3 flex flex-col items-center justify-center overflow-hidden">
                <svg
                  ref={barcodeSvgRef}
                  className="w-full max-h-16"
                  aria-label={`Barcode 128 for ${file.file_reference}`}
                />
              </div>
            </div>

            {/* Footer metadata */}
            <div className="mt-3 pt-2 border-t border-slate-200 flex justify-between items-center text-[10px] text-slate-400 font-mono">
              <span>REF ID: {file.id.substring(0, 8)}...</span>
              <span>STATE: {file.is_checked_out ? "CHECKED OUT" : "STORED"}</span>
            </div>
          </div>
        </div>

        {/* Modal Footer - Actions */}
        <div className="print:hidden px-6 py-4 border-t border-slate-200 bg-white flex items-center justify-between">
          <div className="text-xs text-slate-500 flex items-center gap-1.5">
            {auditStatus === "logged" && (
              <span className="text-emerald-600 flex items-center gap-1 font-medium">
                <CheckCircle className="w-3.5 h-3.5" /> Print audited
              </span>
            )}
            {auditStatus === "failed" && (
              <span className="text-amber-600 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5" /> Audit unrecorded
              </span>
            )}
          </div>

          <div className="flex items-center space-x-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handlePrint}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors shadow-sm flex items-center gap-2"
            >
              <Printer className="w-4 h-4" />
              Print Label
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
