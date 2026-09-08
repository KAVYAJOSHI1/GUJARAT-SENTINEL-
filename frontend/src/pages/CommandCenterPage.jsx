import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CircleMarker, Tooltip } from "react-leaflet";
import {
  Activity, AlertTriangle, BellRing, Bot, Car, ClipboardList, FolderOpen,
  Gauge, MapPin, RefreshCw, ScanLine, ShieldAlert, Video,
} from "lucide-react";
import { C } from "../theme.js";
import GisMap from "../components/gis/GisMap.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import {
  Badge, CommandButton, MetricCard, Panel, SectionHeader, SeverityBadge,
  SourceBadge, StatusBadge,
} from "../components/ui/primitives.jsx";
import { fmtDateTime, fmtRelative } from "../utils/datetime.js";
import { commandCenterSummary } from "../services/commandCenterApi.js";

const STATE_COLOR = { ONLINE: C.green, DEGRADED: C.amber, OFFLINE: C.red };
const fmtAge = (s) => (s == null ? "" : s < 60 ? `${s}s` : s < 3600 ? `${Math.round(s / 60)}m` : `${Math.round(s / 3600)}h`);

// Phase 16A — SENTINEL Command Center. The primary landing page. One
// bounded aggregation call (/command-center/summary), a bounded refresh,
// and a subtle LIVE indicator driven by the shared WS status.
export default function CommandCenterPage() {
  const nav = useNavigate();
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [lastAt, setLastAt] = useState(null);
  const timer = useRef(null);

  const load = useCallback(async () => {
    try {
      setErr("");
      setD(await commandCenterSummary());
      setLastAt(new Date());
    } catch (e) {
      setErr(e?.response?.data?.error?.message || "Command Center unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    timer.current = setInterval(load, 20000);      // bounded poll; WS covers urgent
    return () => clearInterval(timer.current);
  }, [load]);

  const k = d?.kpis || {};
  const geoCams = (d?.cameras || []).filter((c) => c.latitude != null);
  const wsLive = typeof window !== "undefined" && window.__sentinelWsOpen;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontWeight: 800, fontSize: 16, letterSpacing: 0.4 }}>SENTINEL COMMAND CENTER</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 10, color: wsLive ? C.green : C.muted, fontWeight: 700 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: wsLive ? C.green : C.muted, animation: wsLive ? "pulse 2s infinite" : "none" }} />
          {wsLive ? "LIVE" : "POLLING"}
        </span>
        <span style={{ color: C.dim, fontSize: 10, marginLeft: "auto" }}>
          {lastAt ? `updated ${fmtRelative(lastAt.toISOString())}` : ""}
        </span>
        <button onClick={load} style={{ background: C.panel, border: `1px solid ${C.border}`, color: C.muted, borderRadius: 4, padding: "4px 8px", cursor: "pointer" }} title="Refresh">
          <RefreshCw size={12} />
        </button>
      </div>

      {err && <ErrorBanner message={err} onRetry={load} />}

      {loading && !d ? (
        <Panel><div style={{ padding: 16 }}><SkeletonRows rows={5} height={40} /></div></Panel>
      ) : d ? (
        <>
          {/* ── KPI strip ─────────────────────────────────────────────── */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <MetricCard label="Active Alerts" value={k.active_alerts} color={k.active_alerts ? C.red : C.green} onClick={() => nav("/alerts")} />
            <MetricCard label="Escalated" value={k.escalated} color={k.escalated ? C.red : C.muted} onClick={() => nav("/alerts?status=ESCALATED")} />
            <MetricCard label="Open Incidents" value={k.open_incidents} color={k.open_incidents ? C.amber : C.green} onClick={() => nav("/incidents")} />
            <MetricCard label="Open Cases" value={k.open_cases} color={C.violet} onClick={() => nav("/cases")} />
            <MetricCard label="Cameras Online" value={k.cameras_online} color={C.green} onClick={() => nav("/cameras")} />
            <MetricCard label="Cameras Degraded" value={k.cameras_degraded + k.cameras_offline} sub={`${k.cameras_poor_video} poor video`} color={(k.cameras_degraded + k.cameras_offline) ? C.amber : C.green} onClick={() => nav("/camera-intelligence")} />
            <MetricCard label="Vehicles Today" value={(k.vehicles_today || 0).toLocaleString("en-IN")} color={C.accent} onClick={() => nav("/traffic")} />
            <MetricCard label="Anomalies Today" value={k.anomalies_today} color={k.anomalies_today ? C.violet : C.green} onClick={() => nav("/anomalies")} />
          </div>

          {/* ── top row: alerts | map | camera health ─────────────────── */}
          <div style={{ display: "grid", gridTemplateColumns: "320px 1fr 300px", gap: 12, alignItems: "start" }} className="cc-top">
            <Panel>
              <SectionHeader icon={BellRing} title="Active Alerts" sub={`${d.active_alerts_total} total`}
                right={<CommandButton small to="/alerts">All</CommandButton>} />
              <div style={{ maxHeight: 360, overflowY: "auto" }}>
                {d.active_alerts.length === 0 ? (
                  <EmptyState icon={ShieldAlert} title="No active alerts" hint="The board is clear." />
                ) : d.active_alerts.map((a) => (
                  <div key={a.id} style={{ padding: "9px 12px", borderTop: `1px solid ${C.border}` }}>
                    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                      <SeverityBadge level={a.severity} />
                      <span style={{ fontFamily: "monospace", color: C.amber, fontSize: 12 }}>{a.plate}</span>
                      <span style={{ color: C.dim, fontSize: 10 }}>{a.camera_code}</span>
                      <span style={{ marginLeft: "auto", color: C.muted, fontSize: 9 }}>{fmtAge(a.age_seconds)} old</span>
                    </div>
                    <div style={{ display: "flex", gap: 6, marginTop: 5 }}>
                      <CommandButton small primary onClick={() => nav(a.investigate_href)}>INVESTIGATE</CommandButton>
                      <CommandButton small to={a.href}>Open alert</CommandButton>
                    </div>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel>
              <SectionHeader icon={MapPin} title="Live Situation" sub={`${geoCams.length} geolocated cameras`} />
              <GisMap height={380}>
                {geoCams.map((c) => (
                  <CircleMarker key={c.id} center={[c.latitude, c.longitude]}
                    radius={c.state === "OFFLINE" ? 9 : 7}
                    pathOptions={{
                      color: c.poor_video ? C.violet : STATE_COLOR[c.state],
                      fillColor: STATE_COLOR[c.state], fillOpacity: 0.5, weight: c.poor_video ? 3 : 1.5,
                    }}
                    eventHandlers={{ click: () => nav(`/camera-intelligence/${c.code}`) }}>
                    <Tooltip>
                      <b>{c.code}</b> — {c.state}{c.poor_video ? " · POOR VIDEO" : ""}<br />
                      {c.name}<br />
                      {c.last_detection_at ? `last det ${fmtRelative(c.last_detection_at)}` : "no detections"}
                    </Tooltip>
                  </CircleMarker>
                ))}
              </GisMap>
              <div style={{ padding: "6px 12px", color: C.dim, fontSize: 9, display: "flex", gap: 10 }}>
                <span><b style={{ color: C.green }}>●</b> online</span>
                <span><b style={{ color: C.amber }}>●</b> degraded</span>
                <span><b style={{ color: C.red }}>●</b> offline</span>
                <span><b style={{ color: C.violet }}>◯</b> poor video</span>
              </div>
            </Panel>

            <Panel>
              <SectionHeader icon={Video} title="Camera Health"
                right={<CommandButton small to="/camera-intelligence">Intel</CommandButton>} />
              <div style={{ maxHeight: 380, overflowY: "auto" }}>
                {d.problem_cameras.length === 0 ? (
                  <EmptyState icon={Video} title="All cameras healthy" />
                ) : d.problem_cameras.map((c) => (
                  <Link key={c.id} to={`/camera-intelligence/${c.code}`} style={{ display: "block", textDecoration: "none", padding: "8px 12px", borderTop: `1px solid ${C.border}`, color: C.text }}>
                    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                      <span style={{ fontFamily: "monospace", color: C.accent, fontSize: 11 }}>{c.code}</span>
                      <Badge color={STATE_COLOR[c.state]}>{c.state}</Badge>
                      {c.poor_video && <Badge color={C.violet}>POOR VIDEO</Badge>}
                      <span style={{ marginLeft: "auto", color: C.muted, fontSize: 9 }}>
                        {c.last_heartbeat ? fmtRelative(c.last_heartbeat) : "no telemetry"}
                      </span>
                    </div>
                    <div style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>{c.name}</div>
                  </Link>
                ))}
              </div>
            </Panel>
          </div>

          {/* ── active investigations ─────────────────────────────────── */}
          <Panel>
            <SectionHeader icon={ClipboardList} title="Active Investigations"
              sub={`${k.open_incidents} incidents · ${k.open_cases} cases`} />
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(260px,1fr))", gap: 8, padding: 12 }}>
              {d.active_investigations.length === 0 ? (
                <EmptyState icon={FolderOpen} title="No open investigations" />
              ) : d.active_investigations.map((x) => (
                <Link key={x.id} to={x.href} style={{ display: "block", textDecoration: "none", color: C.text, background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6, padding: "8px 10px" }}>
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <span style={{ fontSize: 8, fontWeight: 800, color: x.kind === "CASE" ? C.violet : C.amber }}>{x.kind}</span>
                    <span style={{ fontFamily: "monospace", color: C.accent, fontSize: 11 }}>{x.label}</span>
                    <span style={{ marginLeft: "auto" }}><StatusBadge status={x.status} /></span>
                  </div>
                  <div style={{ color: C.muted, fontSize: 10.5, marginTop: 3 }}>{x.title}</div>
                  {x.plate && <div style={{ color: C.dim, fontSize: 9, fontFamily: "monospace", marginTop: 2 }}>{x.plate}</div>}
                </Link>
              ))}
            </div>
          </Panel>

          {/* ── bottom row ────────────────────────────────────────────── */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 12 }}>
            <Panel>
              <SectionHeader icon={Car} title="Recent Vehicles" />
              <div style={{ padding: 8, display: "grid", gap: 5 }}>
                {(d.recent_vehicles || []).map((v) => (
                  <Link key={v.plate} to={v.href} style={{ display: "flex", justifyContent: "space-between", textDecoration: "none", color: C.text, fontSize: 11, padding: "4px 8px", borderRadius: 4, background: C.panel }}>
                    <span style={{ fontFamily: "monospace", color: C.accent }}>{v.plate}</span>
                    <span style={{ color: C.muted }}>{v.sightings} · {fmtRelative(v.last_seen)}</span>
                  </Link>
                ))}
                {!d.recent_vehicles?.length && <div style={{ color: C.dim, fontSize: 10, padding: 8 }}>No vehicles yet</div>}
              </div>
            </Panel>

            <Panel>
              <SectionHeader icon={Bot} title="Recent Anomalies" sub={`${d.anomalies_new} NEW`}
                right={<CommandButton small to="/anomalies">All</CommandButton>} />
              <div style={{ padding: 8, display: "grid", gap: 5 }}>
                {(d.recent_anomalies || []).map((a) => (
                  <Link key={a.id} to={a.href} style={{ textDecoration: "none", color: C.text, fontSize: 10.5, padding: "4px 8px", borderRadius: 4, background: C.panel, display: "flex", gap: 6, alignItems: "center" }}>
                    <span style={{ fontSize: 8, fontWeight: 700, color: C.amber }}>{a.kind}</span>
                    <span style={{ fontFamily: "monospace", color: C.accent }}>{a.camera_code}</span>
                    <span style={{ marginLeft: "auto", color: C.muted }}>{fmtRelative(a.created_at)}</span>
                  </Link>
                ))}
                {!d.recent_anomalies?.length && <div style={{ color: C.dim, fontSize: 10, padding: 8 }}>None detected</div>}
              </div>
            </Panel>

            <Panel>
              <SectionHeader icon={Gauge} title="System Status" right={<CommandButton small to="/system">Details</CommandButton>} />
              <div style={{ padding: 10, display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 10px", fontSize: 11 }}>
                <span style={{ color: C.muted }}>Pipeline</span>
                <span style={{ textAlign: "right", color: d.metrics.pipeline.reported ? C.green : C.amber, fontFamily: "monospace" }}>
                  {d.metrics.pipeline.reported ? (d.metrics.pipeline.stale ? "STALE" : "reporting") : "offline"}
                </span>
                <span style={{ color: C.muted }}>ANPR (24h)</span>
                <span style={{ textAlign: "right", fontFamily: "monospace", color: C.text }}>
                  {d.metrics.anpr.success_rate != null ? `${Math.round(d.metrics.anpr.success_rate * 100)}%` : "—"} of {d.metrics.anpr.window_total}
                </span>
                <span style={{ color: C.muted }}>Cameras</span>
                <span style={{ textAlign: "right", fontFamily: "monospace", color: C.text }}>
                  {d.metrics.cameras.online}/{d.metrics.cameras.total} online
                </span>
                <span style={{ color: C.muted }}>Reconnects</span>
                <span style={{ textAlign: "right", fontFamily: "monospace", color: C.muted }}>
                  {d.metrics.cameras.cumulative_reconnects}
                </span>
              </div>
            </Panel>

            <Panel>
              <SectionHeader icon={ScanLine} title="Quick Actions" />
              <div style={{ padding: 10, display: "flex", flexDirection: "column", gap: 6 }}>
                <CommandButton to="/workspace" icon={Car}>Investigation Workspace</CommandButton>
                <CommandButton to="/live-monitoring" icon={Video}>Live Monitoring Wall</CommandButton>
                <CommandButton to="/copilot" icon={Bot}>AI Copilot</CommandButton>
                <CommandButton to="/anpr-intelligence" icon={ScanLine}>ANPR Intelligence</CommandButton>
                <CommandButton to="/traffic" icon={Activity}>Traffic Intelligence</CommandButton>
              </div>
            </Panel>
          </div>
        </>
      ) : null}
    </div>
  );
}
