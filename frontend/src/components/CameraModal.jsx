import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Camera, MapPinned, Radio, Send, X } from "lucide-react";
import { C } from "../theme.js";

// Camera details modal (README §4.6) — stream resolution, FPS, protocol
// (RTSP / WebRTC) and location. Also the hand-off point into Vishakha's GIS
// map (README §13 — "camera links route directly into your GIS Map view").
export default function CameraModal({ cam, onClose }) {
  const navigate = useNavigate();

  useEffect(() => {
    if (!cam) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cam, onClose]);

  if (!cam) return null;

  const rtsp = cam.streamUrl || `rtsp://sentinel.guj/${cam.id.toLowerCase()}/live`;
  const meta = [
    ["Zone", cam.zone],
    ["Status", String(cam.status).toUpperCase()],
    ["Protocol", cam.protocol || "RTSP"],
    ["Resolution", cam.resolution || "—"],
    ["FPS", cam.fps ?? "—"],
    ["Lat / Lng", cam.lat != null && cam.lng != null ? `${cam.lat}, ${cam.lng}` : "—"],
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
        aria-label={`${cam.id} ${cam.name}`}
        style={{
          background: C.surface,
          border: `1px solid ${C.accent}`,
          borderRadius: 8,
          width: "min(520px, 100%)",
          maxHeight: "90vh",
          overflowY: "auto",
          padding: 16,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <span style={{ color: C.accent, fontWeight: 700 }}>
            {cam.id} — {cam.name}
          </span>
          <button
            onClick={onClose}
            style={{ background: "transparent", border: "none", color: C.muted, cursor: "pointer", display: "flex" }}
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div
          style={{
            background: "#000",
            borderRadius: 4,
            height: 160,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            position: "relative",
            overflow: "hidden",
          }}
        >
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(135deg, #071420, #0A1E32)" }} />
          <div style={{ position: "relative", textAlign: "center" }}>
            <Radio size={26} color={C.feedText} />
            <div style={{ color: C.feedMuted, fontSize: 11, marginTop: 6 }}>
              {cam.protocol === "WebRTC" ? "WebRTC" : "RTSP"} stream renders here in production
            </div>
            <div style={{ color: C.feedText, fontSize: 10, fontFamily: "monospace", marginTop: 4 }}>{rtsp}</div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, marginTop: 12 }}>
          {meta.map(([k, v]) => (
            <div key={k} style={{ background: C.panel, borderRadius: 4, padding: "6px 10px" }}>
              <div style={{ color: C.muted, fontSize: 9, textTransform: "uppercase", letterSpacing: 1 }}>{k}</div>
              <div style={{ color: C.text, fontSize: 12, marginTop: 2, wordBreak: "break-word" }}>{v}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
          <button style={actionBtn}>
            <Camera size={12} /> Snapshot
          </button>
          <button style={actionBtn}>
            <Send size={12} /> Dispatch
          </button>
          <button
            style={{ ...actionBtn, borderColor: C.accent, color: C.accent }}
            onClick={() => navigate(`/investigation?cam=${encodeURIComponent(cam.id)}`)}
          >
            <MapPinned size={12} /> Open in Investigation
          </button>
        </div>
      </div>
    </div>
  );
}

const actionBtn = {
  flex: "1 1 120px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 6,
  background: C.panel,
  border: `1px solid ${C.border}`,
  color: C.text,
  borderRadius: 4,
  padding: "7px 8px",
  fontSize: 11,
  cursor: "pointer",
};
