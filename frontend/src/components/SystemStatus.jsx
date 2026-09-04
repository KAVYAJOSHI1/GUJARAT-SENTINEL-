import { Activity, Cpu, Database, Radio, Server } from "lucide-react";
import { C } from "../theme.js";

const DOT = { online: C.green, degraded: C.amber, offline: C.red };
const LABEL = { online: "ONLINE", degraded: "DEGRADED", offline: "OFFLINE" };

function Row({ icon: Icon, label, state, detail }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0" }}>
      <Icon size={13} color={C.muted} style={{ flexShrink: 0 }} />
      <span style={{ flex: 1, color: C.text, fontSize: 11.5 }}>{label}</span>
      {detail && <span style={{ color: C.muted, fontSize: 10, marginRight: 6 }}>{detail}</span>}
      <span style={{ display: "flex", alignItems: "center", gap: 5, color: DOT[state], fontSize: 9.5, fontWeight: 700, letterSpacing: 0.5 }}>
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: DOT[state], display: "inline-block" }} />
        {LABEL[state]}
      </span>
    </div>
  );
}

// Honest, derived-only system status strip (README task §1 "System Status").
// Every state below is computed from data the app already holds — nothing
// is a synthetic/simulated health check the backend was never asked for.
export default function SystemStatus({ backendLive, cameras = [], detections = [], lastRefresh }) {
  const total = cameras.length;
  const online = cameras.filter((c) => c.status !== "offline").length;
  const cameraState = total === 0 ? "offline" : online === total ? "online" : online === 0 ? "offline" : "degraded";

  // "AI pipeline" isn't a separate health endpoint (there isn't one to poll
  // honestly) — it's inferred from whether detections have actually landed
  // recently, which is the real, observable signal that YOLO/ByteTrack/OCR
  // are running and reaching the backend.
  const newestDetectionAgeMin = detections.length
    ? (Date.now() - new Date(detections[0].ts || detections[0].time).getTime()) / 60000
    : null;
  const aiState =
    !backendLive
      ? "offline"
      : newestDetectionAgeMin == null
      ? "degraded"
      : newestDetectionAgeMin < 5
      ? "online"
      : newestDetectionAgeMin < 30
      ? "degraded"
      : "offline";

  const backendState = backendLive ? "online" : "offline";
  // Every stats/camera/alert read already round-trips through PostgreSQL —
  // a live backend response IS a live DB, there is no separate signal to
  // fake here.
  const dbState = backendLive ? "online" : "offline";

  return (
    <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6, padding: "10px 12px", flex: 1, minWidth: 220 }}>
      <div style={{ color: C.muted, fontSize: 10, textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>
        System Status
      </div>
      <Row icon={Radio} label="Camera Connectivity" state={cameraState} detail={`${online}/${total}`} />
      <Row icon={Cpu} label="AI Pipeline (YOLO/ByteTrack/OCR)" state={aiState} />
      <Row icon={Server} label="Backend API" state={backendState} />
      <Row icon={Database} label="Database (PostGIS)" state={dbState} />
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.border}`, color: C.dim, fontSize: 9.5 }}>
        <Activity size={10} /> Last refresh: {lastRefresh ? lastRefresh.toLocaleTimeString("en-IN", { hour12: false }) : "—"}
      </div>
    </div>
  );
}
