import { useMemo, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import {
  Activity,
  BarChart3,
  BellRing,
  Bot,
  Briefcase,
  Car,
  ClipboardList,
  Clock,
  FileBarChart,
  FolderOpen,
  PanelRightOpen,
  ScanLine,
  Search,
  ShieldAlert,
  Video,
  VideoOff,
} from "lucide-react";
import { C } from "../theme.js";
import { isMockCamera } from "../services/api.js";
import { SEVERITY_COLOR } from "../theme.js";
import StatCard from "../components/StatCard.jsx";
import SystemHealthPanel from "../components/observability/SystemHealthPanel.jsx";
import AiPipelinePanel from "../components/observability/AiPipelinePanel.jsx";
import IncidentBar from "../components/observability/IncidentBar.jsx";
import MiniBarList from "../components/analytics/MiniBarList.jsx";
import VehicleIntelPanel from "../components/analytics/VehicleIntelPanel.jsx";
import CameraGrid from "../components/CameraGrid.jsx";
import CameraModal from "../components/CameraModal.jsx";
import AlertFeed from "../components/AlertFeed.jsx";
import AlertDrawer from "../components/AlertDrawer.jsx";
import DetectionFeed from "../components/DetectionFeed.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";

const SOURCE_FILTERS = ["ALL", "REAL", "MOCK"];

export default function Dashboard() {
  const {
    stats,
    cameras,
    alerts,
    detections,
    incidents = [],
    cases = [],
    anomalies = [],
    health,
    healthLive,
    latestDetectionByCamera,
    detectionCountByCamera,
    loading,
    backendLive,
    retrying,
    lastRefresh,
    critCount,
    reload,
    ackAlert,
    ackAll,
  } = useOutletContext();

  const navigate = useNavigate();
  const [selectedCam, setSelectedCam] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sourceFilter, setSourceFilter] = useState("ALL");

  const onlineFeeds = stats?.onlineFeeds ?? cameras.filter((c) => c.status !== "offline").length;
  const offlineCameras = stats?.offlineCameras ?? cameras.filter((c) => c.status === "offline").length;
  const activeAlerts = alerts.filter((a) => !a.ack).length;
  const hasMock = cameras.some((c) => c.isMock);

  const visibleCameras = useMemo(() => {
    if (sourceFilter === "ALL") return cameras;
    return cameras.filter((c) => (sourceFilter === "MOCK" ? c.isMock : !c.isMock));
  }, [cameras, sourceFilter]);

  // ── Compact analytics — all derived from the already-loaded feed/alert
  // lists (README task §1: real data only, no extra fetches, no fabricated
  // history). Kept small on purpose: top-5 rows, no dense dashboard. ────────
  const analytics = useMemo(() => {
    const byCamera = {};
    const byVehicleType = {};
    const byHour = {};
    for (const d of detections) {
      byCamera[d.cam] = (byCamera[d.cam] || 0) + 1;
      const vt = d.vehicleType || "unknown";
      byVehicleType[vt] = (byVehicleType[vt] || 0) + 1;
      const t = new Date(d.ts || d.time);
      if (!Number.isNaN(t.getTime())) {
        const h = `${String(t.getHours()).padStart(2, "0")}:00`;
        byHour[h] = (byHour[h] || 0) + 1;
      }
    }
    const bySeverity = { critical: 0, high: 0, medium: 0, low: 0 };
    for (const a of alerts) bySeverity[a.severity] = (bySeverity[a.severity] || 0) + 1;

    const topN = (obj, n, colorFn) =>
      Object.entries(obj)
        .sort((a, b) => b[1] - a[1])
        .slice(0, n)
        .map(([label, value]) => ({ label, value, color: colorFn?.(label) }));

    return {
      byCamera: topN(byCamera, 5),
      byVehicleType: topN(byVehicleType, 6),
      byHour: Object.entries(byHour)
        .sort((a, b) => a[0].localeCompare(b[0]))
        .slice(-8)
        .map(([label, value]) => ({ label, value })),
      bySeverity: [
        { label: "critical", value: bySeverity.critical, color: C.red },
        { label: "high", value: bySeverity.high, color: C.amber },
        { label: "medium", value: bySeverity.medium, color: C.violet },
        { label: "low", value: bySeverity.low, color: C.muted },
      ].filter((r) => r.value > 0),
    };
  }, [detections, alerts]);

  return (
    <div>
      {!backendLive && (
        <ErrorBanner
          message="OFFLINE — DEMO DATA. Backend unreachable: cameras, stats and alerts below are simulated fallback data, not a live feed. Retrying…"
          onRetry={reload}
          retrying={retrying}
        />
      )}

      {/* Phase 7 — unhandled HIGH/CRITICAL incidents pinned to the top */}
      <IncidentBar alerts={alerts} onOpenDrawer={() => setDrawerOpen(true)} />

      <div className="stat-row" style={{ marginBottom: 14 }}>
        <StatCard label="Total Cameras" value={stats?.totalCameras ?? cameras.length} sub="Registered feeds" icon={Video} color={C.accent} loading={loading} />
        <StatCard label="Online Cameras" value={onlineFeeds} sub={`${cameras.filter((c) => c.status === "alert").length} in incident`} icon={Activity} color={C.green} loading={loading} />
        <StatCard label="Offline Cameras" value={offlineCameras} sub="Needs attention" icon={VideoOff} color={offlineCameras > 0 ? C.red : C.muted} loading={loading} />
        <StatCard label="Live Detections" value={(stats?.todaysDetections ?? 0).toLocaleString("en-IN")} sub="Last 24h" icon={ScanLine} color={C.amber} loading={loading} />
        <StatCard label="ANPR Reads" value={stats?.anprReadsPerHour ?? 0} sub="Readable plates / hr" icon={Car} color={C.violet} loading={loading} />
        <StatCard label="Watchlist Matches" value={stats?.watchlistMatches ?? 0} sub="All-time confirmed" icon={ShieldAlert} color={C.red} loading={loading} />
        <StatCard label="Active Alerts" value={activeAlerts} sub="Requires attention" icon={BellRing} color={activeAlerts > 0 ? C.red : C.green} pulse={activeAlerts > 0} loading={loading} />
        <StatCard label="Active Incidents" value={stats?.activeIncidents ?? 0} sub="Open / investigating" icon={ClipboardList} color={(stats?.activeIncidents ?? 0) > 0 ? C.amber : C.green} loading={loading} />
        <StatCard label="Open Cases" value={stats?.openCases ?? 0} sub="Under investigation" icon={FolderOpen} color={C.violet} loading={loading} />
        <StatCard label="AI Anomalies" value={anomalies.filter((a) => a.status === "NEW").length} sub="Stopped vehicles · NEW" icon={Bot} color={anomalies.some((a) => a.status === "NEW") ? C.violet : C.muted} loading={loading} />
      </div>

      {/* ── Quick actions (command center) ─────────────────────────────────── */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
        <QuickAction icon={Bot} label="AI Copilot" onClick={() => navigate("/copilot")} />
        <QuickAction icon={BarChart3} label="Traffic Intelligence" onClick={() => navigate("/traffic")} />
        <QuickAction icon={Activity} label="Camera Reliability" onClick={() => navigate("/camera-intelligence")} />
        <QuickAction icon={Search} label="Advanced Search" onClick={() => navigate("/search")} />
        <QuickAction icon={Briefcase} label="My Work" onClick={() => navigate("/my-work")} />
        <QuickAction icon={ClipboardList} label="Incidents" onClick={() => navigate("/incidents")} />
        <QuickAction icon={FolderOpen} label="Cases" onClick={() => navigate("/cases")} />
        <QuickAction icon={ShieldAlert} label="Watchlists" onClick={() => navigate("/watchlists")} />
        <QuickAction icon={FileBarChart} label="Reports" onClick={() => navigate("/reports")} />
        <QuickAction icon={Video} label="Cameras" onClick={() => navigate("/cameras")} />
        <QuickAction icon={ShieldAlert} label="Alerts" onClick={() => navigate("/alerts")} />
      </div>

      {/* ── Operations: live incidents + recent cases ─────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: 12, marginBottom: 14 }}>
        <OpsList
          title="Live Incidents" icon={ClipboardList} to="/incidents"
          empty="No active incidents"
          rows={incidents.map((i) => ({
            id: i.id, href: `/incidents/${i.id}`, ref: i.incident_number, main: i.title,
            tag: i.status, sub: `${i.plate_number_normalized || "—"} · ${i.assigned_to_username || "unassigned"}`,
            color: SEVCOL(i.priority_level),
          }))}
        />
        <OpsList
          title="Recent Cases" icon={FolderOpen} to="/cases"
          empty="No cases opened"
          rows={cases.map((c) => ({
            id: c.id, href: `/cases/${c.id}`, ref: c.case_number, main: c.title,
            tag: c.status, sub: `${c.incident_count} incidents · ${c.evidence_count} evidence`,
            color: SEVCOL(c.priority_level),
          }))}
        />
        <OpsList
          title="AI Anomaly Events" icon={Bot} to="/anomalies"
          empty="No anomalies detected"
          rows={(anomalies || []).map((a) => ({
            id: a.id, href: "/anomalies", ref: a.camera_code || "cam",
            main: `Stopped vehicle · ${a.plate_number_normalized || "unknown"}`,
            tag: a.confidence_level,
            sub: `${Math.round(a.duration_seconds / 60)} min · ${a.detection_count} detections · ${a.status}`,
            color: a.confidence_level === "HIGH" ? C.red : C.amber,
          }))}
        />
      </div>

      {/* ── System health + compact live analytics ─────────────────────────── */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
        <SystemHealthPanel health={health} healthLive={healthLive} cameras={cameras} lastRefresh={lastRefresh} />
        <MiniBarList title="Detections / hour" icon={Clock} items={analytics.byHour} loading={loading} emptyHint="Waiting for detections…" />
        <MiniBarList title="Top cameras" icon={BarChart3} items={analytics.byCamera} loading={loading} emptyHint="No detections yet" />
        <MiniBarList title="Vehicle types" icon={Car} items={analytics.byVehicleType} loading={loading} emptyHint="No detections yet" />
        <MiniBarList title="Alert severity" icon={ShieldAlert} items={analytics.bySeverity} loading={loading} emptyHint="No alerts yet" />
      </div>

      {/* ── AI pipeline metrics (Phase 7) — pipeline self-report, honest —— */}
      <div style={{ marginBottom: 14 }}>
        <AiPipelinePanel health={health} />
      </div>

      {/* ── Vehicle Intelligence — true DB aggregates (Phase 5 §4) ─────────── */}
      <div style={{ marginBottom: 14 }}>
        <VehicleIntelPanel reloadKey={lastRefresh} />
      </div>

      <div className="overview-grid">
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
          <div
            style={{
              padding: "12px 16px",
              borderBottom: `1px solid ${C.border}`,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 8,
            }}
          >
            <span style={{ fontWeight: 600, fontSize: 13 }}>Live Camera Grid</span>
            <span style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 11 }}>
              {/* ALL / REAL / MOCK filter (README task §12) — only shown once
                  a mock camera actually exists, so nothing changes for a
                  real-cameras-only deployment. */}
              {hasMock && (
                <span style={{ display: "flex", gap: 4 }}>
                  {SOURCE_FILTERS.map((f) => (
                    <button
                      key={f}
                      onClick={() => setSourceFilter(f)}
                      style={{
                        background: sourceFilter === f ? C.accentGlow : "transparent",
                        border: `1px solid ${sourceFilter === f ? C.accent : C.border}`,
                        color: sourceFilter === f ? C.accent : C.muted,
                        borderRadius: 3,
                        padding: "2px 8px",
                        fontSize: 9.5,
                        fontWeight: 700,
                        cursor: "pointer",
                      }}
                    >
                      {f}
                    </button>
                  ))}
                </span>
              )}
              {hasMock && (
                <span style={{ color: C.muted }}>
                  <span style={{ color: C.green, fontWeight: 700 }}>REAL</span>{" "}
                  {cameras.filter((c) => !isMockCamera(c.id)).length} ·{" "}
                  <span style={{ color: C.violet, fontWeight: 700 }}>MOCK</span>{" "}
                  {cameras.filter((c) => isMockCamera(c.id)).length}
                </span>
              )}
              <span style={{ color: C.muted }}>{visibleCameras.length} feeds</span>
            </span>
          </div>
          <div style={{ padding: 12 }}>
            <CameraGrid
              cameras={visibleCameras}
              columns={3}
              loading={loading}
              selectedId={selectedCam?.id}
              onSelect={setSelectedCam}
              detectionsByCamera={latestDetectionByCamera}
              detectionCountByCamera={detectionCountByCamera}
            />
          </div>
        </div>

        <div
          style={{
            background: C.surface,
            border: `1px solid ${C.border}`,
            borderRadius: 8,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ padding: "8px 12px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontWeight: 600, fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
              <ShieldAlert size={13} color={C.accent} /> Incident / Alert Center
            </span>
            <button
              onClick={() => setDrawerOpen(true)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                background: "transparent",
                border: `1px solid ${C.border}`,
                color: C.muted,
                borderRadius: 4,
                padding: "3px 10px",
                fontSize: 10,
                cursor: "pointer",
              }}
            >
              <PanelRightOpen size={12} /> Open drawer
            </button>
          </div>
          <div style={{ flex: 1, minHeight: 0 }}>
            <AlertFeed
              alerts={alerts}
              loading={loading}
              critCount={critCount}
              onAck={ackAlert}
              onAckAll={ackAll}
              maxHeight={520}
            />
          </div>
        </div>
      </div>

      <div
        style={{
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: 8,
          overflow: "hidden",
          marginTop: 16,
        }}
      >
        <DetectionFeed detections={detections} loading={loading} maxHeight={420} />
      </div>

      <CameraModal cam={selectedCam} onClose={() => setSelectedCam(null)} />
      <AlertDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        alerts={alerts}
        loading={loading}
        critCount={critCount}
        onAck={ackAlert}
        onAckAll={ackAll}
      />
    </div>
  );
}

const SEVCOL = (p) => SEVERITY_COLOR[String(p || "").toLowerCase()] || C.muted;

function QuickAction({ icon: Icon, label, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "flex", alignItems: "center", gap: 6, background: C.surface,
        border: `1px solid ${C.border}`, color: C.text, borderRadius: 6,
        padding: "7px 12px", fontSize: 11.5, fontWeight: 600, cursor: "pointer",
      }}
    >
      <Icon size={13} color={C.accent} /> {label}
    </button>
  );
}

function OpsList({ title, icon: Icon, to, rows, empty }) {
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontWeight: 600, fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
          <Icon size={13} color={C.accent} /> {title}
        </span>
        <Link to={to} style={{ color: C.muted, fontSize: 10, textDecoration: "none" }}>View all →</Link>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: "auto", maxHeight: 260 }}>
        {rows.length === 0 ? (
          <div style={{ color: C.dim, fontSize: 11, padding: "16px 14px" }}>{empty}</div>
        ) : (
          rows.map((r) => (
            <Link
              key={r.id}
              to={r.href}
              style={{
                display: "block", padding: "9px 14px", borderTop: `1px solid ${C.border}`,
                textDecoration: "none", borderLeft: `3px solid ${r.color}`,
              }}
            >
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ fontFamily: "monospace", color: C.accent, fontSize: 11 }}>{r.ref}</span>
                <span style={{ color: C.text, fontSize: 11.5, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.main}</span>
                <span style={{ color: C.muted, fontSize: 9, textTransform: "uppercase", letterSpacing: 0.5 }}>{String(r.tag).replace(/_/g, " ")}</span>
              </div>
              <div style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>{r.sub}</div>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
