import { useEffect, useState } from "react";
import { FileBarChart, FileDown } from "lucide-react";
import { C } from "../theme.js";
import { useToast } from "../context/ToastContext.jsx";
import { downloadReport, listReports } from "../services/opsApi.js";
import EmptyState from "../components/ui/EmptyState.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";

// Reports Center (Phase 11 FEATURE 9). Every report is a bounded PostgreSQL
// aggregate over existing tables — CSV export (PDF deferred; the on-screen
// table can be printed).
export default function ReportsPage() {
  const { push } = useToast();
  const [reports, setReports] = useState(null);
  const [loading, setLoading] = useState(true);
  const [f, setF] = useState({ date_from: "", date_to: "", camera_code: "", department: "", severity: "", plate: "" });
  const [busy, setBusy] = useState("");

  useEffect(() => {
    listReports().then(setReports).catch(() => setReports([])).finally(() => setLoading(false));
  }, []);

  const run = async (r) => {
    setBusy(r.key);
    try {
      const params = {};
      for (const [k, v] of Object.entries(f)) if (v) params[k] = v;
      if (r.needs_plate && !params.plate) {
        push({ title: "This report needs a plate", severity: "high" });
        return;
      }
      await downloadReport(r.key, params);
      push({ title: `${r.name} exported`, severity: "medium" });
    } catch (e) {
      push({ title: "Export failed", msg: e?.response?.data?.error?.message || "", severity: "high" });
    } finally {
      setBusy("");
    }
  };

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <FileBarChart size={16} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>Reports Center</span>
      </div>
      <div style={{ color: C.muted, fontSize: 11, marginBottom: 12 }}>
        Operational reports over real data. Filters apply to every report where relevant.
      </div>

      <div style={{ ...panel, padding: 12, marginBottom: 14, display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 8 }}>
        <F label="Date from"><input type="datetime-local" value={f.date_from} onChange={(e) => setF({ ...f, date_from: e.target.value })} style={input} /></F>
        <F label="Date to"><input type="datetime-local" value={f.date_to} onChange={(e) => setF({ ...f, date_to: e.target.value })} style={input} /></F>
        <F label="Camera code"><input value={f.camera_code} onChange={(e) => setF({ ...f, camera_code: e.target.value })} style={input} /></F>
        <F label="Department / location"><input value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })} style={input} /></F>
        <F label="Severity / priority"><select value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value })} style={input}><option value="">Any</option>{["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((s) => <option key={s}>{s}</option>)}</select></F>
        <F label="Plate (journey report)"><input value={f.plate} onChange={(e) => setF({ ...f, plate: e.target.value })} style={{ ...input, fontFamily: "monospace" }} /></F>
      </div>

      {loading ? (
        <SkeletonRows rows={5} height={44} />
      ) : !reports?.length ? (
        <EmptyState icon={FileBarChart} title="No reports available" />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 10 }}>
          {reports.map((r) => (
            <div key={r.key} style={{ ...panel, padding: 14, display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{r.name}</div>
              {r.needs_plate && <div style={{ color: C.amber, fontSize: 10 }}>requires a plate filter</div>}
              <button style={btn} disabled={busy === r.key} onClick={() => run(r)}>
                <FileDown size={12} /> {busy === r.key ? "Generating…" : "Export CSV"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const F = ({ label, children }) => (
  <label style={{ fontSize: 10, color: C.muted, display: "flex", flexDirection: "column", gap: 3 }}>{label}{children}</label>
);
const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" };
const input = { background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "5px 8px", fontSize: 11 };
const btn = { display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, background: C.accent, color: "#0b0f14", border: "none", borderRadius: 4, padding: "8px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer" };
