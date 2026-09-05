import { Activity, Cpu, Database, Radio, Server, Zap } from "lucide-react";
import { C } from "../../theme.js";

// Phase 7 — command-center system health. Every state below comes from the
// backend's GET /api/v1/dashboard/health (real DB probe + camera health +
// AI-pipeline self-report + event-flow freshness). When that endpoint is
// unavailable, the panel says so explicitly and falls back ONLY to what the
// already-loaded camera list can tell us — it never shows a fabricated
// "ONLINE".

const DOT = { ok: C.green, online: C.green, degraded: C.amber, stale: C.amber, down: C.red, offline: C.red, unknown: C.muted };
const TEXT = { ok: "OK", online: "ONLINE", degraded: "DEGRADED", stale: "STALE", down: "DOWN", offline: "OFFLINE", unknown: "UNKNOWN" };

function ago(seconds) {
  if (seconds == null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

function Row({ icon: Icon, label, state, detail }) {
  const s = state || "unknown";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 0" }}>
      <Icon size={13} color={C.muted} style={{ flexShrink: 0 }} />
      <span style={{ flex: 1, color: C.text, fontSize: 11.5 }}>{label}</span>
      {detail != null && (
        <span style={{ color: C.muted, fontSize: 10, marginRight: 6, fontFamily: "monospace" }}>{detail}</span>
      )}
      <span style={{ display: "flex", alignItems: "center", gap: 5, color: DOT[s], fontSize: 9.5, fontWeight: 700, letterSpacing: 0.5 }}>
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: DOT[s], display: "inline-block" }} />
        {TEXT[s] || s.toUpperCase()}
      </span>
    </div>
  );
}

export default function SystemHealthPanel({ health, healthLive, cameras = [], lastRefresh }) {
  const wrap = {
    background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6,
    padding: "10px 12px", flex: 1, minWidth: 240,
  };

  const heading = (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
      <span style={{ color: C.muted, fontSize: 10, textTransform: "uppercase", letterSpacing: 1 }}>System Health</span>
      {!healthLive && (
        <span style={{ color: C.amber, fontSize: 8.5, fontWeight: 700, border: `1px solid ${C.amber}55`, borderRadius: 3, padding: "0 4px" }}>
          HEALTH FEED DOWN
        </span>
      )}
    </div>
  );

  // ── Degraded mode: /dashboard/health unavailable ──────────────────────────
  if (!health) {
    const total = cameras.length;
    const online = cameras.filter((c) => c.status === "active" || c.status === "alert").length;
    const camState = total === 0 ? "unknown" : online === total ? "online" : online === 0 ? "offline" : "degraded";
    return (
      <div style={wrap}>
        {heading}
        <div style={{ color: C.muted, fontSize: 10.5, marginBottom: 6 }}>
          Health endpoint unreachable — showing only what the camera list reports. AI-pipeline / DB / event-flow status unavailable (no estimates shown).
        </div>
        <Row icon={Radio} label="Camera list" state={camState} detail={`${online}/${total}`} />
        <Row icon={Server} label="Backend API" state="unknown" />
        <Row icon={Database} label="Database" state="unknown" />
        <Row icon={Cpu} label="AI Pipeline" state="unknown" />
      </div>
    );
  }

  const { backend, database, aiPipeline: ai, cameras: cam, events } = health;

  const camState = cam.total === 0
    ? "unknown"
    : cam.online === cam.total ? "online"
    : cam.online === 0 ? "offline" : "degraded";

  const eventState = events.lastEventAgeSeconds == null
    ? "unknown"
    : events.lastEventAgeSeconds < 120 ? "ok"
    : events.lastEventAgeSeconds < 900 ? "degraded" : "down";

  return (
    <div style={wrap}>
      {heading}
      <Row icon={Server} label="Backend API" state={backend.status} />
      <Row
        icon={Database}
        label="Database (PostGIS)"
        state={database.status}
        detail={database.latencyMs != null ? `${database.latencyMs.toFixed(1)}ms` : null}
      />
      <Row
        icon={Cpu}
        label="AI Pipeline"
        state={ai.status}
        detail={
          ai.status === "unknown"
            ? "no report"
            : `${ai.processedFps != null ? ai.processedFps.toFixed(1) + " fps · " : ""}${ago(ai.ageSeconds)}`
        }
      />
      <Row
        icon={Radio}
        label="Camera Connectivity"
        state={camState}
        detail={`${cam.online} on · ${cam.degraded} deg · ${cam.offline} off${cam.stale ? ` · ${cam.stale} stale` : ""}`}
      />
      <Row
        icon={Zap}
        label="Event Flow"
        state={eventState}
        detail={events.lastEventAgeSeconds != null ? `last ${ago(events.lastEventAgeSeconds)}` : "no events"}
      />
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 5, paddingTop: 5, borderTop: `1px solid ${C.border}`, color: C.dim, fontSize: 9.5 }}>
        <Activity size={10} /> Refreshed {lastRefresh ? lastRefresh.toLocaleTimeString("en-IN", { hour12: false }) : "—"}
      </div>
    </div>
  );
}
