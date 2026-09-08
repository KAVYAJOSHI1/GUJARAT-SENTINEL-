import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FolderOpen, Plus, RefreshCw } from "lucide-react";
import { C } from "../theme.js";
import { canManageOps } from "../services/api.js";
import { useToast } from "../context/ToastContext.jsx";
import { createCase, listCases } from "../services/opsApi.js";
import SeverityBadge from "../components/SeverityBadge.jsx";
import StatusBadge from "../components/ops/StatusBadge.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import { Pager } from "./IncidentsPage.jsx";
import { fmtDateTime, fmtRelative } from "../utils/datetime.js";

const STATUSES = ["", "OPEN", "INVESTIGATING", "ON_HOLD", "RESOLVED", "CLOSED"];
const PAGE = 25;

export default function CasesPage() {
  const navigate = useNavigate();
  const { push } = useToast();
  const manage = canManageOps();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState({ title: "", primary_plate_number: "", priority_level: "MEDIUM", description: "" });
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const params = { limit: PAGE, offset };
      if (status) params.status = status;
      if (q.trim()) params.q = q.trim();
      setData(await listCases(params));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [offset, status, q]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setOffset(0); }, [status]);

  const submitNew = async () => {
    setCreating(true);
    try {
      const c = await createCase(form);
      push({ title: `Case ${c.case_number} created`, severity: "medium" });
      navigate(`/cases/${c.id}`);
    } catch (e) {
      push({ title: "Could not create case", msg: e?.response?.data?.error?.message || "", severity: "high" });
    } finally {
      setCreating(false);
    }
  };

  const items = data?.items || [];
  const total = data?.total || 0;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <FolderOpen size={16} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>Investigation Cases</span>
        <span style={{ color: C.muted, fontSize: 12 }}>· {total}</span>
        <button onClick={load} style={iconBtn} title="Refresh"><RefreshCw size={12} /></button>
        {manage && (
          <button onClick={() => setShowNew((v) => !v)} style={{ ...iconBtn, color: C.accent, marginLeft: "auto" }}>
            <Plus size={12} /> New case
          </button>
        )}
      </div>
      <div style={{ color: C.muted, fontSize: 11, marginBottom: 12 }}>
        A case groups incidents, evidence and officer notes around a vehicle or line of enquiry.
      </div>

      {error && <ErrorBanner message="Could not load cases from the backend." onRetry={load} />}

      {showNew && manage && (
        <div style={{ ...panel, padding: 12, marginBottom: 12, display: "flex", flexDirection: "column", gap: 8 }}>
          <input placeholder="Case title *" value={form.title}
                 onChange={(e) => setForm({ ...form, title: e.target.value })} style={inputStyle} />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input placeholder="Primary vehicle plate (optional)" value={form.primary_plate_number}
                   onChange={(e) => setForm({ ...form, primary_plate_number: e.target.value })}
                   style={{ ...inputStyle, flex: "1 1 200px" }} />
            <select value={form.priority_level} onChange={(e) => setForm({ ...form, priority_level: e.target.value })} style={inputStyle}>
              {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <textarea placeholder="Description (optional)" rows={2} value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                    style={{ ...inputStyle, resize: "vertical" }} />
          <div>
            <button style={primaryBtn} disabled={creating || !form.title.trim()} onClick={submitNew}>
              {creating ? "Creating…" : "Create case"}
            </button>
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12, alignItems: "center" }}>
        <label style={{ fontSize: 11, color: C.muted, display: "flex", alignItems: "center", gap: 5 }}>
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)} style={inputStyle}>
            {STATUSES.map((s) => <option key={s} value={s}>{s || "All"}</option>)}
          </select>
        </label>
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()}
               placeholder="Search title / CASE-number…" style={{ ...inputStyle, flex: "1 1 220px" }} />
      </div>

      <div style={panel}>
        {loading ? (
          <div style={{ padding: 14 }}><SkeletonRows rows={5} height={44} /></div>
        ) : items.length === 0 ? (
          <EmptyState icon={FolderOpen} title="No cases" hint={manage ? "Create the first case above." : "No cases have been opened."} />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ color: C.muted, textAlign: "left", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.6 }}>
                  <th style={th}>Case</th><th style={th}>Vehicle</th><th style={th}>Priority</th>
                  <th style={th}>Links</th><th style={th}>Assigned</th><th style={th}>Status</th><th style={th}>Updated</th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id} onClick={() => navigate(`/cases/${c.id}`)}
                      style={{ borderTop: `1px solid ${C.border}`, cursor: "pointer" }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = C.panel)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                    <td style={td}>
                      <div style={{ fontFamily: "monospace", color: C.accent }}>{c.case_number}</div>
                      <div style={{ color: C.text, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.title}</div>
                    </td>
                    <td style={{ ...td, fontFamily: "monospace", color: C.amber }}>{c.primary_plate_normalized || "—"}</td>
                    <td style={td}><SeverityBadge s={String(c.priority_level).toLowerCase()} /></td>
                    <td style={{ ...td, color: C.muted }}>
                      {c.incident_count} inc · {c.evidence_count} ev · {c.note_count} notes
                    </td>
                    <td style={{ ...td, color: c.assigned_to_username ? C.text : C.dim }}>{c.assigned_to_username || "Unassigned"}</td>
                    <td style={td}><StatusBadge status={c.status} kind="case" /></td>
                    <td style={{ ...td, color: C.muted }} title={fmtDateTime(c.updated_at)}>{fmtRelative(c.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Pager offset={offset} total={total} onPage={setOffset} loading={loading} page={PAGE} />
    </div>
  );
}

const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" };
const th = { padding: "10px 12px" };
const td = { padding: "10px 12px", verticalAlign: "top" };
const inputStyle = { background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "6px 8px", fontSize: 12 };
const iconBtn = { ...inputStyle, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4 };
const primaryBtn = { background: C.accent, color: "#0b0f14", border: "none", borderRadius: 4, padding: "7px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer" };
