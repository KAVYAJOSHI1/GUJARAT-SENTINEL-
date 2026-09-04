import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Crosshair, MapPinned, Video } from "lucide-react";
import { C, CAMERA_STATUS_COLOR } from "../theme.js";
import Pulse from "./Pulse.jsx";
import { evidenceUrl, mockVideoUrl } from "../services/api.js";

// Live camera preview card with status badge + metadata overlay (README §4.3).
// The Sentinel RTSP feeds require Basic-auth the browser cannot supply and
// have no CORS-open HLS path, so raw video is not embedded here (per spec: no
// exposing RTSP to the browser, no bespoke streaming stack). Instead, when a
// real AI detection has landed for this camera, its evidence FRAME — the
// actual most recent snapshot pulled from the live feed — is shown as the
// preview, which is the honest signal that this camera is live and being
// analysed right now.
export default function CameraCard({ cam, selected, onClick, preview, detectionCount = 0 }) {
  const navigate = useNavigate();
  const [now, setNow] = useState(() => new Date());
  const [videoFailed, setVideoFailed] = useState(false);
  const statusColor = CAMERA_STATUS_COLOR[cam.status] || C.muted;
  const isAlert = cam.status === "alert";
  const isOffline = cam.status === "offline";
  const trackablePlate = preview?.plate && preview.plate !== "UNKNOWN" ? preview.plate : null;
  const thumb = preview?.id ? evidenceUrl(preview.id) : null;
  // MOCK cameras are a local video file -- actually playable in-browser,
  // unlike the real Sentinel RTSP feeds (Basic-auth + no CORS HLS, see the
  // module comment above). Falls back to the evidence-thumbnail look if the
  // clip fails to load for any reason.
  const videoSrc = cam.isMock && !videoFailed ? mockVideoUrl(cam.id) : null;

  useEffect(() => setVideoFailed(false), [cam.id]);

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
        border: `1px solid ${selected ? C.accent : isAlert ? C.amber : C.border}`,
        borderRadius: 6,
        padding: "10px 12px",
        cursor: "pointer",
        transition: "border-color 0.15s, background 0.15s",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ color: C.accent, fontSize: 11, fontFamily: "monospace", fontWeight: 700 }}>{cam.id}</span>
          {/* Unobtrusive REAL-vs-MOCK indicator (README §"Mock cameras"): a
              LOCAL trafficdataset demo feed must never look like a real
              government camera. Real cameras get no badge at all (zero
              visual change from before this existed). */}
          {cam.isMock && (
            <span
              title="Local mock camera — trafficdataset demo source, not a live government feed"
              style={{
                color: C.violet,
                border: `1px solid ${C.violet}`,
                borderRadius: 3,
                padding: "1px 5px",
                fontSize: 8,
                fontWeight: 700,
                letterSpacing: 0.5,
                fontFamily: "monospace",
              }}
            >
              MOCK
            </span>
          )}
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          {isAlert && <Pulse color={C.amber} size={7} />}
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
              background: !videoSrc && thumb
                ? `#000 url(${thumb}) center/cover no-repeat`
                : `linear-gradient(135deg, #071420 60%, ${isAlert ? "#221a06" : "#081828"})`,
            }}
          >
            {videoSrc && (
              <video
                src={videoSrc}
                autoPlay
                loop
                muted
                playsInline
                onError={() => setVideoFailed(true)}
                style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
              />
            )}
            {!videoSrc && !thumb && (
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
              <div style={{ position: "absolute", top: 4, right: 6, color: C.amber, fontSize: 9, fontWeight: 700, fontFamily: "monospace" }}>
                ⚠ INCIDENT
              </div>
            )}
          </div>
        )}
      </div>

      <div style={{ color: C.text, fontSize: 12, fontWeight: 600 }}>{cam.name}</div>
      <div style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>
        {cam.zone} · {String(cam.status).toUpperCase()}
      </div>

      {/* Detection summary (README task §7 — camera grid improvement):
          real counts derived from the already-loaded detection feed, no new
          fetch. Omitted entirely if nothing has been seen on this camera
          yet, rather than printing zeroes for every idle card. */}
      {(detectionCount > 0 || preview) && (
        <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.border}`, fontSize: 10, color: C.muted, display: "flex", flexDirection: "column", gap: 2 }}>
          <div>
            Vehicle detections: <strong style={{ color: C.text }}>{detectionCount}</strong>
          </div>
          {preview && (
            <>
              <div>
                Latest plate:{" "}
                <strong style={{ color: trackablePlate ? C.text : C.muted, fontFamily: "monospace" }}>
                  {preview.plate || "UNKNOWN"}
                </strong>
              </div>
              <div>Latest detection: {preview.time}</div>
            </>
          )}
        </div>
      )}

      <div style={{ display: "flex", gap: 6, marginTop: 8 }} onClick={(e) => e.stopPropagation()}>
        <button type="button" onClick={() => onClick?.(cam)} style={cardActionBtn} title="Open camera details">
          <Video size={11} /> Open
        </button>
        <button
          type="button"
          onClick={() => trackablePlate && navigate(`/investigation?plate=${encodeURIComponent(trackablePlate)}`)}
          disabled={!trackablePlate}
          title={trackablePlate ? `Track ${trackablePlate}` : "No readable plate yet on this camera"}
          style={{ ...cardActionBtn, opacity: trackablePlate ? 1 : 0.4, cursor: trackablePlate ? "pointer" : "not-allowed" }}
        >
          <Crosshair size={11} /> Track
        </button>
        <button
          type="button"
          onClick={() => navigate(`/investigation?cam=${encodeURIComponent(cam.id)}`)}
          style={cardActionBtn}
          title="Open this camera in the investigation console"
        >
          <MapPinned size={11} /> Investigate
        </button>
      </div>
    </div>
  );
}

const cardActionBtn = {
  flex: 1,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 4,
  background: "transparent",
  border: `1px solid ${C.border}`,
  color: C.muted,
  borderRadius: 4,
  padding: "4px 4px",
  fontSize: 9.5,
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
};
