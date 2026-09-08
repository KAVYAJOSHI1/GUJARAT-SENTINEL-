import { useCallback, useEffect, useState } from "react";
import { ScrollText, ShieldAlert } from "lucide-react";
import { C } from "../theme.js";
import { currentRole } from "../services/api.js";
import { listAuditLogs } from "../services/opsApi.js";
import EmptyState from "../components/ui/EmptyState.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import { Pager } from "./IncidentsPage.jsx";
import { fmtDateTime } from "../utils/datetime.js";

const PAGE = 50;

// Admin — Activity / Audit center (phase brief FEATURE 11). Read-only view
// over the EXISTING audit_logs table. ADMIN only (enforced by the backend;
// this also hides the screen for other roles).
export default function AdminPage() {
  const isAdmin = currentRole() === "ADMIN";
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [offset, setOffset] = useState(0);
  const [action, setAction] = useState("");
  const [q, setQ] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const params = { limit: PAGE, offset };
      if (action) params.action = action;
      if (q.trim()) params.q = q.trim();
      setData(await listAuditLogs(params));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [offset, action, q]);

  useEffect(() => {
    if (isAdmin) load();
    else setLoading(false);
  }, [isAdmin, load]);
  useEffect(() => { setOffset(0); }, [action]);

  if (!isAdmin) {
    return (
      <div style={{ padding: 20 }}>
        <EmptyState icon={ShieldAlert} title="Administrator access required"
                    hint="The activity log is restricted to ADMIN users." />
      </div>
    );
  }

  const items = data?.items || [];
  const total = data?.total || 0;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <ScrollText size={16} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>Activity / Audit Log</span>
        <span style={{ color: C.muted, fontSize: 12 }}>· {total}</span>
      </div>
      <div style={{ color: C.muted, fontSize: 11, marginBottom: 12 }}>
        Append-only record of privileged actions — logins, searches, evidence access, watchlist / incident / case changes.
      </div>

      {error && <ErrorBanner message="Could not load the audit log." onRetry={load} />}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12, alignItems: "center" }}>
        <label style={{ fontSize: 11, color: C.muted, display: "flex", alignItems: "center", gap: 5 }}>
          Action
          <select value={action} onChange={(e) => setAction(e.target.value)} style={inputStyle}>
            <option value="">All</option>
            {(data?.actions || []).map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </label>
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()}
               placeholder="Search detail…" style={{ ...inputStyle, flex: "1 1 220px" }} />
      </div>

      <div style={panel}>
        {loading ? (
          <div style={{ padding: 14 }}><SkeletonRows rows={8} height={34} /></div>
        ) : items.length === 0 ? (
          <EmptyState icon={ScrollText} title="No activity" hint="Audited actions will appear here." />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
              <thead>
                <tr style={{ color: C.muted, textAlign: "left", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.6 }}>
                  <th style={th}>Time</th><th style={th}>User</th><th style={th}>Action</th>
                  <th style={th}>Resource</th><th style={th}>IP</th><th style={th}>Detail</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.id} style={{ borderTop: `1px solid ${C.border}` }}>
                    <td style={{ ...td, color: C.muted, whiteSpace: "nowrap" }}>{fmtDateTime(r.created_at)}</td>
                    <td style={td}>{r.username || <span style={{ color: C.dim }}>{r.user_id ? r.user_id.slice(0, 8) : "system"}</span>}</td>
                    <td style={{ ...td, fontFamily: "monospace", color: C.accent }}>{r.action}</td>
                    <td style={{ ...td, color: C.muted }}>
                      {r.resource || "—"}{r.resource_id ? <span style={{ color: C.dim }}> · {String(r.resource_id).slice(0, 8)}</span> : null}
                    </td>
                    <td style={{ ...td, color: C.dim, fontFamily: "monospace" }}>{r.ip_address || "—"}</td>
                    <td style={{ ...td, color: C.muted, maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                        title={r.detail || ""}>{r.detail || "—"}</td>
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
const th = { padding: "8px 12px" };
const td = { padding: "8px 12px", verticalAlign: "top" };
const inputStyle = { background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "5px 8px", fontSize: 11 };
