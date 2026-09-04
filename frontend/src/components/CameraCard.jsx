import { useEffect, useState } from "react";
import { C } from "../theme.js";
import Pulse from "./Pulse.jsx";
import { evidenceUrl } from "../services/api.js";

const STATUS_COLOR = { active: C.green, alert: C.red, offline: C.muted };

// Live camera preview card with status badge + metadata overlay (README §4.3).
// The Sentinel RTSP feeds require Basic-auth the browser cannot supply and
// have no CORS-open HLS path, so raw video is not embedded here (per spec: no
// exposing RTSP to the browser, no bespoke streaming stack). Instead, when a
// real AI detection has landed for this camera, its evidence FRAME — the
// actual most recent snapshot pulled from the live feed — is shown as the
// preview, which is the honest signal that this camera is live and being
// analysed right now.
export default function CameraCard({ cam, selected, onClick, preview }) {
  const [now, setNow] = useState(() => new Date());
  const statusColor = STATUS_COLOR[cam.status] || C.muted;
  const isAlert = cam.status === "alert";
  const isOffline = cam.status === "offline";
  const thumb = preview?.id ? evidenceUrl(preview.id) : null;

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div
      onClick={() => onClick?.(cam)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onClick?.(cam)}
      style={{
        background: selected ? C.accentGlow : C.panel,
        border: `1px solid ${selected ? C.accent : isAlert ? C.red : C.border}`,
        borderRadius: 6,
        padding: "10px 12px",
        cursor: "pointer",
        transition: "border-color 0.15s, background 0.15s",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ color: C.accent, fontSize: 11, fontFamily: "monospace", fontWeight: 700 }}>{cam.id}</span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          {isAlert && <Pulse color={C.red} size={7} />}
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: statusColor, display: "inline-block" }} />
        </span>
      </div>

      <div
        style={{
          background: "#000",
          borderRadius: 4,
          height: 64,
          marginBottom: 8,
          position: "relative",
          overflow: "hidden",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {isOffline ? (
          <span style={{ color: C.feedMuted, fontSize: 11 }}>NO SIGNAL</span>
        ) : (
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: thumb
                ? `#000 url(${thumb}) center/cover no-repeat`
                : `linear-gradient(135deg, #071420 60%, ${isAlert ? "#200808" : "#081828"})`,
            }}
          >
            {!thumb && (
              <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: C.feedMuted, fontSize: 9 }}>
                Awaiting first detection…
              </div>
            )}
            <div style={{ position: "absolute", bottom: 4, left: 6, color: C.feedText, fontSize: 9, fontFamily: "monospace", textShadow: "0 1px 2px #000" }}>
              LIVE ● {now.toLocaleTimeString("en-IN", { hour12: false })}
            </div>
            {preview && !isAlert && (
              <div style={{ position: "absolute", top: 4, left: 6, color: C.feedText, fontSize: 9, fontFamily: "monospace", textShadow: "0 1px 2px #000" }}>
                {preview.vehicleType || "vehicle"} · trk {preview.trackId ?? "—"}
              </div>
            )}
            {isAlert && (
              <div style={{ position: "absolute", top: 4, right: 6, color: C.red, fontSize: 9, fontWeight: 700, fontFamily: "monospace" }}>
                ⚠ ALERT
              </div>
            )}
          </div>
        )}
      </div>

      <div style={{ color: C.text, fontSize: 12, fontWeight: 600 }}>{cam.name}</div>
      <div style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>
        {cam.zone} · {String(cam.status).toUpperCase()}
      </div>
    </div>
  );
}
