import { useEffect, useRef, useState, type ChangeEvent } from "react";

import { Icon } from "../components/ui";
import { decodeBlob, decodeVideoFrame } from "./decode";

/** Synthetic demo QR codes in web/public/demo-qr (decoded for real, like a photo would be). */
export interface QrSample {
  id: string;
  label: string;
  file: string;
  /** Scenario defaults applied with the sample, so the demo story is complete. */
  scenario?: { payer_id: string; beneficiary_age_minutes: number; amount?: number };
}

const MIN_PER_DAY = 60 * 24;
export const QR_SAMPLES: QrSample[] = [
  {
    id: "genuine",
    label: "Tea stall (genuine)",
    file: "/demo-qr/tea-stall-genuine.png",
    scenario: { payer_id: "payer_demo_003", beneficiary_age_minutes: 400 * MIN_PER_DAY, amount: 40 },
  },
  {
    id: "swapped",
    label: "Tea stall (swapped sticker)",
    file: "/demo-qr/tea-stall-swapped.png",
    scenario: { payer_id: "payer_demo_003", beneficiary_age_minutes: 0 },
  },
  {
    id: "rent",
    label: "Landlord rent",
    file: "/demo-qr/rent-landlord.png",
    scenario: { payer_id: "payer_demo_002", beneficiary_age_minutes: 400 * MIN_PER_DAY },
  },
  { id: "link", label: "'KYC update' link", file: "/demo-qr/kyc-link.png" },
];

type Mode = "upload" | "camera" | "samples";
const SCAN_INTERVAL_MS = 200;

function cameraError(err: unknown): string {
  const name = err instanceof DOMException ? err.name : "";
  if (name === "NotAllowedError") return "Camera permission was denied. Upload a photo instead.";
  if (name === "NotFoundError" || name === "OverconstrainedError")
    return "No camera was found on this device. Upload a photo instead.";
  return "The camera couldn't start. Upload a photo instead.";
}

export function QrScanner({
  onResult,
  onClose,
}: {
  onResult: (text: string, sample?: QrSample) => void;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<Mode>("upload");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const cameraAvailable =
    typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

  // Esc closes; focus starts on the close button.
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Camera: start only when the Camera tab is open; always release it.
  useEffect(() => {
    if (mode !== "camera") return;
    let stream: MediaStream | null = null;
    let timer: number | undefined;
    let cancelled = false;
    (async () => {
      try {
        if (!window.isSecureContext) throw new Error("insecure");
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } },
          audio: false,
        });
        if (cancelled || !videoRef.current) return;
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        timer = window.setInterval(() => {
          const video = videoRef.current;
          const text = video ? decodeVideoFrame(video) : null;
          if (text) {
            window.clearInterval(timer);
            onResult(text);
          }
        }, SCAN_INTERVAL_MS);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error && err.message === "insecure"
              ? "The camera needs a secure (https) page. Upload a photo instead."
              : cameraError(err),
          );
      }
    })();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [mode, onResult]);

  async function decode(blob: Blob, sample?: QrSample) {
    setBusy(true);
    setError(null);
    try {
      const text = await decodeBlob(blob);
      if (text) onResult(text, sample);
      else setError("No QR code found in this image. Try a clearer, straight-on photo.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "That image couldn't be read.");
    } finally {
      setBusy(false);
    }
  }

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Please choose an image (PNG or JPEG).");
      return;
    }
    await decode(file);
  }

  async function pickSample(sample: QrSample) {
    try {
      const res = await fetch(sample.file);
      if (!res.ok) throw new Error();
      await decode(await res.blob(), sample);
    } catch {
      setError("The sample QR couldn't be loaded.");
    }
  }

  const tabs: { id: Mode; label: string; icon: string; show: boolean }[] = [
    { id: "upload", label: "Upload photo", icon: "upload", show: true },
    { id: "camera", label: "Camera", icon: "photo_camera", show: cameraAvailable },
    { id: "samples", label: "Sample QRs", icon: "qr_code_2", show: true },
  ];

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div
        className="dialog card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="qr-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="dialog-head">
          <Icon name="qr_code_scanner" className="result-icon" />
          <div>
            <h2 id="qr-title">Scan a QR code</h2>
            <p className="muted small">Read on this device; the image isn't uploaded anywhere.</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="icon-button"
            aria-label="Close"
            onClick={onClose}
          >
            <Icon name="close" />
          </button>
        </div>

        <div className="segmented" role="tablist" aria-label="How to scan">
          {tabs
            .filter((t) => t.show)
            .map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={mode === t.id}
                className={mode === t.id ? "segment active" : "segment"}
                onClick={() => {
                  setError(null);
                  setMode(t.id);
                }}
              >
                <Icon name={t.icon} />
                {t.label}
              </button>
            ))}
        </div>

        <div className="dialog-body">
          {mode === "upload" && (
            <label className="drop">
              <Icon name="add_photo_alternate" className="drop-icon" />
              <span>Choose a photo or screenshot of the QR code</span>
              <input type="file" accept="image/*" onChange={onFile} aria-label="QR image" />
            </label>
          )}
          {mode === "camera" && (
            <div className="camera">
              <video ref={videoRef} muted playsInline aria-label="Camera preview" />
              <span className="camera-frame" aria-hidden="true" />
              <p className="muted small">Point the camera at the QR code.</p>
            </div>
          )}
          {mode === "samples" && (
            <ul className="samples">
              {QR_SAMPLES.map((s) => (
                <li key={s.id}>
                  <button type="button" className="sample" onClick={() => pickSample(s)}>
                    <img src={s.file} alt="" />
                    <span>{s.label}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {busy && <p className="muted small">Reading the QR code…</p>}
          {error && (
            <p className="notice notice-error" role="alert">
              {error}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
