import { useEffect, useState } from "react";
import { Gauge } from "lucide-react";
import { C } from "../../theme.js";
import { http } from "../../services/api.js";
import { fmtRelative } from "../../utils/datetime.js";

// Phase 15G — lightweight observability snapshot (/system/metrics/summary).
// Live queries + the pipeline's last pushed snapshot. No time-series store.
export default function MetricsSummaryPanel() {
  const [m, setM] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    const load = () => http.get("/system/metrics/summary")
      .then((r) => alive && setM(r.data))
      .catch((e) => alive && setErr(e?.response?.data?.error?.message || "metrics unavailable"));
    load();
    const t = setInterval(load, 15000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const p = m?.pipeline || {};
  const a = m?.anpr || {};

  return (
    <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6, padding: "10px 12px", flex: "1 1 320px", minWidth: 300 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, color: C.muted, fontSize: 10, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
        <Gauge size={11} /> Observability
      </div>
      {err ? (
        <div style={{ color: C.dim, fontSize: 11 }}>{err}</div>
      ) : !m ? (
        <div style={{ color: C.dim, fontSize: 11 }}>Loading…</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 12px", fontSize: 11 }}>
          <Row k="Pipeline" v={p.reported ? (p.stale ? "STALE" : "reporting") : "not reporting"}
            color={p.reported && !p.stale ? C.green : C.amber} />
          {p.reported && <Row k="Processed FPS" v={p.processed_fps ?? "—"} />}
          {p.reported && <Row k="Workers" v={`${p.num_workers ?? "—"} · ${p.cameras_processing ?? "—"} cams`} />}
          {p.reported && <Row k="Queue depth" v={`${p.event_queue_depth ?? 0} / ${p.event_queue_max_depth ?? "—"}`} />}
          {p.reported && <Row k="Events" v={`${p.events_delivered ?? 0} ok · ${p.events_dropped ?? 0} dropped`} />}
          {p.reported && <Row k="YOLO / OCR p50" v={`${fmtMs(p.yolo_p50_ms)} / ${fmtMs(p.ocr_p50_ms)}`} />}
          <Row k={`ANPR (${m.window_hours}h)`} v={a.window_total
            ? `${Math.round((a.success_rate || 0) * 100)}% of ${a.window_total}` : "no data"} />
          {Object.keys(a.failure_reasons || {}).length > 0 && (
            <Row k="Top failures" v={Object.entries(a.failure_reasons).slice(0, 2).map(([r, n]) => `${r}×${n}`).join(" ")} />
          )}
          <Row k="Cameras" v={`${m.cameras.online}/${m.cameras.total} online · ${m.cameras.cumulative_reconnects} reconnects`} />
          <Row k="Open work" v={`${m.alerts.new} alert · ${m.incidents.open} inc · ${m.cases.open} case`} />
          {p.reported_at && <Row k="Snapshot age" v={fmtRelative(p.reported_at)} />}
        </div>
      )}
    </div>
  );
}

const fmtMs = (v) => (v == null ? "—" : `${Math.round(v)}ms`);

function Row({ k, v, color }) {
  return (
    <>
      <span style={{ color: C.muted }}>{k}</span>
      <span style={{ color: color || C.text, fontFamily: "monospace", textAlign: "right" }}>{String(v)}</span>
    </>
  );
}
