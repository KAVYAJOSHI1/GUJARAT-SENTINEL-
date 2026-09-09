import { useEffect, useState } from "react";
import { Gauge } from "lucide-react";
import { C } from "../../theme.js";
import { http } from "../../services/api.js";

// Phase 17 Step 12 -- /system/capacity. Extends the existing System page
// observability row rather than a new standalone dashboard. Shows current
// load, the measured/assumed capacity model, and the 80,000-camera scaling
// calculation -- never presented as "80,000 cameras supported today".
const STATE_COLOR = { HEALTHY: C.green, DEGRADED: C.amber, OVERLOADED: C.red };

export default function CapacityPanel() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    const load = () => http.get("/system/capacity")
      .then((r) => alive && setD(r.data))
      .catch((e) => alive && setErr(e?.response?.data?.error?.message || "capacity data unavailable"));
    load();
    const t = setInterval(load, 20000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  return (
    <section style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden", flex: "1 1 420px", minWidth: 360 }}>
      <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 8 }}>
        <Gauge size={13} color={C.accent} />
        <span style={{ fontWeight: 600, fontSize: 12 }}>System Capacity</span>
        {d && (
          <span
            style={{
              marginLeft: "auto", fontSize: 9.5, fontWeight: 700, letterSpacing: 0.5,
              color: STATE_COLOR[d.degradation.state] || C.muted,
              border: `1px solid ${(STATE_COLOR[d.degradation.state] || C.muted)}55`,
              borderRadius: 3, padding: "1px 6px",
            }}
          >
            {d.degradation.state}
          </span>
        )}
      </div>
      <div style={{ padding: 12 }}>
        {err && <div style={{ color: C.dim, fontSize: 11 }}>{err}</div>}
        {!err && !d && <div style={{ color: C.dim, fontSize: 11 }}>Loading…</div>}
        {d && (
          <>
            {d.degradation.reasons.length > 0 && (
              <div style={{ fontSize: 10.5, color: STATE_COLOR[d.degradation.state], marginBottom: 8 }}>
                Reason: {d.degradation.reasons.join("; ")}
              </div>
            )}

            <Section title="Current">
              <Row k="Cameras" v={`${d.current.cameras_total} total · ${d.current.cameras_active} active${d.current.cameras_processing != null ? ` · ${d.current.cameras_processing} processing` : ""}`} />
              <Row k="AI workers" v={d.current.workers ?? "—"} />
              <Row k="CPU" v={d.health.cpu_percent != null ? `${d.health.cpu_percent.toFixed(0)}%` : "—"} />
              <Row k="Queue depth" v={`${d.health.event_queue_depth ?? "—"} / ${d.health.event_queue_max_depth ?? "—"}`} />
            </Section>

            <Section title="Scaling toward 80,000">
              <Row k="Measured worker budget" v={`${d.scaling.measured_worker_capacity} fps`} />
              <Row k="Effective cameras/worker" v={d.scaling.effective_cameras_per_worker} />
              <Row k="Estimated current capacity" v={d.scaling.estimated_current_capacity} />
              <Row k="Target" v={d.scaling.target_capacity.toLocaleString("en-IN")} />
              <Row k="Required workers" v={d.scaling.required_workers_for_target.toLocaleString("en-IN")} />
              <Row k="Per region (÷ ~5, simulated)" v={d.scaling.workers_per_region.toLocaleString("en-IN")} />
              {d.scaling.estimated_gpu_count != null && (
                <Row k="Est. GPUs (unverified)" v={d.scaling.estimated_gpu_count.toLocaleString("en-IN")} />
              )}
              <Row k="Est. ingress bandwidth" v={`${d.scaling.estimated_ingress_bandwidth_gbps.toFixed(2)} Gbps`} />
              <Row k="Est. evidence storage" v={`${d.scaling.estimated_storage_tb_per_day.toFixed(2)} TB/day`} />
            </Section>

            <div style={{ fontSize: 9.5, color: C.dim, marginTop: 8, lineHeight: 1.5 }}>
              {d.capacity_model.measured.source}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ color: C.muted, fontSize: 9.5, textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>{title}</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "3px 12px", fontSize: 11 }}>
        {children}
      </div>
    </div>
  );
}

function Row({ k, v }) {
  return (
    <>
      <span style={{ color: C.muted }}>{k}</span>
      <span style={{ color: C.text, fontFamily: "monospace", textAlign: "right" }}>{v}</span>
    </>
  );
}
