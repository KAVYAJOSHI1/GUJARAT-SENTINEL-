import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Clock,
  Crosshair,
  FileStack,
  Paperclip,
  Sparkles,
  StickyNote,
  Trash2,
  UserPlus,
} from "lucide-react";
import { C } from "../theme.js";
import { canManageOps } from "../services/api.js";
import { useMediaTicket } from "../services/mediaTicket.js";
import { useToast } from "../context/ToastContext.jsx";
import { fakePlate } from "../lib/evidenceFallback.js";
import EvidenceThumb from "../components/EvidenceThumb.jsx";
import {
  addIncidentNote,
  assignIncident,
  attachCaseIncident,
  attachIncidentEvidence,
  detachIncidentEvidence,
  getIncident,
  incidentTimeline,
  listAssignableUsers,
  listCases,
  setIncidentStatus,
  updateIncident,
} from "../services/opsApi.js";
import Timeline from "../components/ops/Timeline.jsx";
import AISummaryPanel from "../components/ops/AISummaryPanel.jsx";
import { aiIncidentSummary } from "../services/aiApi.js";
import SeverityBadge from "../components/SeverityBadge.jsx";
import StatusBadge from "../components/ops/StatusBadge.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import EvidenceModal from "../components/gis/EvidenceModal.jsx";
import ConfirmDialog from "../components/ui/ConfirmDialog.jsx";
import { fmtDateTime } from "../utils/datetime.js";

const STATUS_FLOW = ["NEW", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "CLOSED"];

export default function IncidentDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { push } = useToast();
  const manage = canManageOps();
  const mediaTicket = useMediaTicket(); // "" until a real credential exists -- gate evidence <img> render on it

  const [inc, setInc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [users, setUsers] = useState([]);
  const [cases, setCases] = useState([]);
  const [note, setNote] = useState("");
  const [evidenceInput, setEvidenceInput] = useState("");
  const [viewing, setViewing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      setInc(await getIncident(id));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [id]);

  const timelineLoader = useCallback((category) => incidentTimeline(id, category), [id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!manage) return;
    listAssignableUsers().then(setUsers).catch(() => {});
    listCases({ limit: 50, active_only: true }).then((d) => setCases(d.items || [])).catch(() => {});
  }, [manage]);

  const run = async (fn, okMsg) => {
    setBusy(true);
    try {
      const updated = await fn();
      if (updated && updated.id) setInc(updated);
      else await load();
      if (okMsg) push({ title: okMsg, severity: "medium" });
    } catch (e) {
      push({ title: "Action failed", msg: e?.response?.data?.error?.message || "", severity: "high" });
    } finally {
      setBusy(false);
    }
  };

  const evidence = inc?.evidence || [];
  const notes = inc?.notes || [];

  if (loading) return <div style={{ padding: 20 }}><SkeletonRows rows={6} height={40} /></div>;
  if (error || !inc)
    return (
      <div>
        <BackLink />
        <ErrorBanner message="Incident not found or backend unavailable." onRetry={load} />
      </div>
    );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <BackLink />

      <div style={panel}>
        <div style={{ padding: "14px 16px", borderBottom: `1px solid ${C.border}` }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontFamily: "monospace", color: C.accent, fontWeight: 700 }}>{inc.incident_number}</span>
            <SeverityBadge s={String(inc.priority_level).toLowerCase()} />
            <StatusBadge status={inc.status} kind="incident" />
            <span style={{ color: C.muted, fontSize: 11 }}>{inc.category}</span>
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, marginTop: 6 }}>{inc.title}</div>
          {inc.description && <div style={{ color: C.muted, fontSize: 12, marginTop: 4 }}>{inc.description}</div>}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 0 }}>
          <Field label="Vehicle">
            {inc.plate_number_normalized ? (
              <Link to={`/workspace?plate=${encodeURIComponent(inc.plate_number_normalized)}`}
                    style={{ color: C.amber, fontFamily: "monospace", textDecoration: "none" }}>
                {inc.plate_number_normalized}
              </Link>
            ) : "—"}
          </Field>
          <Field label="Camera">
            {inc.camera_id
              ? <Link to={`/investigation?cam=${encodeURIComponent(inc.camera_id)}`} style={{ color: C.accent, textDecoration: "none" }}>
                  {inc.camera_code || inc.camera_id}
                </Link>
              : "—"}
          </Field>
          <Field label="Location">{inc.location_desc || "—"}</Field>
          <Field label="Source alert">{inc.alert_id ? <span style={{ fontFamily: "monospace", fontSize: 10 }}>{inc.alert_id.slice(0, 8)}…</span> : "manual"}</Field>
          <Field label="Created by">{inc.created_by_username || "—"} · {fmtDateTime(inc.created_at)}</Field>
          <Field label="Acknowledged">{inc.acknowledged_by_username ? `${inc.acknowledged_by_username} · ${fmtDateTime(inc.acknowledged_at)}` : "—"}</Field>
          <Field label="Resolved">{inc.resolved_by_username ? `${inc.resolved_by_username} · ${fmtDateTime(inc.resolved_at)}` : "—"}</Field>
          <Field label="Cases">{inc.case_numbers?.length ? inc.case_numbers.join(", ") : "—"}</Field>
        </div>

        {/* Quick actions */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", padding: "12px 16px", borderTop: `1px solid ${C.border}` }}>
          {inc.plate_number_normalized && (
            <button style={actBtn(C.accent)}
                    onClick={() => navigate(`/workspace?plate=${encodeURIComponent(inc.plate_number_normalized)}`)}>
              <Crosshair size={12} /> Investigate vehicle
            </button>
          )}
          {manage && (
            <>
              <label style={{ ...actBtn(C.border), color: C.muted }}>
                Status:&nbsp;
                <select
                  value={inc.status}
                  disabled={busy}
                  onChange={(e) => run(() => setIncidentStatus(inc.id, e.target.value), `Status → ${e.target.value}`)}
                  style={bareSelect}
                >
                  {STATUS_FLOW.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label style={{ ...actBtn(C.border), color: C.muted }}>
                <UserPlus size={12} />&nbsp;
                <select
                  value={inc.assigned_to_user_id || ""}
                  disabled={busy}
                  onChange={(e) => run(() => assignIncident(inc.id, e.target.value || null), "Assignment updated")}
                  style={bareSelect}
                >
                  <option value="">Unassigned</option>
                  {users.map((u) => <option key={u.id} value={u.id}>{u.username} ({u.role})</option>)}
                </select>
              </label>
              <label style={{ ...actBtn(C.border), color: C.muted }}>
                Priority:&nbsp;
                <select
                  value={inc.priority_level}
                  disabled={busy}
                  onChange={(e) => run(() => updateIncident(inc.id, { priority_level: e.target.value }), "Priority updated")}
                  style={bareSelect}
                >
                  {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </label>
              {cases.length > 0 && (
                <label style={{ ...actBtn(C.border), color: C.muted }}>
                  <FileStack size={12} />&nbsp;
                  <select
                    value=""
                    disabled={busy}
                    onChange={(e) => e.target.value && run(() => attachCaseIncident(e.target.value, inc.id), "Attached to case")}
                    style={bareSelect}
                  >
                    <option value="">Attach to case…</option>
                    {cases.map((c) => <option key={c.id} value={c.id}>{c.case_number} — {c.title}</option>)}
                  </select>
                </label>
              )}
            </>
          )}
        </div>
      </div>

      {/* Evidence */}
      <div style={panel}>
        <SectionHead icon={Paperclip} title={`Evidence (${evidence.length})`} />
        <div style={{ padding: 12, display: "flex", flexWrap: "wrap", gap: 10 }}>
          {evidence.length === 0 && <span style={{ color: C.dim, fontSize: 12 }}>No evidence attached.</span>}
          {evidence.map((e) => (
            <div key={e.id} style={{ width: 150, background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6, overflow: "hidden" }}>
              <div style={{ height: 90, background: "#000", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <EvidenceThumb eventId={e.vehicle_event_id} hasSnapshot={e.has_snapshot} mediaTicket={mediaTicket}
                  style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              </div>
              <div style={{ padding: "6px 8px", fontSize: 10, color: C.muted }}>
                <div style={{ fontFamily: "monospace", color: C.amber }}>{e.plate_number || fakePlate(e.vehicle_event_id || e.id)}</div>
                <div>{e.camera_code || "—"} · {fmtDateTime(e.event_timestamp)}</div>
                {e.note && <div style={{ color: C.text }}>{e.note}</div>}
                <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                  <button style={linkBtn} onClick={() => setViewing(e)}>View</button>
                  {manage && (
                    <button style={{ ...linkBtn, color: C.red }}
                            onClick={() => setConfirming({
                              message: "Detach this evidence?",
                              onConfirm: () => { setConfirming(null); run(() => detachIncidentEvidence(inc.id, e.id), "Evidence detached"); },
                            })}>
                      <Trash2 size={10} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
        {manage && (
          <div style={{ display: "flex", gap: 8, padding: "0 12px 12px", flexWrap: "wrap" }}>
            <input
              value={evidenceInput}
              onChange={(e) => setEvidenceInput(e.target.value)}
              placeholder="vehicle_event id to attach"
              style={{ ...inputStyle, flex: "1 1 240px" }}
            />
            <button
              style={actBtn(C.accent)}
              disabled={busy || !evidenceInput.trim()}
              onClick={() => run(() => attachIncidentEvidence(inc.id, evidenceInput.trim()).then(() => setEvidenceInput("")), "Evidence attached")}
            >
              Attach
            </button>
            <span style={{ color: C.dim, fontSize: 10, alignSelf: "center" }}>
              Tip: copy an event id from the vehicle trace timeline.
            </span>
          </div>
        )}
      </div>

      {/* AI Summary */}
      <div style={panel}>
        <SectionHead icon={Sparkles} title="AI Summary" />
        <AISummaryPanel loader={() => aiIncidentSummary(inc.id)} />
      </div>

      {/* Timeline */}
      <div style={panel}>
        <SectionHead icon={Clock} title="Timeline" />
        <div style={{ padding: 12 }}>
          <Timeline loader={timelineLoader} refreshKey={inc.updated_at} />
        </div>
      </div>

      {/* Notes */}
      <div style={panel}>
        <SectionHead icon={StickyNote} title={`Officer remarks (${notes.length})`} />
        <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
          {notes.length === 0 && <span style={{ color: C.dim, fontSize: 12 }}>No remarks yet.</span>}
          {notes.map((n) => (
            <div key={n.id} style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6, padding: "8px 10px" }}>
              <div style={{ fontSize: 10, color: C.muted, marginBottom: 3 }}>
                {n.author_username || "unknown"} · {fmtDateTime(n.created_at)}
              </div>
              <div style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{n.body}</div>
            </div>
          ))}
          {manage && (
            <div style={{ display: "flex", gap: 8 }}>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Add an officer remark…"
                rows={2}
                style={{ ...inputStyle, flex: 1, resize: "vertical" }}
              />
              <button
                style={actBtn(C.accent)}
                disabled={busy || !note.trim()}
                onClick={() => run(() => addIncidentNote(inc.id, note.trim()).then(() => setNote("")), "Remark added")}
              >
                Add
              </button>
            </div>
          )}
        </div>
      </div>

      <EvidenceModal
        sighting={viewing ? {
          eventId: viewing.vehicle_event_id,
          cameraId: viewing.camera_code || viewing.camera_id,
          cameraName: viewing.camera_name || viewing.camera_code,
          timestamp: viewing.event_timestamp,
          snapshotUrl: null, plateCropUrl: null, ocrConfidence: NaN, vehicleType: null,
        } : null}
        plate={viewing?.plate_number || ""}
        onClose={() => setViewing(null)}
      />

      <ConfirmDialog
        open={!!confirming}
        title="Confirm detach"
        message={confirming?.message}
        confirmLabel="Detach"
        onConfirm={confirming?.onConfirm}
        onCancel={() => setConfirming(null)}
      />
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/incidents" style={{ display: "inline-flex", alignItems: "center", gap: 5, color: C.muted, fontSize: 12, textDecoration: "none" }}>
      <ArrowLeft size={13} /> Incident Center
    </Link>
  );
}

const Field = ({ label, children }) => (
  <div style={{ padding: "10px 16px", borderTop: `1px solid ${C.border}`, borderRight: `1px solid ${C.border}` }}>
    <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.6, color: C.dim, marginBottom: 3 }}>{label}</div>
    <div style={{ fontSize: 12, color: C.text }}>{children}</div>
  </div>
);

const SectionHead = ({ icon: Icon, title }) => (
  <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, fontWeight: 600, fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
    <Icon size={13} color={C.accent} /> {title}
  </div>
);

const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" };
const inputStyle = { background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "6px 8px", fontSize: 12 };
const bareSelect = { background: "transparent", border: "none", color: C.text, fontSize: 11, cursor: "pointer" };
const linkBtn = { background: "transparent", border: "none", color: C.accent, fontSize: 10, cursor: "pointer", padding: 0, display: "inline-flex", alignItems: "center", gap: 3 };
const actBtn = (color) => ({
  display: "inline-flex", alignItems: "center", gap: 5, background: "transparent",
  border: `1px solid ${color}`, color: color === C.border ? C.text : color,
  borderRadius: 4, padding: "5px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer",
});
