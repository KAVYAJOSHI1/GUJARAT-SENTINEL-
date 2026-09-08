import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, ChevronRight, HeartPulse, RefreshCw, ShieldAlert } from "lucide-react";
import { C } from "../theme.js";
import StatCard from "../components/StatCard.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import { fmtDateTime } from "../utils/datetime.js";
import { cameraIntelligence, cameraReliability } from "../services/cameraIntelApi.js";

const WINDOWS = [{ h: 24, l: "24h" }, { h: 72, l: "3d" }, { h: 168, l: "7d" }];
const REL_COLOR = { HIGH: C.green, MEDIUM: C.amber, LOW: C.red, UNKNOWN: C.muted };
const VQ_COLOR = { GOOD: C.green, FAIR: C.amber, POOR: C.red, UNKNOWN: C.muted };

// Phase 14 §9 — Camera Reliability Intelligence. A statistical view of
// recent camera stability from camera_health_history. NOT failure
// prediction — the page never claims a camera will fail.
export default function CameraIntelligencePage() {
  const [hours, setHours] = useState(24);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [detail, setDetail] = useState(null);

  async function load() {
    setLoading(true);
    setErr("");
    try {
      setData(await cameraIntelligence(hours));
    } catch (e) {
      setErr(e?.response?.data?.error?.message || "Failed to load camera intelligence");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [hours]);

  async function openDetail(code) {
    try { setDetail(await cameraReliability(code, hours)); } catch { /* ignore */ }
  }

  const cams = data?.cameras || [];
  const scored = cams.filter((c) => c.health_score != null);
  const avg = scored.length
    ? Math.round(scored.reduce((s, c) => s + c.health_score, 0) / scored.length) : "—";

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <HeartPulse size={16} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>Camera Reliability Intelligence</span>
        <span style={{ color: C.muted, fontSize: 11 }}>
          recent stability from health history · not failure prediction
        </span>
        <button onClick={load} style={iconBtn} title="Refresh"><RefreshCw size={12} /></button>
      </div>

      <div style={{ display: "flex", gap: 4, margin: "10px 0 14px" }}>
        {WINDOWS.map((w) => (
          <button key={w.h} onClick={() => setHours(w.h)} style={pill(hours === w.h)}>{w.l}</button>
        ))}
      </div>

      {err && <ErrorBanner message={err} onRetry={load} />}

      {loading && !data ? (
        <div style={panel}><div style={{ padding: 14 }}><SkeletonRows rows={6} height={34} /></div></div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
            <StatCard label="Cameras" value={data?.camera_count ?? 0} sub={`${hours}h window`} icon={Activity} color={C.accent} />
            <StatCard label="Avg health score" value={avg} sub="0–100 (higher = healthier)" icon={HeartPulse} color={C.violet} />
            <StatCard label="Showing degradation" value={data?.degraded_count ?? 0}
              sub="recent instability observed" icon={ShieldAlert}
              color={(data?.degraded_count ?? 0) > 0 ? C.amber : C.green} />
            <StatCard label="Poor video quality" value={data?.poor_video_count ?? 0}
              sub="online but unusable video" icon={ShieldAlert}
              color={(data?.poor_video_count ?? 0) > 0 ? C.red : C.green} />
          </div>

          <div style={panel}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ color: C.muted, textAlign: "left", fontSize: 10, textTransform: "uppercase" }}>
                    <th style={th}>Camera</th><th style={th}>Status</th><th style={th}>Health</th>
                    <th style={th}>Reliability</th><th style={th}>Video quality</th><th style={th}>ANPR OK</th>
                    <th style={th}>Disconnects</th><th style={th}>FPS</th>
                    <th style={th}>Observations</th><th style={th} />
                  </tr>
                </thead>
                <tbody>
                  {cams.map((c) => (
                    <tr key={c.camera_id} onClick={() => openDetail(c.camera_code)}
                      style={{ borderTop: `1px solid ${C.border}`, cursor: "pointer" }}>
                      <td style={td}>
                        <div style={{ fontFamily: "monospace", color: C.accent }}>{c.camera_code || c.camera_id}</div>
                        <div style={{ color: C.muted }}>{c.camera_name}</div>
                      </td>
                      <td style={{ ...td, color: c.current_status === "ONLINE" ? C.green : C.red, fontWeight: 700, fontSize: 11 }}>
                        {c.current_status}
                      </td>
                      <td style={{ ...td, fontFamily: "monospace" }}>
                        {c.health_score == null ? "—" : (
                          <span style={{ color: c.health_score >= 80 ? C.green : c.health_score >= 55 ? C.amber : C.red }}>
                            {c.health_score}
                          </span>
                        )}
                      </td>
                      <td style={td}>
                        <span style={{ color: REL_COLOR[c.reliability_score] || C.muted, fontWeight: 700, fontSize: 11 }}>
                          {c.reliability_score}
                        </span>
                        {c.degradation_indicator && (
                          <span style={{ marginLeft: 5, fontSize: 8, color: C.amber, border: `1px solid ${C.amber}`, borderRadius: 3, padding: "0 3px" }}>
                            DEGRADING
                          </span>
                        )}
                      </td>
                      <td style={td}>
                        <span style={{ color: VQ_COLOR[c.video_quality_label] || C.muted, fontWeight: 700, fontSize: 11 }}>
                          {c.video_quality_label}
                        </span>
                        {c.video_quality_score != null && (
                          <span style={{ color: C.dim, fontFamily: "monospace", marginLeft: 4 }}>{c.video_quality_score}</span>
                        )}
                      </td>
                      <td style={{ ...td, fontFamily: "monospace", color: c.anpr_success_rate != null && c.anpr_success_rate < 0.6 ? C.red : C.muted }}>
                        {c.anpr_success_rate != null ? `${Math.round(c.anpr_success_rate * 100)}%` : "—"}
                      </td>
                      <td style={{ ...td, fontFamily: "monospace", color: c.disconnect_count ? C.amber : C.muted }}>
                        {c.disconnect_count}
                        {c.mean_recovery_seconds ? ` (~${Math.round(c.mean_recovery_seconds)}s)` : ""}
                      </td>
                      <td style={{ ...td, fontFamily: "monospace", color: c.fps_degraded ? C.red : C.muted }}>
                        {c.stream_fps == null ? "—" : c.stream_fps.toFixed(1)}
                      </td>
                      <td style={{ ...td, fontFamily: "monospace", color: C.muted }}>
                        {c.detection_rate_per_hour}
                        {c.detection_rate_change_pct != null && c.detection_rate_change_pct < -20 && (
                          <span style={{ color: C.red }}> ↓{Math.abs(Math.round(c.detection_rate_change_pct))}%</span>
                        )}
                      </td>
                      <td style={{ ...td, color: C.muted, maxWidth: 260, fontSize: 10.5 }}>
                        {c.observations.slice(0, 2).join(" · ") || "stable"}
                      </td>
                      <td style={td}><ChevronRight size={13} color={C.dim} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!cams.length && <EmptyState icon={HeartPulse} title="No cameras" hint="Register cameras to see reliability intelligence." />}
            </div>
          </div>

          <div style={{ color: C.dim, fontSize: 9.5, marginTop: 8 }}>
            {data?.note}
          </div>
        </>
      )}

      {detail && (
        <div onClick={() => setDetail(null)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ ...panel, maxWidth: 620, width: "100%", maxHeight: "82vh", overflowY: "auto" }}>
            <div style={{ padding: "12px 16px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between" }}>
              <span style={{ fontWeight: 700 }}>{detail.camera_code} · {detail.camera_name}</span>
              <button onClick={() => setDetail(null)} style={{ ...iconBtn }}>✕</button>
            </div>
            <div style={{ padding: 16 }}>
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 10 }}>
                <Metric label="Health score" value={detail.health_score ?? "—"} color={REL_COLOR[detail.reliability_score]} />
                <Metric label="Reliability" value={detail.reliability_score} color={REL_COLOR[detail.reliability_score]} />
                <Metric label="Disconnects" value={detail.disconnect_count} />
                <Metric label="Avg recovery" value={detail.mean_recovery_seconds ? `${Math.round(detail.mean_recovery_seconds)}s` : "—"} />
                <Metric label="Reconnects" value={detail.reconnect_count} />
                <Metric label="Video quality" value={detail.video_quality_label}
                  color={VQ_COLOR[detail.video_quality_label]} />
                <Metric label="ANPR OK" value={detail.anpr_success_rate != null ? `${Math.round(detail.anpr_success_rate * 100)}%` : "—"} />
              </div>
              {(detail.video_quality_reasons || []).length > 0 && (
                <div style={{ fontSize: 10.5, color: C.amber, marginBottom: 8 }}>
                  Video quality: {detail.video_quality_reasons.join(" · ")}
                </div>
              )}
              <div style={{ fontSize: 9, fontWeight: 700, color: C.muted, letterSpacing: 0.6, marginBottom: 4 }}>OBSERVATIONS</div>
              {detail.observations.length ? detail.observations.map((o, i) => (
                <div key={i} style={{ fontSize: 11, color: C.text, padding: "2px 0" }}>• {o}</div>
              )) : <div style={{ fontSize: 11, color: C.muted }}>No instability observed in window.</div>}

              <div style={{ fontSize: 9, fontWeight: 700, color: C.muted, letterSpacing: 0.6, margin: "12px 0 4px" }}>
                HEALTH TRANSITIONS
              </div>
              {(detail.transitions || []).length ? detail.transitions.slice().reverse().map((t, i) => (
                <div key={i} style={{ display: "flex", gap: 8, fontSize: 10.5, padding: "2px 0" }}>
                  <span style={{ color: C.dim, fontFamily: "monospace", minWidth: 118 }}>{fmtDateTime(t.detected_at)}</span>
                  <span style={{ color: t.status === "ONLINE" ? C.green : C.red, minWidth: 62 }}>{t.status}</span>
                  <span style={{ color: C.muted }}>{t.previous_status ? `from ${t.previous_status}` : ""} · {t.source}</span>
                </div>
              )) : <div style={{ fontSize: 11, color: C.muted }}>No recorded transitions.</div>}

              <Link to={`/cameras/manage`} style={{ ...pill(false), display: "inline-block", marginTop: 12, textDecoration: "none" }}>
                Camera management console →
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, color }) {
  return (
    <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6, padding: "8px 12px", minWidth: 92 }}>
      <div style={{ color: C.muted, fontSize: 9, textTransform: "uppercase", letterSpacing: 0.8 }}>{label}</div>
      <div style={{ color: color || C.text, fontSize: 17, fontWeight: 700, fontFamily: "monospace" }}>{value}</div>
    </div>
  );
}

const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" };
const th = { padding: "9px 12px" };
const td = { padding: "9px 12px", verticalAlign: "top" };
const iconBtn = { background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "4px 8px", fontSize: 11, cursor: "pointer" };
const pill = (active) => ({
  background: active ? C.accentGlow : "transparent",
  border: `1px solid ${active ? C.accent : C.border}`,
  color: active ? C.accent : C.muted,
  borderRadius: 4, padding: "4px 10px", fontSize: 10, fontWeight: 700, cursor: "pointer",
});
