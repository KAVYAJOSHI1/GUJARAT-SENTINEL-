import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft, Camera as CameraIcon, Clock, Crosshair, FileDown,
  Link2, Paperclip, Sparkles, StickyNote, Trash2, UserPlus,
} from "lucide-react";
import AISummaryPanel from "../components/ops/AISummaryPanel.jsx";
import { aiCaseSummary } from "../services/aiApi.js";
import { C } from "../theme.js";
import { canManageOps, evidenceUrl } from "../services/api.js";
import { useMediaTicket } from "../services/mediaTicket.js";
import { useToast } from "../context/ToastContext.jsx";
import {
  addCaseNote, assignCase, attachCaseEvidence, attachCaseIncident, caseTimeline,
  detachCaseEvidence, detachCaseIncident, downloadCaseReportCSV, getCase,
  listAssignableUsers, listIncidents, updateCase,
} from "../services/opsApi.js";
import Timeline from "../components/ops/Timeline.jsx";
import SeverityBadge from "../components/SeverityBadge.jsx";
import StatusBadge from "../components/ops/StatusBadge.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import EvidenceModal from "../components/gis/EvidenceModal.jsx";
import { fmtDateTime, fmtTime } from "../utils/datetime.js";

const CASE_STATUS = ["OPEN", "INVESTIGATING", "ON_HOLD", "RESOLVED", "CLOSED"];
const TIMELINE_COLOR = { CASE_CREATED: C.accent, INCIDENT: C.amber, EVIDENCE: C.violet, SIGHTING: C.violet, NOTE: C.muted };

export default function CaseDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { push } = useToast();
  const manage = canManageOps();
  const mediaTicket = useMediaTicket(); // "" until a real credential exists -- gate evidence <img> render on it

  const [c, setC] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [users, setUsers] = useState([]);
  const [openIncidents, setOpenIncidents] = useState([]);
  const [note, setNote] = useState("");
  const [evInput, setEvInput] = useState("");
  const [viewing, setViewing] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      setC(await getCase(id));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [id]);

  const timelineLoader = useCallback((category) => caseTimeline(id, category), [id]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!manage) return;
    listAssignableUsers().then(setUsers).catch(() => {});
    listIncidents({ limit: 50, active_only: true }).then((d) => setOpenIncidents(d.items || [])).catch(() => {});
  }, [manage]);

  const run = async (fn, okMsg) => {
    setBusy(true);
    try {
      const updated = await fn();
      if (updated && updated.id) setC(updated);
      else await load();
      if (okMsg) push({ title: okMsg, severity: "medium" });
    } catch (e) {
      push({ title: "Action failed", msg: e?.response?.data?.error?.message || "", severity: "high" });
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div style={{ padding: 20 }}><SkeletonRows rows={6} height={40} /></div>;
  if (error || !c)
    return <div><Back /><ErrorBanner message="Case not found or backend unavailable." onRetry={load} /></div>;

  const incidents = c.incidents || [];
  const evidence = c.evidence || [];
  const notes = c.notes || [];
  const timeline = c.timeline || [];
  const linkedIncidentIds = new Set(incidents.map((i) => i.id));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <Back />

      <div style={panel}>
        <div style={{ padding: "14px 16px", borderBottom: `1px solid ${C.border}` }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <span style={{ fontFamily: "monospace", color: C.accent, fontWeight: 700 }}>{c.case_number}</span>
            <SeverityBadge s={String(c.priority_level).toLowerCase()} />
            <StatusBadge status={c.status} kind="case" />
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, marginTop: 6 }}>{c.title}</div>
          {c.description && <div style={{ color: C.muted, fontSize: 12, marginTop: 4 }}>{c.description}</div>}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))" }}>
          <Field label="Primary vehicle">
            {c.primary_plate_normalized
              ? <Link to={`/workspace?plate=${encodeURIComponent(c.primary_plate_normalized)}`} style={{ color: C.amber, fontFamily: "monospace", textDecoration: "none" }}>{c.primary_plate_normalized}</Link>
              : "—"}
          </Field>
          <Field label="Incidents">{c.incident_count}</Field>
          <Field label="Camera sightings">{c.sighting_count}</Field>
          <Field label="Evidence">{c.evidence_count}</Field>
          <Field label="Created by">{c.created_by_username || "—"} · {fmtDateTime(c.created_at)}</Field>
          <Field label="Assigned">{c.assigned_to_username || "Unassigned"}</Field>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", padding: "12px 16px", borderTop: `1px solid ${C.border}` }}>
          {c.primary_plate_normalized && (
            <button style={actBtn(C.accent)} onClick={() => navigate(`/workspace?plate=${encodeURIComponent(c.primary_plate_normalized)}`)}>
              <Crosshair size={12} /> Investigate vehicle
            </button>
          )}
          <button style={actBtn(C.border)} onClick={() => downloadCaseReportCSV(c.id, c.case_number)}>
            <FileDown size={12} /> Export Case Report (CSV)
          </button>
          {manage && (
            <>
              <label style={{ ...actBtn(C.border) }}>
                Status:&nbsp;
                <select value={c.status} disabled={busy} style={bareSelect}
                        onChange={(e) => run(() => updateCase(c.id, { status: e.target.value }), `Status → ${e.target.value}`)}>
                  {CASE_STATUS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label style={{ ...actBtn(C.border) }}>
                <UserPlus size={12} />&nbsp;
                <select value={c.assigned_to_user_id || ""} disabled={busy} style={bareSelect}
                        onChange={(e) => run(() => assignCase(c.id, e.target.value || null), "Assignment updated")}>
                  <option value="">Unassigned</option>
                  {users.map((u) => <option key={u.id} value={u.id}>{u.username} ({u.role})</option>)}
                </select>
              </label>
            </>
          )}
        </div>
      </div>

      {/* Incidents */}
      <div style={panel}>
        <SectionHead icon={Link2} title={`Incidents (${incidents.length})`} />
        <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
          {incidents.length === 0 && <span style={{ color: C.dim, fontSize: 12 }}>No incidents linked.</span>}
          {incidents.map((i) => (
            <div key={i.id} style={{ display: "flex", alignItems: "center", gap: 10, background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6, padding: "8px 10px" }}>
              <Link to={`/incidents/${i.id}`} style={{ fontFamily: "monospace", color: C.accent, textDecoration: "none" }}>{i.incident_number}</Link>
              <span style={{ flex: 1, fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{i.title}</span>
              <SeverityBadge s={String(i.priority_level).toLowerCase()} />
              <StatusBadge status={i.status} kind="incident" />
              {manage && (
                <button style={{ ...linkBtn, color: C.red }}
                        onClick={() => window.confirm("Detach incident from case?") && run(() => detachCaseIncident(c.id, i.id), "Incident detached")}>
                  <Trash2 size={11} />
                </button>
              )}
            </div>
          ))}
          {manage && openIncidents.filter((i) => !linkedIncidentIds.has(i.id)).length > 0 && (
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: C.muted, marginTop: 4 }}>
              Attach incident:
              <select value="" disabled={busy} style={inputStyle}
                      onChange={(e) => e.target.value && run(() => attachCaseIncident(c.id, e.target.value), "Incident attached")}>
                <option value="">select…</option>
                {openIncidents.filter((i) => !linkedIncidentIds.has(i.id)).map((i) => (
                  <option key={i.id} value={i.id}>{i.incident_number} — {i.title}</option>
                ))}
              </select>
            </label>
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
                {e.has_snapshot && mediaTicket
                  ? <img src={evidenceUrl(e.vehicle_event_id)} alt="evidence" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                  : <CameraIcon size={16} color={C.dim} />}
              </div>
              <div style={{ padding: "6px 8px", fontSize: 10, color: C.muted }}>
                <div style={{ fontFamily: "monospace", color: C.amber }}>{e.plate_number || "—"}</div>
                <div>{e.camera_code || "—"} · {fmtDateTime(e.event_timestamp)}</div>
                <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                  <button style={linkBtn} onClick={() => setViewing(e)}>View</button>
                  {manage && (
                    <button style={{ ...linkBtn, color: C.red }}
                            onClick={() => window.confirm("Detach evidence?") && run(() => detachCaseEvidence(c.id, e.id), "Evidence detached")}>
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
            <input value={evInput} onChange={(e) => setEvInput(e.target.value)} placeholder="vehicle_event id to attach"
                   style={{ ...inputStyle, flex: "1 1 240px" }} />
            <button style={actBtn(C.accent)} disabled={busy || !evInput.trim()}
                    onClick={() => run(() => attachCaseEvidence(c.id, evInput.trim()).then(() => setEvInput("")), "Evidence attached")}>
              Attach
            </button>
          </div>
        )}
      </div>

      {/* AI Summary */}
      <div style={panel}>
        <SectionHead icon={Sparkles} title="AI Summary" />
        <AISummaryPanel loader={() => aiCaseSummary(c.id)} />
      </div>

      {/* Timeline (Phase 11 — filterable, derived from audit + linked rows) */}
      <div style={panel}>
        <SectionHead icon={Clock} title="Case Timeline & Activity" />
        <div style={{ padding: 12 }}>
          <Timeline loader={timelineLoader} refreshKey={c.updated_at} />
        </div>
      </div>

      {/* Notes */}
      <div style={panel}>
        <SectionHead icon={StickyNote} title={`Officer notes (${notes.length})`} />
        <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
          {notes.length === 0 && <span style={{ color: C.dim, fontSize: 12 }}>No notes yet.</span>}
          {notes.map((n) => (
            <div key={n.id} style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6, padding: "8px 10px" }}>
              <div style={{ fontSize: 10, color: C.muted, marginBottom: 3 }}>{n.author_username || "unknown"} · {fmtDateTime(n.created_at)}</div>
              <div style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{n.body}</div>
            </div>
          ))}
          {manage && (
            <div style={{ display: "flex", gap: 8 }}>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="Add an officer note…"
                        style={{ ...inputStyle, flex: 1, resize: "vertical" }} />
              <button style={actBtn(C.accent)} disabled={busy || !note.trim()}
                      onClick={() => run(() => addCaseNote(c.id, note.trim()).then(() => setNote("")), "Note added")}>
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
    </div>
  );
}

const Back = () => (
  <Link to="/cases" style={{ display: "inline-flex", alignItems: "center", gap: 5, color: C.muted, fontSize: 12, textDecoration: "none" }}>
    <ArrowLeft size={13} /> Investigation Cases
  </Link>
);
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
