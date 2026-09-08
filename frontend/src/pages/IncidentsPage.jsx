import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ClipboardList, RefreshCw } from "lucide-react";
import { C } from "../theme.js";
import { listIncidents } from "../services/opsApi.js";
import SeverityBadge from "../components/SeverityBadge.jsx";
import StatusBadge from "../components/ops/StatusBadge.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import { fmtDateTime, fmtRelative } from "../utils/datetime.js";

const STATUSES = ["", "NEW", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "CLOSED"];
const PRIORITIES = ["", "CRITICAL", "HIGH", "MEDIUM", "LOW"];
const PAGE = 25;

// Incident Center (phase brief FEATURE 1). Backend-filtered + paginated —
// no client-side fake filtering. Every row links to the full incident view.
export default function IncidentsPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [q, setQ] = useState("");
  const [activeOnly, setActiveOnly] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const params = { limit: PAGE, offset };
      if (status) params.status = status;
      if (priority) params.priority = priority;
      if (q.trim()) params.q = q.trim();
      if (activeOnly) params.active_only = true;
      setData(await listIncidents(params));
    } catch {
      setError(true);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [offset, status, priority, q, activeOnly]);

  useEffect(() => {
    load();
  }, [load]);

  // reset to first page when a filter changes
  useEffect(() => {
    setOffset(0);
  }, [status, priority, activeOnly]);

  const items = data?.items || [];
  const total = data?.total || 0;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <ClipboardList size={16} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>Incident Center</span>
        <span style={{ color: C.muted, fontSize: 12 }}>· {total} matching</span>
        <button onClick={load} style={iconBtn} title="Refresh">
          <RefreshCw size={12} />
        </button>
      </div>
      <div style={{ color: C.muted, fontSize: 11, marginBottom: 12 }}>
        Alerts promoted into tracked, assignable units of work. Open an incident from an alert on the
        Alerts screen.
      </div>

      {error && <ErrorBanner message="Could not load incidents from the backend." onRetry={load} />}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12, alignItems: "center" }}>
        <Select label="Status" value={status} onChange={setStatus} options={STATUSES} />
        <Select label="Priority" value={priority} onChange={setPriority} options={PRIORITIES} />
        <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: C.muted }}>
          <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} />
          Active only
        </label>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load()}
          placeholder="Search title / INC-number…"
          style={{ ...inputStyle, flex: "1 1 220px" }}
        />
      </div>

      <div style={panel}>
        {loading ? (
          <div style={{ padding: 14 }}>
            <SkeletonRows rows={6} height={44} />
          </div>
        ) : items.length === 0 ? (
          <EmptyState icon={ClipboardList} title="No incidents" hint="Promote an alert to create the first incident." />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ color: C.muted, textAlign: "left", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.6 }}>
                  <Th>Incident</Th>
                  <Th>Severity</Th>
                  <Th>Vehicle</Th>
                  <Th>Camera / location</Th>
                  <Th>Assigned</Th>
                  <Th>Status</Th>
                  <Th>Updated</Th>
                </tr>
              </thead>
              <tbody>
                {items.map((i) => (
                  <tr
                    key={i.id}
                    onClick={() => navigate(`/incidents/${i.id}`)}
                    style={{ borderTop: `1px solid ${C.border}`, cursor: "pointer" }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = C.panel)}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                  >
                    <Td>
                      <div style={{ fontFamily: "monospace", color: C.accent }}>{i.incident_number}</div>
                      <div style={{ color: C.text, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {i.title}
                      </div>
                    </Td>
                    <Td><SeverityBadge s={String(i.priority_level).toLowerCase()} /></Td>
                    <Td style={{ fontFamily: "monospace", color: C.amber }}>{i.plate_number_normalized || "—"}</Td>
                    <Td style={{ color: C.muted }}>
                      {i.camera_code || "—"}
                      {i.location_desc ? <div style={{ fontSize: 10 }}>{i.location_desc}</div> : null}
                    </Td>
                    <Td style={{ color: i.assigned_to_username ? C.text : C.dim }}>
                      {i.assigned_to_username || "Unassigned"}
                    </Td>
                    <Td><StatusBadge status={i.status} kind="incident" /></Td>
                    <Td style={{ color: C.muted }} title={fmtDateTime(i.updated_at)}>{fmtRelative(i.updated_at)}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Pager offset={offset} total={total} onPage={setOffset} loading={loading} />
    </div>
  );
}

function Select({ label, value, onChange, options }) {
  return (
    <label style={{ fontSize: 11, color: C.muted, display: "flex", alignItems: "center", gap: 5 }}>
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} style={inputStyle}>
        {options.map((o) => (
          <option key={o} value={o}>{o || "All"}</option>
        ))}
      </select>
    </label>
  );
}

export function Pager({ offset, total, onPage, loading, page = PAGE }) {
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + page, total);
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10, fontSize: 11, color: C.muted }}>
      <span>{from}–{to} of {total}</span>
      <span style={{ display: "flex", gap: 6 }}>
        <button disabled={loading || offset === 0} onClick={() => onPage(Math.max(0, offset - page))} style={pageBtn}>Prev</button>
        <button disabled={loading || to >= total} onClick={() => onPage(offset + page)} style={pageBtn}>Next</button>
      </span>
    </div>
  );
}

const Th = ({ children }) => <th style={{ padding: "10px 12px" }}>{children}</th>;
const Td = ({ children, style }) => <td style={{ padding: "10px 12px", verticalAlign: "top", ...style }}>{children}</td>;

const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" };
const inputStyle = {
  background: C.panel, border: `1px solid ${C.border}`, color: C.text,
  borderRadius: 4, padding: "5px 8px", fontSize: 11,
};
const iconBtn = { ...inputStyle, cursor: "pointer", display: "inline-flex", alignItems: "center" };
const pageBtn = { ...inputStyle, cursor: "pointer" };
