import { useEffect, useMemo, useState } from "react";
import { CircleMarker, Tooltip } from "react-leaflet";
import {
  Activity, ArrowDownRight, ArrowRight, ArrowUpRight, Car, Clock, Gauge, MapPin,
} from "lucide-react";
import { C } from "../theme.js";
import StatCard from "../components/StatCard.jsx";
import MiniBarList from "../components/analytics/MiniBarList.jsx";
import GisMap from "../components/gis/GisMap.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import {
  trafficByCamera, trafficHeatmap, trafficOverview, trafficTrends,
} from "../services/trafficApi.js";

const WINDOWS = [
  { label: "6h", hours: 6 }, { label: "24h", hours: 24 },
  { label: "7d", hours: 168 }, { label: "30d", hours: 720 },
];
const HEAT_KINDS = [
  { key: "vehicle_density", label: "Vehicles" },
  { key: "alert_density", label: "Alerts" },
  { key: "anomaly_density", label: "Anomalies" },
  { key: "incident_density", label: "Incidents" },
];
const CONGESTION_COLOR = { HIGH: C.red, MODERATE: C.amber, LOW: C.green, NONE: C.muted };
const TREND_ICON = { up: ArrowUpRight, down: ArrowDownRight, flat: ArrowRight };

// Phase 14 §4/§5 — Traffic Intelligence. All figures are live SQL aggregates
// over vehicle_events (never re-processed video). Heatmap = per-camera
// density; only geolocated cameras contribute (no fabricated coordinates).
export default function TrafficIntelligencePage() {
  const [hours, setHours] = useState(24);
  const [vehicleType, setVehicleType] = useState("");
  const [zone, setZone] = useState("");
  const [heatKind, setHeatKind] = useState("vehicle_density");

  const [ov, setOv] = useState(null);
  const [cams, setCams] = useState(null);
  const [trends, setTrends] = useState(null);
  const [heat, setHeat] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const params = useMemo(
    () => ({ window_hours: hours, vehicle_type: vehicleType || undefined, zone: zone || undefined }),
    [hours, vehicleType, zone],
  );

  async function load() {
    setLoading(true);
    setErr("");
    try {
      const [o, c, t, h] = await Promise.all([
        trafficOverview(params),
        trafficByCamera(params),
        trafficTrends({ ...params, bucket: hours > 168 ? "day" : "hour" }),
        trafficHeatmap({ ...params, kind: heatKind }),
      ]);
      setOv(o); setCams(c); setTrends(t); setHeat(h);
    } catch (e) {
      setErr(e?.response?.data?.error?.message || "Failed to load traffic analytics");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [params, heatKind]);

  const TrendIcon = ov ? (TREND_ICON[ov.trend] || ArrowRight) : ArrowRight;
  const trendColor = ov?.trend === "up" ? C.green : ov?.trend === "down" ? C.red : C.muted;

  const typeItems = (ov?.vehicle_type_distribution || []).slice(0, 8).map((d) => ({
    label: d.label, value: d.count, color: C.accent,
  }));
  const camItems = (ov?.top_cameras || []).slice(0, 8).map((d) => ({
    label: d.label, value: d.count, color: C.violet,
  }));
  const maxBucket = trends?.max_bucket?.total || 1;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <Gauge size={16} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>Traffic Intelligence</span>
        <span style={{ color: C.muted, fontSize: 11 }}>
          live aggregates over vehicle_events · no video reprocessing
        </span>
      </div>

      {/* filters */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", margin: "10px 0 14px" }}>
        <div style={{ display: "flex", gap: 4 }}>
          {WINDOWS.map((w) => (
            <button key={w.hours} onClick={() => setHours(w.hours)}
              style={pill(hours === w.hours)}>{w.label}</button>
          ))}
        </div>
        <input value={vehicleType} onChange={(e) => setVehicleType(e.target.value)}
          placeholder="vehicle type (car, truck…)" style={input} />
        <input value={zone} onChange={(e) => setZone(e.target.value)}
          placeholder="zone / area name" style={input} />
      </div>

      {err && <ErrorBanner message={err} onRetry={load} />}

      {loading && !ov ? (
        <div style={panel}><div style={{ padding: 14 }}><SkeletonRows rows={6} height={34} /></div></div>
      ) : ov ? (
        <>
          <div className="stat-row" style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
            <StatCard label="Vehicles" value={ov.total_vehicles.toLocaleString("en-IN")}
              sub={`${ov.window_hours}h window`} icon={Car} color={C.accent} />
            <StatCard label="Per hour" value={ov.vehicles_per_hour} sub="average flow" icon={Activity} color={C.violet} />
            <StatCard label="Peak hour"
              value={ov.peak_hour ? ov.peak_hour.count : "—"}
              sub={ov.peak_hour ? new Date(ov.peak_hour.hour).toLocaleString("en-IN", { hour: "2-digit", day: "2-digit", month: "short" }) : "no data"}
              icon={Clock} color={C.amber} />
            <StatCard label="Trend"
              value={ov.trend_pct == null ? ov.trend.toUpperCase() : `${ov.trend_pct > 0 ? "+" : ""}${ov.trend_pct}%`}
              sub={`vs prev ${ov.window_hours}h (${ov.prev_window_total})`} icon={TrendIcon} color={trendColor} />
            <StatCard label="Congestion" value={ov.congestion}
              sub="busiest-camera flow" icon={Gauge} color={CONGESTION_COLOR[ov.congestion] || C.muted} />
            <StatCard label="Active cameras" value={ov.active_cameras}
              sub={`${ov.readable_plates} readable / ${ov.unknown_plates} unknown`} icon={MapPin} color={C.green} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: 12, marginBottom: 12 }}>
            <MiniBarList title="Vehicle type distribution" icon={Car} items={typeItems}
              emptyHint="No detections in window" />
            <MiniBarList title="Top cameras by volume" icon={MapPin} items={camItems}
              emptyHint="No detections in window" />
          </div>

          {/* hourly / daily trend */}
          <div style={{ ...panel, padding: 12, marginBottom: 12 }}>
            <div style={sectionHead}>
              Traffic trend · {trends?.bucket === "day" ? "daily" : "hourly"} ({trends?.total || 0} total)
            </div>
            {trends?.series?.length ? (
              <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 90, overflowX: "auto", paddingTop: 8 }}>
                {trends.series.map((s) => (
                  <div key={s.bucket} title={`${s.bucket} · ${s.total} (${s.readable} readable)`}
                    style={{
                      flex: "1 0 8px", minWidth: 8,
                      height: `${Math.max(4, (s.total / maxBucket) * 100)}%`,
                      background: C.accent, borderRadius: "2px 2px 0 0", opacity: 0.85,
                    }} />
                ))}
              </div>
            ) : (
              <div style={{ color: C.dim, fontSize: 11, padding: "6px 0" }}>No activity in window</div>
            )}
          </div>

          {/* heatmap */}
          <div style={{ ...panel, padding: 12, marginBottom: 12 }}>
            <div style={{ ...sectionHead, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
              <span>
                Density heatmap · {heat?.contributing_cameras || 0}/{heat?.geolocated_cameras || 0} geolocated cameras
              </span>
              <div style={{ display: "flex", gap: 4 }}>
                {HEAT_KINDS.map((k) => (
                  <button key={k.key} onClick={() => setHeatKind(k.key)} style={pill(heatKind === k.key)}>
                    {k.label}
                  </button>
                ))}
              </div>
            </div>
            <GisMap height={340}>
              {(heat?.points || []).filter((p) => p.count > 0).map((p) => (
                <CircleMarker key={p.camera_id}
                  center={[p.latitude, p.longitude]}
                  radius={8 + p.weight * 22}
                  pathOptions={{
                    color: C.amber, fillColor: C.amber,
                    fillOpacity: 0.15 + p.weight * 0.5, weight: 1,
                  }}>
                  <Tooltip>
                    <b>{p.camera_code}</b> — {p.count} {heatKind.replace("_density", "")}
                    {p.camera_name ? <><br />{p.camera_name}</> : null}
                  </Tooltip>
                </CircleMarker>
              ))}
            </GisMap>
            <div style={{ color: C.dim, fontSize: 9.5, marginTop: 6 }}>
              {heat?.note || "Only geolocated cameras contribute. No coordinates are fabricated."}
            </div>
          </div>

          {/* per-camera table */}
          <div style={panel}>
            <div style={{ ...sectionHead, padding: "10px 14px", borderBottom: `1px solid ${C.border}` }}>
              Per-camera breakdown
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ color: C.muted, textAlign: "left", fontSize: 10, textTransform: "uppercase" }}>
                    <th style={th}>Camera</th><th style={th}>Vehicles</th><th style={th}>/ hour</th>
                    <th style={th}>Readable</th><th style={th}>Busiest hour</th><th style={th}>Congestion</th>
                  </tr>
                </thead>
                <tbody>
                  {(cams?.cameras || []).map((c) => (
                    <tr key={c.camera_id} style={{ borderTop: `1px solid ${C.border}` }}>
                      <td style={td}>
                        <div style={{ fontFamily: "monospace", color: C.accent }}>{c.camera_code || c.camera_id}</div>
                        <div style={{ color: C.muted }}>{c.camera_name}</div>
                      </td>
                      <td style={{ ...td, fontFamily: "monospace" }}>{c.total_vehicles}</td>
                      <td style={{ ...td, fontFamily: "monospace", color: C.muted }}>{c.vehicles_per_hour}</td>
                      <td style={{ ...td, fontFamily: "monospace", color: C.muted }}>{c.readable_plates}</td>
                      <td style={{ ...td, color: C.muted }}>
                        {c.busiest_hour ? new Date(c.busiest_hour.hour).toLocaleString("en-IN", { hour: "2-digit", day: "2-digit", month: "short" }) : "—"}
                      </td>
                      <td style={td}>
                        <span style={{ color: CONGESTION_COLOR[c.congestion] || C.muted, fontWeight: 700, fontSize: 11 }}>
                          {c.congestion}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!cams?.cameras?.length && (
                <EmptyState icon={Car} title="No traffic in window" hint="Widen the time window or clear filters." />
              )}
            </div>
          </div>
        </>
      ) : (
        <EmptyState icon={Gauge} title="No traffic data" hint="No vehicle events recorded yet." />
      )}
    </div>
  );
}

const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" };
const sectionHead = { fontWeight: 600, fontSize: 12, color: C.text, marginBottom: 8 };
const th = { padding: "9px 12px" };
const td = { padding: "9px 12px", verticalAlign: "top" };
const input = { background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "5px 9px", fontSize: 11 };
const pill = (active) => ({
  background: active ? C.accentGlow : "transparent",
  border: `1px solid ${active ? C.accent : C.border}`,
  color: active ? C.accent : C.muted,
  borderRadius: 4, padding: "4px 10px", fontSize: 10, fontWeight: 700, cursor: "pointer",
});
