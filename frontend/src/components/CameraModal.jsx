import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, Camera, MapPinned, Radio, Send, X } from "lucide-react";
import { C } from "../theme.js";
import { cameraHealthHistory } from "../services/opsApi.js";
import { fmtDateTime } from "../utils/datetime.js";
import CameraPlayer from "./camera/CameraPlayer.jsx";

// Camera details modal (README §4.6) — stream resolution, FPS, protocol
// (RTSP / WebRTC) and location. Also the hand-off point into Vishakha's GIS
// map (README §13 — "camera links route directly into your GIS Map view").
export default function CameraModal({ cam, onClose }) {
  const navigate = useNavigate();
  const [history, setHistory] = useState(null);

  useEffect(() => {
    if (!cam) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cam, onClose]);

  useEffect(() => {
    setHistory(null);
    if (cam?.uuid) {
      cameraHealthHistory(cam.uuid).then(setHistory).catch(() => setHistory({ transitions: [] }));
    }
  }, [cam?.uuid]);

  if (!cam) return null;

  const rtsp = cam.streamUrl || `rtsp://sentinel.guj/${cam.id.toLowerCase()}/live`;
  const meta = [
    ["Code", cam.code || cam.id],
    ["Status", String(cam.status).toUpperCase()],
    ["Location", cam.locationDesc || cam.zone || "—"],
    ["FPS", cam.fps ?? "—"],
    ["Last frame", cam.healthUpdatedAt ? fmtDateTime(cam.healthUpdatedAt) : "no telemetry"],
    ["Last detection", cam.lastDetectionAt ? fmtDateTime(cam.lastDetectionAt) : "—"],
    ["AI status", cam.lastDetectionAt ? "PROCESSING" : "NO DATA"],
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

        {(cam.uuid || cam.id) ? (
          <CameraPlayer cameraId={cam.uuid || cam.id} height={200} />
        ) : (
          <div style={{ background: "#000", borderRadius: 4, height: 160, display: "flex", alignItems: "center", justifyContent: "center", color: C.muted, fontSize: 11 }}>
            No camera id
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, marginTop: 12 }}>
          {meta.map(([k, v]) => (
            <div key={k} style={{ background: C.panel, borderRadius: 4, padding: "6px 10px" }}>
              <div style={{ color: C.muted, fontSize: 9, textTransform: "uppercase", letterSpacing: 1 }}>{k}</div>
              <div style={{ color: C.text, fontSize: 12, marginTop: 2, wordBreak: "break-word" }}>{v}</div>
            </div>
          ))}
        </div>

        {history && history.transitions && (
          <div style={{ marginTop: 12, background: C.panel, borderRadius: 4, padding: "8px 10px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, color: C.muted, fontSize: 9, textTransform: "uppercase", letterSpacing: 1, marginBottom: 6 }}>
              <Activity size={11} /> Health history {history.total ? `(${history.total})` : ""}
            </div>
            {history.transitions.length === 0 ? (
              <div style={{ color: C.dim, fontSize: 10 }}>No status transitions recorded.</div>
            ) : (
              history.transitions.slice(0, 8).map((t) => (
                <div key={t.id} style={{ display: "flex", gap: 8, fontSize: 10, alignItems: "baseline" }}>
                  <span style={{ color: C.dim, fontFamily: "monospace", minWidth: 128 }}>{fmtDateTime(t.detected_at)}</span>
                  <span style={{ color: C.muted }}>{t.previous_status || "—"}</span>
                  <span style={{ color: C.dim }}>→</span>
                  <span style={{ color: t.status === "ONLINE" ? C.green : t.status === "OFFLINE" ? C.red : C.amber, fontWeight: 700 }}>{t.status}</span>
                  <span style={{ color: C.dim, marginLeft: "auto" }}>{t.source}</span>
                </div>
              ))
            )}
          </div>
        )}

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
