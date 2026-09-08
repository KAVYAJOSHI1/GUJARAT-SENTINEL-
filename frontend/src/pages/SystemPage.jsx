import { useCallback, useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Bell, BellRing, CheckCheck, ServerCog } from "lucide-react";
import { C } from "../theme.js";
import SystemHealthPanel from "../components/observability/SystemHealthPanel.jsx";
import AiPipelinePanel from "../components/observability/AiPipelinePanel.jsx";
import MetricsSummaryPanel from "../components/observability/MetricsSummaryPanel.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import { listNotifications, markAllNotificationsRead, markNotificationRead } from "../services/opsApi.js";
import { fmtDateTime, fmtRelative } from "../utils/datetime.js";

const SEV_COLOR = { CRITICAL: C.red, WARNING: C.amber, INFO: C.accent };
const PAGE = 40;

// System screen (phase brief FEATURE 12 + system health). The notification
// center shows only real backend events — nothing synthesised.
export default function SystemPage() {
  const ctx = useOutletContext() || {};
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const params = { limit: PAGE, offset };
      if (unreadOnly) params.unread_only = true;
      setData(await listNotifications(params));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [offset, unreadOnly]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setOffset(0); }, [unreadOnly]);

  const items = data?.items || [];

  const markOne = async (id) => {
    try {
      await markNotificationRead(id);
      ctx.refreshNotifications?.();
      load();
    } catch { /* ignore */ }
  };
  const markAll = async () => {
    setBusy(true);
    try {
      await markAllNotificationsRead();
      ctx.refreshNotifications?.();
      load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <ServerCog size={16} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>System</span>
      </div>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <SystemHealthPanel health={ctx.health} healthLive={ctx.healthLive} cameras={ctx.cameras || []} lastRefresh={ctx.lastRefresh} />
        <AiPipelinePanel health={ctx.health} />
        <MetricsSummaryPanel />
      </div>

      <div style={panel}>
        <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 10 }}>
          <Bell size={13} color={C.accent} />
          <span style={{ fontWeight: 600, fontSize: 12 }}>Notification Center</span>
          <span style={{ color: C.muted, fontSize: 11 }}>{data?.unread ?? 0} unread · {data?.total ?? 0} total</span>
          <label style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: C.muted }}>
            <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} /> Unread only
          </label>
          <button onClick={markAll} disabled={busy || !(data?.unread)} style={smallBtn}>
            <CheckCheck size={12} /> Mark all read
          </button>
        </div>

        {error && <div style={{ padding: 12 }}><ErrorBanner message="Could not load notifications." onRetry={load} /></div>}

        {loading ? (
          <div style={{ padding: 14 }}><SkeletonRows rows={6} height={40} /></div>
        ) : items.length === 0 ? (
          <EmptyState icon={BellRing} title="No notifications" hint="Operational events (watchlist matches, assignments, incidents) will appear here." />
        ) : (
          <div>
            {items.map((n) => (
              <div key={n.id} style={{
                display: "flex", gap: 10, alignItems: "flex-start", padding: "10px 14px",
                borderTop: `1px solid ${C.border}`, background: n.read ? "transparent" : `${SEV_COLOR[n.severity] || C.accent}0f`,
              }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", marginTop: 5, background: SEV_COLOR[n.severity] || C.accent, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ fontSize: 12, color: C.text, fontWeight: 600 }}>{n.title}</span>
                    <span style={{ fontSize: 9, color: C.muted, fontFamily: "monospace" }}>{n.type}</span>
                  </div>
                  {n.body && <div style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>{n.body}</div>}
                  <div style={{ fontSize: 10, color: C.dim, marginTop: 2 }} title={fmtDateTime(n.created_at)}>{fmtRelative(n.created_at)}</div>
                </div>
                {!n.read && (
                  <button style={{ ...smallBtn, borderColor: C.dim, color: C.muted }} onClick={() => markOne(n.id)}>Mark read</button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" };
const smallBtn = {
  display: "inline-flex", alignItems: "center", gap: 4, background: "transparent",
  border: `1px solid ${C.border}`, color: C.muted, borderRadius: 4, padding: "3px 8px",
  fontSize: 10, cursor: "pointer",
};
