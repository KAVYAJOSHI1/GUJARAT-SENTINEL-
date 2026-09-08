import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Briefcase, RefreshCw } from "lucide-react";
import { C } from "../theme.js";
import { fetchWorkQueue } from "../services/opsApi.js";
import SeverityBadge from "../components/SeverityBadge.jsx";
import StatusBadge from "../components/ops/StatusBadge.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import { fmtRelative, fmtDateTime } from "../utils/datetime.js";

const TABS = ["ALL", "INCIDENTS", "CASES", "ALERTS"];

// Officer Work Queue — "My Work" (Phase 11 FEATURE 12). Role-aware: the
// backend returns assigned work for OFFICER, all open work for ADMIN.
export default function MyWorkPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [sort, setSort] = useState("priority");
  const [tab, setTab] = useState("ALL");

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      setData(await fetchWorkQueue(sort));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [sort]);

  useEffect(() => { load(); }, [load]);

  const all = data
    ? [...(data.incidents || []), ...(data.cases || []), ...(data.alerts || [])]
    : [];
  const rows = tab === "ALL" ? all
    : tab === "INCIDENTS" ? (data?.incidents || [])
    : tab === "CASES" ? (data?.cases || [])
    : (data?.alerts || []);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <Briefcase size={16} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>My Work</span>
        {data && <span style={{ color: C.muted, fontSize: 12 }}>· {data.scope === "all" ? "all open work" : "assigned to you"}</span>}
        <button onClick={load} style={iconBtn} title="Refresh"><RefreshCw size={12} /></button>
      </div>

      {error && <ErrorBanner message="Could not load your work queue." onRetry={load} />}

      {data && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <Kpi label="Incidents" v={data.counts.incidents} />
          <Kpi label="Cases" v={data.counts.cases} />
          <Kpi label="Alerts" v={data.counts.alerts} />
          <Kpi label="Unacknowledged" v={data.counts.unacknowledged_alerts} color={C.red} />
          <Kpi label="Escalated" v={data.counts.escalated_alerts} color={C.amber} />
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12, alignItems: "center" }}>
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: tab === t ? C.accentGlow : "transparent",
            border: `1px solid ${tab === t ? C.accent : C.border}`,
            color: tab === t ? C.accent : C.muted, borderRadius: 4, padding: "4px 12px",
            fontSize: 11, cursor: "pointer",
          }}>{t}</button>
        ))}
        <select value={sort} onChange={(e) => setSort(e.target.value)} style={{ ...iconBtn, marginLeft: "auto" }}>
          {["priority", "newest", "oldest"].map((s) => <option key={s} value={s}>sort: {s}</option>)}
        </select>
      </div>

      <div style={panel}>
        {loading ? (
          <div style={{ padding: 14 }}><SkeletonRows rows={6} height={40} /></div>
        ) : rows.length === 0 ? (
          <EmptyState icon={Briefcase} title="Nothing pending" hint="Work assigned to you will appear here." />
        ) : (
          rows.map((w) => (
            <Link key={`${w.kind}-${w.id}`} to={w.href} style={{
              display: "block", padding: "10px 14px", borderTop: `1px solid ${C.border}`,
              textDecoration: "none",
            }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ fontSize: 9, fontWeight: 700, color: C.muted, minWidth: 56 }}>{w.kind}</span>
                <span style={{ fontFamily: "monospace", color: C.accent, fontSize: 11 }}>{w.ref}</span>
                <span style={{ color: C.text, fontSize: 12, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{w.title}</span>
                <SeverityBadge s={String(w.priority).toLowerCase()} />
                <StatusBadge status={w.status} kind={w.kind === "CASE" ? "case" : "incident"} />
                <span style={{ color: C.dim, fontSize: 10 }} title={fmtDateTime(w.created_at)}>{fmtRelative(w.created_at)}</span>
              </div>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}

function Kpi({ label, v, color = C.accent }) {
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 16px", minWidth: 110 }}>
      <div style={{ color: C.muted, fontSize: 9, textTransform: "uppercase", letterSpacing: 0.6 }}>{label}</div>
      <div style={{ color, fontSize: 20, fontWeight: 700 }}>{v ?? 0}</div>
    </div>
  );
}

const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" };
const iconBtn = { background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "5px 8px", fontSize: 11, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4 };
