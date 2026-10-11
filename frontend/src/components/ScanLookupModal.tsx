"use client";

import React, { useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";
import { api, ApiError } from "@/lib/api";
import { PhysicalFileDetail } from "@/types/physical_file";
import {
  QrCode,
  Camera,
  Search,
  X,
  AlertCircle,
  RefreshCw,
  Keyboard,
  Info,
} from "lucide-react";

interface ScanLookupModalProps {
  onClose: () => void;
  onFileFound: (file: PhysicalFileDetail) => void;
}

export function ScanLookupModal({ onClose, onFileFound }: ScanLookupModalProps) {
  const [activeTab, setActiveTab] = useState<"camera" | "manual">("camera");
  const [manualCode, setManualCode] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Camera State
  const [cameraLoading, setCameraLoading] = useState<boolean>(false);
  const [cameraPermissionError, setCameraPermissionError] = useState<string | null>(null);
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [cameras, setCameras] = useState<Array<{ id: string; label: string }>>([]);
  const [selectedCameraId, setSelectedCameraId] = useState<string>("");

  const html5QrCodeRef = useRef<Html5Qrcode | null>(null);
  const isMountedRef = useRef<boolean>(true);
  const scannerContainerId = "qr-reader-viewport";

  // Perform backend lookup
  const handlePerformLookup = async (codeToLookup: string) => {
    const trimmed = codeToLookup.trim();
    if (!trimmed) {
      setError("Please provide a file reference or barcode.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // If camera is scanning, stop it before presenting result
      if (html5QrCodeRef.current && isScanning) {
        await html5QrCodeRef.current.stop().catch(() => {});
        if (isMountedRef.current) {
          setIsScanning(false);
        }
      }

      const foundFile = await api.lookupPhysicalFile(trimmed);
      onFileFound(foundFile);
      onClose();
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 404) {
        setError(
          `Record not found for "${trimmed}". Verify the reference or check your department permissions.`
        );
      } else {
        setError(err.message || "Failed to lookup physical file.");
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  };

  // Start Camera QR Scanner with robust fallback cascade
  const startCamera = async (overrideCameraId?: string) => {
    if (!isMountedRef.current) return;
    setCameraPermissionError(null);
    setError(null);
    setCameraLoading(true);

    // 1. Secure context check (WebRTC getUserMedia requires HTTPS or localhost)
    if (typeof window !== "undefined" && !window.isSecureContext) {
      setCameraPermissionError(
        "Camera video streaming requires a secure context (HTTPS or http://localhost:3000). Please access the system via localhost or enable HTTPS."
      );
      setCameraLoading(false);
      return;
    }

    // 2. Browser mediaDevices support check
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setCameraPermissionError(
        "Camera video capture is not supported by your browser. Please use Google Chrome, Microsoft Edge, or Mozilla Firefox, or use the Manual / USB Scanner tab."
      );
      setCameraLoading(false);
      return;
    }

    try {
      // If instance exists and is running, stop it first
      if (html5QrCodeRef.current) {
        try {
          if (html5QrCodeRef.current.isScanning) {
            await html5QrCodeRef.current.stop();
          }
        } catch (_) {}
      } else {
        html5QrCodeRef.current = new Html5Qrcode(scannerContainerId);
      }

      // Try discovering available video cameras
      let deviceList: Array<{ id: string; label: string }> = [];
      try {
        deviceList = await Html5Qrcode.getCameras();
        if (deviceList && deviceList.length > 0 && isMountedRef.current) {
          setCameras(deviceList);
        }
      } catch (_) {
        // getCameras() may fail or return empty before permission is granted; we continue to .start()
      }

      const scanConfig = {
        fps: 10,
        qrbox: { width: 250, height: 250 },
        aspectRatio: 1.0,
      };

      const onScanSuccess = (decodedText: string) => {
        handlePerformLookup(decodedText);
      };

      const targetId = overrideCameraId || selectedCameraId;

      if (targetId && deviceList.some((d) => d.id === targetId)) {
        // Start explicit user-selected camera
        await html5QrCodeRef.current.start(targetId, scanConfig, onScanSuccess, () => {});
      } else if (deviceList.length > 0) {
        // Prefer rear/environment camera if available, otherwise first webcam
        const preferred =
          deviceList.find((c) =>
            /back|rear|environment/i.test(c.label)
          ) || deviceList[0];
        if (isMountedRef.current) {
          setSelectedCameraId(preferred.id);
        }
        await html5QrCodeRef.current.start(preferred.id, scanConfig, onScanSuccess, () => {});
      } else {
        // No cameras enumerated yet: start with constraints to trigger native browser permission prompt!
        try {
          // Attempt environment facing mode first (mobile/tablet rear camera)
          await html5QrCodeRef.current.start(
            { facingMode: "environment" },
            scanConfig,
            onScanSuccess,
            () => {}
          );
        } catch (envErr: any) {
          // Fallback to user facing mode (standard laptops/desktops with front webcam)
          await html5QrCodeRef.current.start(
            { facingMode: "user" },
            scanConfig,
            onScanSuccess,
            () => {}
          );
        }

        // Now that permission has been granted, refresh the camera device list
        try {
          const refreshed = await Html5Qrcode.getCameras();
          if (refreshed && refreshed.length > 0 && isMountedRef.current) {
            setCameras(refreshed);
            setSelectedCameraId(refreshed[0].id);
          }
        } catch (_) {}
      }

      if (isMountedRef.current) {
        setIsScanning(true);
        setCameraPermissionError(null);
      }
    } catch (err: any) {
      console.warn("Camera start failed:", err);
      if (!isMountedRef.current) return;

      setIsScanning(false);
      const errName = err?.name || "";
      const errMsg = (err?.message || "").toLowerCase();

      if (
        errName === "NotAllowedError" ||
        errName === "PermissionDeniedError" ||
        errMsg.includes("permission denied") ||
        errMsg.includes("permission dismissed") ||
        errMsg.includes("not allowed")
      ) {
        setCameraPermissionError(
          "Camera access is blocked. Click the camera or lock icon in your browser address bar (top-left), set Camera to 'Allow', and click 'Retry Camera'."
        );
      } else if (
        errName === "NotFoundError" ||
        errName === "DevicesNotFoundError" ||
        errMsg.includes("no camera") ||
        errMsg.includes("requested device not found")
      ) {
        setCameraPermissionError(
          "No webcam hardware detected on this machine. Please plug in a USB camera, or use the 'Manual / USB Scanner' tab."
        );
      } else if (
        errName === "NotReadableError" ||
        errName === "TrackStartError" ||
        errMsg.includes("could not start video source") ||
        errMsg.includes("source unavailable")
      ) {
        setCameraPermissionError(
          "Camera is currently occupied by another program (Zoom, Teams, Meet, or another browser tab). Close other camera applications and retry."
        );
      } else {
        setCameraPermissionError(
          err?.message ||
            "Unable to activate camera. Please ensure permissions are granted or use the Manual / USB Scanner tab."
        );
      }
    } finally {
      if (isMountedRef.current) {
        setCameraLoading(false);
      }
    }
  };

  // Stop camera helper
  const stopCamera = async () => {
    if (html5QrCodeRef.current && isScanning) {
      try {
        await html5QrCodeRef.current.stop();
      } catch (e) {
        // Ignored
      }
      if (isMountedRef.current) {
        setIsScanning(false);
      }
    }
  };

  // Mount & tab effect for camera
  useEffect(() => {
    isMountedRef.current = true;

    if (activeTab === "camera") {
      startCamera();
    } else {
      stopCamera();
    }

    return () => {
      isMountedRef.current = false;
      if (html5QrCodeRef.current) {
        if (html5QrCodeRef.current.isScanning) {
          html5QrCodeRef.current.stop().catch(() => {}).finally(() => {
            html5QrCodeRef.current?.clear();
          });
        } else {
          try {
            html5QrCodeRef.current.clear();
          } catch (_) {}
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 max-w-lg w-full overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
          <div className="flex items-center space-x-2">
            <QrCode className="w-5 h-5 text-blue-600" />
            <h3 className="text-base font-bold text-slate-900">
              Identify & Scan Physical File
            </h3>
          </div>
          <button
            onClick={() => {
              stopCamera();
              onClose();
            }}
            className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg transition-colors"
            aria-label="Close scanner"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Mode Selector Tabs */}
        <div className="flex border-b border-slate-200 bg-slate-100/60 px-6 pt-2">
          <button
            type="button"
            onClick={() => {
              setError(null);
              setActiveTab("camera");
            }}
            className={`flex items-center space-x-2 pb-3 px-3 text-sm font-semibold border-b-2 transition-colors ${
              activeTab === "camera"
                ? "border-blue-600 text-blue-600 bg-transparent"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            <Camera className="w-4 h-4" />
            <span>Camera Scanner</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setError(null);
              setActiveTab("manual");
            }}
            className={`flex items-center space-x-2 pb-3 px-3 text-sm font-semibold border-b-2 transition-colors ${
              activeTab === "manual"
                ? "border-blue-600 text-blue-600 bg-transparent"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            <Keyboard className="w-4 h-4" />
            <span>Manual / USB Scanner</span>
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-4">
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {activeTab === "camera" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-slate-500">
                  Point your device camera at the printed QR code or label barcode.
                </p>
                {cameras.length > 1 && (
                  <select
                    value={selectedCameraId}
                    onChange={(e) => {
                      const newId = e.target.value;
                      setSelectedCameraId(newId);
                      startCamera(newId);
                    }}
                    className="text-xs border border-slate-300 rounded-md px-2 py-1 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-blue-500 max-w-[170px] truncate"
                    title="Switch Camera Device"
                  >
                    {cameras.map((c, idx) => (
                      <option key={c.id} value={c.id}>
                        {c.label || `Camera ${idx + 1}`}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Viewport container: Always kept mounted so DOM reference is permanent */}
              <div className="relative bg-slate-950 rounded-xl overflow-hidden aspect-square max-w-[320px] mx-auto flex items-center justify-center border border-slate-800 shadow-inner">
                <div
                  id={scannerContainerId}
                  className={`w-full h-full ${cameraPermissionError ? "hidden" : "block"}`}
                />

                {/* Initializing / Starting state */}
                {cameraLoading && (
                  <div className="absolute inset-0 bg-slate-900/85 backdrop-blur-xs flex flex-col items-center justify-center text-white space-y-2.5 p-4 text-center">
                    <RefreshCw className="w-8 h-8 animate-spin text-blue-400" />
                    <p className="text-sm font-semibold">Starting Camera...</p>
                    <p className="text-xs text-slate-300 max-w-xs">
                      If prompted by your browser, please click <span className="font-bold text-white">&quot;Allow&quot;</span> to enable camera access.
                    </p>
                  </div>
                )}

                {/* Error overlay with Retry & Manual fallback */}
                {cameraPermissionError && !cameraLoading && (
                  <div className="absolute inset-0 bg-slate-900/95 flex flex-col items-center justify-center text-white p-5 text-center space-y-3">
                    <div className="w-12 h-12 rounded-full bg-amber-500/20 flex items-center justify-center text-amber-400">
                      <Camera className="w-6 h-6" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-amber-300">Camera Unavailable</p>
                      <p className="text-xs text-slate-300 mt-1.5 leading-relaxed">
                        {cameraPermissionError}
                      </p>
                    </div>
                    <div className="flex flex-col sm:flex-row items-center justify-center gap-2 pt-1 w-full max-w-xs">
                      <button
                        type="button"
                        onClick={() => startCamera()}
                        className="w-full sm:w-auto px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                        Retry Camera
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveTab("manual")}
                        className="w-full sm:w-auto px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg text-xs font-medium transition-colors"
                      >
                        Use Manual Lookup
                      </button>
                    </div>
                  </div>
                )}

                {/* Resolving record loader */}
                {loading && (
                  <div className="absolute inset-0 bg-slate-900/80 flex flex-col items-center justify-center text-white space-y-2">
                    <RefreshCw className="w-8 h-8 animate-spin text-blue-400" />
                    <span className="text-xs font-semibold">Resolving Record...</span>
                  </div>
                )}
              </div>

              {/* Helpful tips box */}
              <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-[11px] text-slate-600 flex items-start gap-2">
                <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                <p>
                  <strong className="font-semibold text-slate-700">Tip:</strong> Hold the QR code flat about 6-10 inches from the camera lens under good lighting. You can also switch to the Manual tab at any time to type the code or use a barcode scanner gun.
                </p>
              </div>
            </div>
          )}

          {activeTab === "manual" && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handlePerformLookup(manualCode);
              }}
              className="space-y-4"
            >
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  File Reference, External Barcode, or Scanned URL
                </label>
                <div className="relative">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="text"
                    autoFocus
                    placeholder="e.g. PHY-2026-A1B2C3D4 or scan with USB reader"
                    value={manualCode}
                    onChange={(e) => setManualCode(e.target.value)}
                    className="w-full pl-9 pr-4 py-2.5 text-sm font-mono border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <p className="text-[11px] text-slate-400 mt-1">
                  Accepts standard references (PHY-YYYY-XXXXXXXX), external barcodes, or complete system URLs. Handheld USB barcode scanners will automatically submit when hitting Enter.
                </p>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  type="submit"
                  disabled={loading || !manualCode.trim()}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
                >
                  {loading ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Looking Up...
                    </>
                  ) : (
                    <>
                      <Search className="w-4 h-4" />
                      Lookup File
                    </>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex justify-end">
          <button
            type="button"
            onClick={() => {
              stopCamera();
              onClose();
            }}
            className="px-4 py-1.5 border border-slate-300 rounded-lg text-xs font-medium text-slate-700 hover:bg-white"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
