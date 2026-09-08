import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Briefcase, RefreshCw, ArrowUpCircle, Clock, UserCheck, Zap, CheckCircle2 } from "lucide-react";
import { C } from "../theme.js";
import { fetchWorkQueue, assignAlert, assignIncident, assignCase } from "../services/opsApi.js";
import { acknowledgeAlert, canManageOps, currentSession, currentUsername } from "../services/api.js";
import SeverityBadge from "../components/SeverityBadge.jsx";
import StatusBadge from "../components/ops/StatusBadge.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import { useToast } from "../context/ToastContext.jsx";
import { fmtRelative, fmtDateTime } from "../utils/datetime.js";

// Age thresholds after which an OPEN item is "overdue" and needs attention.
const OVERDUE_MS = { ALERT: 4 * 3600e3, INCIDENT: 24 * 3600e3, CASE: 72 * 3600e3 };
const RECENT_MS = 24 * 3600e3;

// Officer Work Queue — "My Work" (Phase 11 FEATURE 12, Phase 16G).
// Role-aware: the backend returns assigned work for OFFICER/OPERATOR, all
// open work for ADMIN. This view slices it into the sections an operator
// actually triages by: URGENT · ESCALATED · ASSIGNED TO ME · OVERDUE · RECENT.
export default function MyWorkPage() {
  const nav = useNavigate();
  const { push } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [busyId, setBusyId] = useState("");

  const me = currentUsername();
  const myId = currentSession()?.userId || null;
  const canManage = canManageOps();

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      setData(await fetchWorkQueue("priority"));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const all = useMemo(
    () => (data ? [...(data.incidents || []), ...(data.cases || []), ...(data.alerts || [])] : []),
    [data]
  );

  const age = (w) => Date.now() - new Date(w.created_at).getTime();
  const isEscalated = (w) => w.status === "ESCALATED";
  const isUrgent = (w) => w.priority === "CRITICAL" || isEscalated(w);
  const isMine = (w) => !!w.assigned_to_username && (w.assigned_to_username === me || data?.scope === "assigned");
  const isOverdue = (w) =>
    !["RESOLVED", "CLOSED"].includes(w.status) && age(w) > (OVERDUE_MS[w.kind] || 24 * 3600e3);
  const isRecent = (w) => age(w) <= RECENT_MS;

  // each item lands in exactly ONE section (first match wins) so the queue
  // has no duplicates and the counts add up.
  const sections = useMemo(() => {
    const buckets = { URGENT: [], ESCALATED: [], "ASSIGNED TO ME": [], OVERDUE: [], RECENT: [], OTHER: [] };
    for (const w of all) {
      if (isEscalated(w)) buckets.ESCALATED.push(w);
      else if (isUrgent(w)) buckets.URGENT.push(w);
      else if (isMine(w)) buckets["ASSIGNED TO ME"].push(w);
      else if (isOverdue(w)) buckets.OVERDUE.push(w);
      else if (isRecent(w)) buckets.RECENT.push(w);
      else buckets.OTHER.push(w);
    }
    return buckets;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all, me, data?.scope]);

  const act = async (label, fn, id) => {
    setBusyId(id);
    try {
      await fn();
      push({ title: label, severity: "medium" });
      await load();
    } catch (e) {
      push({ title: `${label} failed`, msg: e?.response?.data?.error?.message || "", severity: "high" });
    } finally {
      setBusyId("");
    }
  };

  const assignToMe = (w) => {
    if (!myId) return;
    const fn = w.kind === "INCIDENT" ? () => assignIncident(w.id, myId)
      : w.kind === "CASE" ? () => assignCase(w.id, myId)
      : () => assignAlert(w.id, myId);
    act("Assigned to you", fn, w.id);
  };

  const SECTION_META = {
    URGENT: { icon: Zap, color: C.red },
    ESCALATED: { icon: ArrowUpCircle, color: C.red },
    "ASSIGNED TO ME": { icon: UserCheck, color: C.accent },
    OVERDUE: { icon: Clock, color: C.amber },
    RECENT: { icon: Briefcase, color: C.muted },
    OTHER: { icon: Briefcase, color: C.dim },
  };
  const ORDER = ["URGENT", "ESCALATED", "ASSIGNED TO ME", "OVERDUE", "RECENT", "OTHER"];

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <Briefcase size={16} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>My Work</span>
        {data && (
          <span style={{ color: C.muted, fontSize: 12 }}>
            · {data.scope === "all" ? "all open work" : `assigned to ${me || "you"}`}
          </span>
        )}
        <button onClick={load} style={iconBtn} title="Refresh"><RefreshCw size={12} /></button>
      </div>

      {error && <ErrorBanner message="Could not load your work queue." onRetry={load} />}

      {data && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
          <Kpi label="Urgent" v={sections.URGENT.length + sections.ESCALATED.length} color={C.red} />
          <Kpi label="Assigned to me" v={sections["ASSIGNED TO ME"].length} />
          <Kpi label="Overdue" v={sections.OVERDUE.length} color={C.amber} />
          <Kpi label="Incidents" v={data.counts.incidents} />
          <Kpi label="Cases" v={data.counts.cases} />
          <Kpi label="Open alerts" v={data.counts.alerts} />
        </div>
      )}

      {loading ? (
        <div style={{ ...panel, padding: 14 }}><SkeletonRows rows={6} height={44} /></div>
      ) : all.length === 0 ? (
        <EmptyState icon={Briefcase} title="Nothing pending" hint="Work assigned to you will appear here." />
      ) : (
        <div style={{ display: "grid", gap: 14 }}>
          {ORDER.filter((k) => sections[k].length).map((k) => {
            const M = SECTION_META[k];
            return (
              <div key={k} style={panel}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 14px", borderBottom: `1px solid ${C.border}` }}>
                  <M.icon size={13} color={M.color} />
                  <span style={{ fontWeight: 700, fontSize: 12, color: M.color, letterSpacing: 0.5 }}>{k}</span>
                  <span style={{ color: C.muted, fontSize: 11 }}>{sections[k].length}</span>
                </div>
                {sections[k].map((w) => (
                  <WorkRow key={`${w.kind}-${w.id}`} w={w} nav={nav} age={age(w)}
                    canManage={canManage} busy={busyId === w.id}
                    onOpen={() => nav(w.href)}
                    onAck={w.kind === "ALERT" && w.status === "NEW" ? () => act("Alert acknowledged", () => acknowledgeAlert(w.id), w.id) : null}
                    onAssignMe={myId && !w.assigned_to_username ? () => assignToMe(w) : null} />
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function WorkRow({ w, nav, age, canManage, busy, onOpen, onAck, onAssignMe }) {
  const overdueHrs = Math.floor(age / 3600e3);
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", padding: "10px 14px", borderTop: `1px solid ${C.border}` }}>
      <span style={{ fontSize: 9, fontWeight: 700, color: C.muted, minWidth: 54 }}>{w.kind}</span>
      <button onClick={onOpen} style={{ background: "none", border: "none", cursor: "pointer", fontFamily: "monospace", color: C.accent, fontSize: 11, padding: 0 }}>
        {w.ref}
      </button>
      <span style={{ color: C.text, fontSize: 12, flex: 1, minWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {w.title}
      </span>
      {w.plate && (
        <button onClick={() => nav(`/workspace?plate=${encodeURIComponent(w.plate)}`)}
          style={{ background: "none", border: `1px solid ${C.border}`, borderRadius: 3, cursor: "pointer", fontFamily: "monospace", color: C.amber, fontSize: 10, padding: "1px 6px" }}>
          {w.plate}
        </button>
      )}
      <SeverityBadge s={String(w.priority).toLowerCase()} />
      <StatusBadge status={w.status} kind={w.kind === "CASE" ? "case" : "incident"} />
      <span style={{ color: C.dim, fontSize: 10 }} title={fmtDateTime(w.created_at)}>
        {overdueHrs >= 1 ? `${overdueHrs}h old` : fmtRelative(w.created_at)}
      </span>
      {w.assigned_to_username && (
        <span style={{ color: C.muted, fontSize: 10 }}>→ {w.assigned_to_username}</span>
      )}
      <div style={{ display: "flex", gap: 6 }}>
        <button onClick={onOpen} style={rowBtn(C.accent)}>OPEN</button>
        {canManage && onAck && (
          <button disabled={busy} onClick={onAck} style={rowBtn(C.green)}>
            <CheckCircle2 size={10} /> ACK
          </button>
        )}
        {canManage && onAssignMe && (
          <button disabled={busy} onClick={onAssignMe} style={rowBtn(C.muted)}>ASSIGN ME</button>
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
const rowBtn = (color) => ({
  display: "inline-flex", alignItems: "center", gap: 3, background: "transparent",
  border: `1px solid ${color}`, color, borderRadius: 3, padding: "2px 7px",
  fontSize: 9, fontWeight: 700, cursor: "pointer",
});
