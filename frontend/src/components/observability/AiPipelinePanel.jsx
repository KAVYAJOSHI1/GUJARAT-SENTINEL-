import { Cpu as CpuIcon } from "lucide-react";
import { C } from "../../theme.js";

// Phase 7 — detailed AI-pipeline metrics from the pipeline's own
// get_metrics() self-report (via /dashboard/health -> ai_pipeline). Shows
// nothing it wasn't told: a null metric renders "—", and if the pipeline
// has never reported the whole panel says so.

function Metric({ label, value, unit, color = C.text }) {
  return (
    <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6, padding: "8px 12px", flex: "1 1 120px" }}>
      <div style={{ color: C.muted, fontSize: 9.5, textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>{label}</div>
      <div style={{ color, fontSize: 15, fontWeight: 700, fontFamily: "'Space Mono', monospace" }}>
        {value == null ? "—" : value}
        {value != null && unit ? <span style={{ fontSize: 10, color: C.muted, marginLeft: 3 }}>{unit}</span> : null}
      </div>
    </div>
  );
}

const fmt = (v, d = 0) => (v == null ? null : Number(v).toFixed(d));
const int = (v) => (v == null ? null : Number(v).toLocaleString("en-IN"));

export default function AiPipelinePanel({ health }) {
  const ai = health?.aiPipeline;

  const shell = (children) => (
    <section style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
      <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 600, fontSize: 12 }}>
          <CpuIcon size={13} color={C.accent} /> AI Pipeline Metrics
          {ai && ai.status !== "unknown" && (
            <span style={{ color: C.muted, fontWeight: 400 }}>
              · {ai.numWorkers != null ? `${ai.numWorkers} worker${ai.numWorkers === 1 ? "" : "s"} · ` : ""}
              reported {ai.ageSeconds != null ? `${Math.round(ai.ageSeconds)}s ago` : "—"}
            </span>
          )}
        </span>
        {ai && ai.status === "stale" && (
          <span style={{ color: C.amber, fontSize: 9.5, border: `1px solid ${C.amber}55`, borderRadius: 3, padding: "1px 6px" }}>STALE REPORT</span>
        )}
      </div>
      <div style={{ padding: 12 }}>{children}</div>
    </section>
  );

  if (!health) {
    return shell(<div style={{ color: C.muted, fontSize: 12 }}>System health feed unavailable — AI-pipeline metrics can&rsquo;t be shown (no estimated values).</div>);
  }
  if (!ai || ai.status === "unknown") {
    return shell(
      <div style={{ color: C.muted, fontSize: 12 }}>
        The AI pipeline has not reported metrics to this backend. Start it with a
        reachable <code>--backend-url</code> (it posts to <code>/api/v1/pipeline/status</code>
        every few seconds); until then, live FPS / queue / latency are genuinely unknown.
      </div>
    );
  }

  const dropped = ai.eventsDropped;
  return shell(
    <>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        <Metric label="Processed FPS" value={fmt(ai.processedFps, 2)} color={C.accent} />
        <Metric label="Frames processed" value={int(ai.framesProcessed)} />
        <Metric label="Vehicles detected" value={int(ai.vehiclesDetected)} color={C.violet} />
        <Metric label="Cameras processing" value={ai.camerasProcessing == null ? null : `${ai.camerasProcessing}`} />
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        <Metric label="Events generated" value={int(ai.eventsGenerated)} />
        <Metric label="Events delivered" value={int(ai.eventsDelivered)} color={C.green} />
        <Metric label="Events dropped" value={dropped == null ? null : int(dropped)} color={dropped > 0 ? C.red : C.muted} />
        <Metric label="Queue depth" value={ai.queueDepth == null ? null : `${ai.queueDepth}`} unit={ai.queueMaxDepth != null ? `(max ${ai.queueMaxDepth})` : ""} color={ai.queueDepth > 50 ? C.amber : C.text} />
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Metric label="YOLO p50 / p95" value={ai.yolo.p50 == null ? null : `${fmt(ai.yolo.p50)} / ${fmt(ai.yolo.p95)}`} unit="ms" />
        <Metric label="OCR p50 / p95" value={ai.ocr.p50 == null ? null : `${fmt(ai.ocr.p50)} / ${fmt(ai.ocr.p95)}`} unit="ms" />
        <Metric label="CPU" value={fmt(ai.cpuPercent)} unit="%" />
        <Metric label="RSS" value={ai.rssMb == null ? null : int(Math.round(ai.rssMb))} unit="MB" />
      </div>
    </>
  );
}
