import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Car, VideoOff } from "lucide-react";
import { C } from "../theme.js";
import { LIVE_CAMERA_ENDPOINTS, fetchLiveCameraStatus } from "../services/liveCameraApi.js";

const STATUS_STYLE = {
  ONLINE: { c: C.green, label: "ONLINE" },
  RECONNECTING: { c: C.amber, label: "RECONNECTING" },
  OFFLINE: { c: C.red, label: "OFFLINE" },
};

const POLL_MS = 2000;

// New, self-contained page (does not touch the existing multi-camera
// dashboard/registry): a single real RTSP camera (CAM_AHM_001) + real YOLO
// vehicle detection on that same feed, served by the standalone
// scripts/live_camera_ai_service.py. Status/AI values here are always
// exactly what that service reports -- never a fabricated ONLINE, never a
// simulated detection.
export default function LiveCameraAIPage() {
  const [status, setStatus] = useState(null);
  const [live, setLive] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const prevReady = useRef({ cam: false, ai: false });

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      const res = await fetchLiveCameraStatus();
      if (cancelled) return;
      setStatus(res.data);
      setLive(res.live);
      // A fresh not-ready -> ready transition (camera reconnected, or the
      // AI model finished loading) means a new real frame source just
      // became available -- remount the <img> streams so the browser opens
      // a new multipart request instead of sitting on a dead one.
      const camReady = Boolean(res.data?.status && res.data.status !== "OFFLINE");
      const aiReady = camReady && ["PROCESSING", "IDLE"].includes(res.data?.ai_status);
      if ((camReady && !prevReady.current.cam) || (aiReady && !prevReady.current.ai)) {
        setAttempt((a) => a + 1);
      }
      prevReady.current = { cam: camReady, ai: aiReady };
    }
    poll();
    const t = setInterval(poll, POLL_MS);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  const camStatus = status?.status || "OFFLINE";
  const camMeta = STATUS_STYLE[camStatus] || STATUS_STYLE.OFFLINE;
  const cameraId = status?.camera_id || "CAM_AHM_001";
  const connected = camStatus !== "OFFLINE";
  const aiReady = connected && ["PROCESSING", "IDLE"].includes(status?.ai_status);

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontWeight: 700, fontSize: 15 }}>Real-Time CCTV &amp; AI Detection</div>
        <div style={{ color: C.muted, fontSize: 12, marginTop: 2 }}>
          One real RTSP camera ({cameraId}) — live feed and real YOLO vehicle detection. No demo or simulated data.
        </div>
      </div>

      {!live && (
        <div style={{
          display: "flex", alignItems: "center", gap: 8, background: C.redGlow,
          border: `1px solid ${C.red}`, color: C.red, borderRadius: 6,
          padding: "8px 12px", fontSize: 12, marginBottom: 14,
        }}>
          <AlertTriangle size={14} />
          Live Camera &amp; AI service unreachable — {status?.last_error || "check scripts/live_camera_ai_service.py is running"}.
        </div>
      )}

      {live && !status?.configured && (
        <div style={{
          display: "flex", alignItems: "center", gap: 8, background: C.amberGlow,
          border: `1px solid ${C.amber}`, color: C.amber, borderRadius: 6,
          padding: "8px 12px", fontSize: 12, marginBottom: 14,
        }}>
          <AlertTriangle size={14} />
          LIVE_CAMERA_RTSP_URL is not configured yet — the camera will show OFFLINE until the real RTSP URL is set.
        </div>
      )}

      <Section
        title="Provided Data / Live Camera"
        subtitle="Direct, unmodified feed from the real RTSP camera"
      >
        <FeedPanel
          streamUrl={LIVE_CAMERA_ENDPOINTS.rawStream}
          connected={connected}
          attempt={attempt}
          camStatus={camStatus}
          camMeta={camMeta}
          badge={{ text: "REAL FEED", color: C.green }}
        />
        <StatusRow cameraId={cameraId} camStatus={camStatus} camMeta={camMeta}
          reconnectCount={status?.reconnect_count} lastFrameAt={status?.last_frame_at} />
      </Section>

      <Section
        title="AI Vehicle Detection"
        subtitle="Real YOLO inference on the same live camera feed"
      >
        <FeedPanel
          streamUrl={LIVE_CAMERA_ENDPOINTS.annotatedStream}
          connected={aiReady}
          attempt={attempt}
          camStatus={aiReady ? camStatus : (status?.ai_status || "OFFLINE")}
          camMeta={aiReady ? camMeta : (STATUS_STYLE[status?.ai_status] || { c: C.muted, label: status?.ai_status || "UNAVAILABLE" })}
          badge={{ text: "AI ANNOTATED", color: C.violet }}
        />
        <AIStatusRow status={status} />
        <DetectionsList detections={status?.detections || []} />
      </Section>
    </div>
  );
}

function Section({ title, subtitle, children }) {
  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8,
      padding: 16, marginBottom: 16,
    }}>
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontWeight: 700, fontSize: 13 }}>{title}</div>
        <div style={{ color: C.muted, fontSize: 11, marginTop: 2 }}>{subtitle}</div>
      </div>
      {children}
    </div>
  );
}

function FeedPanel({ streamUrl, connected, attempt, camStatus, camMeta, badge }) {
  const [imgError, setImgError] = useState(false);
  useEffect(() => { setImgError(false); }, [attempt, connected]);

  const showImage = connected && !imgError;

  return (
    <div style={{
      position: "relative", background: "#000", borderRadius: 8, overflow: "hidden",
      height: 360, display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div style={{ position: "absolute", top: 8, left: 8, zIndex: 3, display: "flex", gap: 6 }}>
        <span style={{
          display: "inline-flex", alignItems: "center", gap: 5, background: "rgba(0,0,0,0.6)",
          color: camMeta.c, border: `1px solid ${camMeta.c}`, borderRadius: 3,
          padding: "2px 8px", fontSize: 10, fontWeight: 800, letterSpacing: 0.8,
        }}>
          {camStatus === "ONLINE" && <span style={{ width: 6, height: 6, borderRadius: "50%", background: camMeta.c }} />}
          {camMeta.label}
        </span>
        {showImage && (
          <span style={{
            background: "rgba(0,0,0,0.6)", color: badge.color, border: `1px solid ${badge.color}`,
            borderRadius: 3, padding: "2px 6px", fontSize: 8, fontWeight: 700,
          }}>
            {badge.text}
          </span>
        )}
      </div>

      {showImage ? (
        <img
          key={attempt}
          src={`${streamUrl}?t=${attempt}`}
          alt="Live camera stream"
          onError={() => setImgError(true)}
          style={{ width: "100%", height: "100%", objectFit: "contain" }}
        />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, color: C.muted }}>
          <VideoOff size={26} />
          <div style={{ fontSize: 12 }}>
            {connected ? "Stream unavailable — retrying" : `Camera ${camMeta.label.toLowerCase()} — no live feed`}
          </div>
        </div>
      )}
    </div>
  );
}

function StatusRow({ cameraId, camStatus, camMeta, reconnectCount, lastFrameAt }) {
  return (
    <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginTop: 12, fontSize: 11.5, color: C.muted }}>
      <Metric label="Camera" value={cameraId} />
      <Metric label="Status" value={camMeta.label} valueColor={camMeta.c} />
      <Metric label="Reconnects" value={reconnectCount ?? "—"} />
      <Metric label="Last Frame" value={lastFrameAt ? new Date(lastFrameAt * 1000).toLocaleTimeString("en-IN", { hour12: false }) : "—"} />
    </div>
  );
}

function AIStatusRow({ status }) {
  const aiStatus = status?.ai_status || "UNAVAILABLE";
  const aiColor = aiStatus === "PROCESSING" ? C.green : aiStatus === "UNAVAILABLE" ? C.red : C.muted;
  return (
    <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginTop: 12, fontSize: 11.5, color: C.muted }}>
      <Metric label="AI Status" value={aiStatus} valueColor={aiColor} />
      <Metric label="Model" value="YOLOv8 (ai/detection/vehicle_detector.py)" />
      <Metric label="Vehicles Detected" value={status?.vehicles_detected ?? 0} valueColor={C.text} />
      {status?.ai_model_error && (
        <Metric label="Model Error" value={status.ai_model_error} valueColor={C.red} />
      )}
    </div>
  );
}

function Metric({ label, value, valueColor }) {
  return (
    <div>
      <div style={{ textTransform: "uppercase", letterSpacing: 0.6, fontSize: 9.5 }}>{label}</div>
      <div style={{ color: valueColor || C.text, fontWeight: 600, fontSize: 12.5, marginTop: 2 }}>{value}</div>
    </div>
  );
}

function DetectionsList({ detections }) {
  if (!detections.length) {
    return (
      <div style={{ marginTop: 12, color: C.muted, fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
        <Car size={13} /> No vehicles currently detected.
      </div>
    );
  }
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {detections.map((d, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 6, background: C.panel,
            border: `1px solid ${C.border}`, borderRadius: 4, padding: "4px 10px", fontSize: 11.5,
          }}>
            <Car size={12} color={C.accent} />
            <span style={{ textTransform: "capitalize", fontWeight: 600 }}>{d.class}</span>
            <span style={{ color: C.muted }}>{(d.confidence * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
