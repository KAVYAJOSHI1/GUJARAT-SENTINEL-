import { useEffect, useMemo, useState } from "react";
import { Activity, Car, Clock, ScanLine, TrendingDown } from "lucide-react";
import { C } from "../theme.js";
import StatCard from "../components/StatCard.jsx";
import MiniBarList from "../components/analytics/MiniBarList.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import { http } from "../services/api.js";

const WINDOWS = [{ h: 6, l: "6h" }, { h: 24, l: "24h" }, { h: 168, l: "7d" }, { h: 720, l: "30d" }];
const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const rateColor = (r) => (r == null ? C.muted : r >= 0.8 ? C.green : r >= 0.55 ? C.amber : C.red);

// Phase 15H §10 — ANPR performance dashboard. SQL aggregates over
// vehicle_events. "Success rate" is a throughput/quality signal, NOT an
// accuracy measurement (no ground-truth set for the government feeds).
export default function AnprIntelligencePage() {
  const [hours, setHours] = useState(24);
  const [camera, setCamera] = useState("");
  const [vtype, setVtype] = useState("");
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const params = useMemo(() => ({
    window_hours: hours, camera_code: camera || undefined, vehicle_type: vtype || undefined,
  }), [hours, camera, vtype]);

  async function load() {
    setLoading(true); setErr("");
    try {
      const r = await http.get("/analytics/anpr", { params });
      setD(r.data);
    } catch (e) {
      setErr(e?.response?.data?.error?.message || "Failed to load ANPR analytics");
    } finally { setLoading(false); }
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [params]);

  const reasonItems = Object.entries(d?.failure_reasons || {}).map(([k, v]) => ({ label: k, value: v, color: C.red }));
  const maxHour = Math.max(1, ...(d?.by_hour || []).map((h) => h.total));
  const maxConf = Math.max(1, ...(d?.confidence_distribution || []).map((b) => b.count));

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <ScanLine size={16} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>ANPR Intelligence</span>
        <span style={{ color: C.muted, fontSize: 11 }}>plate-recognition throughput &amp; quality · live aggregates</span>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", margin: "10px 0 14px" }}>
        <div style={{ display: "flex", gap: 4 }}>
          {WINDOWS.map((w) => (
            <button key={w.h} onClick={() => setHours(w.h)} style={pill(hours === w.h)}>{w.l}</button>
          ))}
        </div>
        <input value={camera} onChange={(e) => setCamera(e.target.value.toUpperCase())} placeholder="camera code" style={input} />
        <input value={vtype} onChange={(e) => setVtype(e.target.value)} placeholder="vehicle type" style={input} />
      </div>

      {err && <ErrorBanner message={err} onRetry={load} />}

      {loading && !d ? (
        <div style={panel}><div style={{ padding: 14 }}><SkeletonRows rows={6} height={34} /></div></div>
      ) : d ? (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
            <StatCard label="Vehicles" value={d.total_vehicles.toLocaleString("en-IN")} sub={`${hours}h`} icon={Car} color={C.accent} />
            <StatCard label="Readable plates" value={d.readable_plates.toLocaleString("en-IN")} sub={`${d.unknown_plates} unknown`} icon={ScanLine} color={C.green} />
            <StatCard label="ANPR success rate" value={pct(d.success_rate)} sub="detections -> validated plate" icon={Activity} color={rateColor(d.success_rate)} />
            <StatCard label="Low-quality frames" value={d.low_quality_frames} sub={`mean quality ${d.mean_quality_score ?? "—"}`} icon={TrendingDown} color={d.low_quality_frames > 0 ? C.amber : C.green} />
            <StatCard label="OCR latency p50" value={d.ocr_p50_ms != null ? `${Math.round(d.ocr_p50_ms)}ms` : "—"} sub={d.ocr_p95_ms != null ? `p95 ${Math.round(d.ocr_p95_ms)}ms` : "no pipeline snapshot"} icon={Clock} color={C.violet} />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: 12, marginBottom: 12 }}>
            <MiniBarList title="Failure reasons" icon={TrendingDown} items={reasonItems} emptyHint="No failed reads in window" />
            <div style={{ ...panel, padding: 12 }}>
              <div style={sectionHead}>Plate-confidence distribution (readable)</div>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 80, paddingTop: 6 }}>
                {(d.confidence_distribution || []).map((b) => (
                  <div key={b.bucket} title={`${b.bucket}: ${b.count}`} style={{ flex: 1, textAlign: "center" }}>
                    <div style={{ height: `${Math.max(3, (b.count / maxConf) * 70)}px`, background: C.accent, borderRadius: "2px 2px 0 0", opacity: 0.85 }} />
                    <div style={{ fontSize: 7, color: C.dim, marginTop: 2 }}>{b.bucket.split("-")[0]}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div style={{ ...panel, padding: 12, marginBottom: 12 }}>
            <div style={sectionHead}>ANPR success by hour</div>
            {d.by_hour?.length ? (
              <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 90, overflowX: "auto", paddingTop: 6 }}>
                {d.by_hour.map((h) => (
                  <div key={h.hour} title={`${h.hour} · ${h.readable}/${h.total} (${pct(h.success_rate)})`}
                    style={{ flex: "1 0 8px", minWidth: 8, display: "flex", flexDirection: "column", justifyContent: "flex-end", height: "100%" }}>
                    <div style={{ height: `${(h.total / maxHour) * 100}%`, background: C.dim, borderRadius: "2px 2px 0 0", position: "relative" }}>
                      <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: `${(h.success_rate || 0) * 100}%`, background: rateColor(h.success_rate), borderRadius: "2px 2px 0 0" }} />
                    </div>
                  </div>
                ))}
              </div>
            ) : <div style={{ color: C.dim, fontSize: 11 }}>No activity in window</div>}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }} className="anpr-cam-grid">
            <CamTable title="Best cameras" rows={d.top_cameras} />
            <CamTable title="Worst cameras" rows={d.worst_cameras} />
          </div>

          <div style={{ color: C.dim, fontSize: 9.5 }}>{d.disclaimer}</div>
        </>
      ) : (
        <EmptyState icon={ScanLine} title="No ANPR data" hint="No vehicle detections recorded." />
      )}
    </div>
  );
}

function CamTable({ title, rows }) {
  return (
    <div style={panel}>
      <div style={{ ...sectionHead, padding: "9px 12px", borderBottom: `1px solid ${C.border}` }}>{title}</div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
        <tbody>
          {(rows || []).map((c) => (
            <tr key={c.camera_code} style={{ borderTop: `1px solid ${C.border}` }}>
              <td style={{ padding: "6px 12px", fontFamily: "monospace", color: C.accent }}>{c.camera_code}</td>
              <td style={{ padding: "6px 12px", color: C.muted }}>{c.camera_name || ""}</td>
              <td style={{ padding: "6px 12px", fontFamily: "monospace", color: C.muted }}>{c.readable}/{c.total}</td>
              <td style={{ padding: "6px 12px", fontFamily: "monospace", color: rateColor(c.success_rate), fontWeight: 700, textAlign: "right" }}>
                {pct(c.success_rate)}
              </td>
            </tr>
          ))}
          {!rows?.length && <tr><td style={{ padding: 12, color: C.dim, fontSize: 11 }}>Not enough data</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" };
const sectionHead = { fontWeight: 600, fontSize: 12, color: C.text, marginBottom: 8 };
const input = { background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "5px 9px", fontSize: 11 };
const pill = (a) => ({ background: a ? C.accentGlow : "transparent", border: `1px solid ${a ? C.accent : C.border}`, color: a ? C.accent : C.muted, borderRadius: 4, padding: "4px 10px", fontSize: 10, fontWeight: 700, cursor: "pointer" });
