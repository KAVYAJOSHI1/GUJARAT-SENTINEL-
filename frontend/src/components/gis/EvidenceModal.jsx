import { useEffect, useState } from "react";
import { Camera, MapPin, X } from "lucide-react";
import { C } from "../../theme.js";
import { evidenceUrl } from "../../services/investigationApi.js";
import { useMediaTicket } from "../../services/mediaTicket.js";
import { pickFallbackFrame } from "../../lib/evidenceFallback.js";

// Evidence Viewer Modal (DEVELOPER_README §14.8): full-frame snapshot, cropped
// plate image, camera metadata and OCR confidence. Follows the same overlay
// pattern as Isha's components/CameraModal.jsx (Escape to close, role="dialog").
function ImgWithFallback({ src, fallbackKey, cameraCode, alt, height }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);

  const shown = !src || failed ? pickFallbackFrame(fallbackKey, cameraCode) : src;
  return (
    <img
      src={shown}
      alt={alt}
      onError={() => setFailed(true)}
      style={{ width: "100%", height, objectFit: "cover", borderRadius: 4, background: "#000", display: "block" }}
    />
  );
}

export default function EvidenceModal({ sighting, plate, onClose }) {
  useEffect(() => {
    if (!sighting) return undefined;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sighting, onClose]);

  // Re-render the instant a media ticket becomes available (e.g. right after
  // a hard page reload) so `snapshot` below picks up the ticketed URL instead
  // of staying on the tokenless one ImgWithFallback already marked "failed".
  const mediaTicket = useMediaTicket();

  if (!sighting) return null;

  // Prefer the backend evidence proxy: it resolves both object-storage and
  // local file:// snapshot references (a bare file:// URL can't be loaded by
  // the browser directly). Fall back to whatever raw URL the sighting carries
  // only when there's no event id to proxy through.
  const snapshot = (mediaTicket && evidenceUrl(sighting.eventId)) || sighting.snapshotUrl;
  const crop = sighting.plateCropUrl || "";
  const conf = Number.isFinite(sighting.ocrConfidence)
    ? `${(sighting.ocrConfidence * 100).toFixed(1)}%`
    : "—";
  const ts = sighting.timestamp
    ? new Date(sighting.timestamp).toLocaleString("en-IN", { hour12: false })
    : "—";

  const meta = [
    ["Camera", `${sighting.cameraId} — ${sighting.cameraName}`],
    ["Timestamp", ts],
    ["Coordinates", sighting.lat != null ? `${sighting.lat.toFixed(5)}, ${sighting.lng.toFixed(5)}` : "—"],
    ["Vehicle type", sighting.vehicleType || "—"],
    ["OCR confidence", conf],
    ["Event ID", sighting.eventId],
  ];

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(6,9,13,0.72)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 300,
        padding: 20,
        animation: "fadeIn 0.15s ease-out",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Evidence for ${plate} at ${sighting.cameraName}`}
        style={{
          background: C.surface,
          border: `1px solid ${C.accent}`,
          borderRadius: 8,
          width: "min(560px, 100%)",
          maxHeight: "90vh",
          overflowY: "auto",
          padding: 16,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <span style={{ color: C.accent, fontWeight: 700, display: "flex", alignItems: "center", gap: 6 }}>
            <Camera size={14} /> Evidence — {plate}
          </span>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{ background: "transparent", border: "none", color: C.muted, cursor: "pointer", display: "flex" }}
          >
            <X size={16} />
          </button>
        </div>

        <ImgWithFallback src={snapshot} fallbackKey={sighting.eventId || plate} cameraCode={sighting.cameraId} alt="Full-frame evidence snapshot" height={220} />

        <div style={{ marginTop: 12 }}>
          <div style={{ color: C.muted, fontSize: 9, textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>
            Cropped plate
          </div>
          <ImgWithFallback src={crop} fallbackKey={(sighting.eventId || plate) + "-crop"} cameraCode={sighting.cameraId} alt="Cropped number plate" height={64} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8, marginTop: 12 }}>
          {meta.map(([k, v]) => (
            <div key={k} style={{ background: C.panel, borderRadius: 4, padding: "6px 10px" }}>
              <div style={{ color: C.muted, fontSize: 9, textTransform: "uppercase", letterSpacing: 1 }}>{k}</div>
              <div style={{ color: C.text, fontSize: 12, marginTop: 2, wordBreak: "break-word" }}>{v}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 12, color: C.muted, fontSize: 11 }}>
          <MapPin size={12} color={C.accent} />
          Snapshot served from evidence store · {sighting.eventId}
        </div>
      </div>
    </div>
  );
}
