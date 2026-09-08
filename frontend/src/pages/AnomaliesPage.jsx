import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, RefreshCw, ScanSearch } from "lucide-react";
import { C } from "../theme.js";
import { canManageOps } from "../services/api.js";
import { useToast } from "../context/ToastContext.jsx";
import { listAnomalies, reviewAnomaly, scanAnomalies } from "../services/aiApi.js";
import ConfidenceBadge from "../components/ops/ConfidenceBadge.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import { Pager } from "./IncidentsPage.jsx";
import { fmtDateTime } from "../utils/datetime.js";

const PAGE = 25;
const STATUSES = ["", "NEW", "REVIEWED", "DISMISSED"];
const KIND_LABEL = {
  STOPPED_VEHICLE: "STOPPED VEHICLE",
  WRONG_WAY: "WRONG-WAY MOVEMENT",
  RESTRICTED_ZONE: "RESTRICTED-ZONE ENTRY",
};
const KIND_COLOR = { STOPPED_VEHICLE: "#D9A441", WRONG_WAY: "#E0574C", RESTRICTED_ZONE: "#9B8CEE" };

function anomalyDetail(a) {
  if (a.kind === "WRONG_WAY") {
    return `Heading ${Math.round(a.direction_deg)}° vs permitted ${Math.round(a.expected_direction_deg)}° `
      + `over ${a.displacement_meters ?? "?"} m (${a.detection_count} detections)`;
  }
  if (a.kind === "RESTRICTED_ZONE") {
    return `Entered "${a.zone_name || "restricted zone"}" — ${a.detection_count} sighting(s) inside`
      + (a.duration_seconds ? `, ~${Math.round(a.duration_seconds)}s dwell` : "");
  }
  return `Held ${Math.round(a.duration_seconds / 60)} min (${a.detection_count} detections`
    + `${a.displacement_meters != null ? `, ≤ ${a.displacement_meters} m movement` : ""})`;
}

// AI-assisted anomaly detection — stopped / loitering vehicles (Phase 12
// §4). Every figure is derived from stored ByteTrack events; each anomaly
// flows through the existing alert workflow.
export default function AnomaliesPage() {
  const { push } = useToast();
  const manage = canManageOps();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const params = { limit: PAGE, offset };
      if (status) params.status = status;
      setData(await listAnomalies(params));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [offset, status]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setOffset(0); }, [status]);

  const runScan = async () => {
    setBusy(true);
    try {
      const r = await scanAnomalies({});
      push({
        title: `Scan complete — ${r.created} new anomaly event(s)`,
        msg: `${r.scanned_tracks} track(s) analysed, ${r.already_flagged} already flagged`,
        severity: r.created ? "high" : "medium",
      });
      load();
    } catch (e) {
      push({ title: "Scan failed", msg: e?.response?.data?.error?.message || "", severity: "high" });
    } finally {
      setBusy(false);
    }
  };

  const review = async (id, s) => {
    try { await reviewAnomaly(id, s); load(); }
    catch { push({ title: "Review failed", severity: "high" }); }
  };

  const items = data?.items || [];
  const total = data?.total || 0;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <Activity size={16} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>AI Anomaly Detection</span>
        <span style={{ color: C.muted, fontSize: 12 }}>· {total}</span>
        <button onClick={load} style={iconBtn} title="Refresh"><RefreshCw size={12} /></button>
        {manage && (
          <button onClick={runScan} disabled={busy} style={{ ...iconBtn, color: C.accent, marginLeft: "auto" }}>
            <ScanSearch size={12} /> {busy ? "Scanning…" : "Run scan"}
          </button>
        )}
      </div>
      <div style={{ color: C.muted, fontSize: 11, marginBottom: 12 }}>
        Stopped / loitering vehicles inferred from stored ByteTrack tracks. AI-assisted — review before acting.
      </div>

      {error && <ErrorBanner message="Could not load anomaly events." onRetry={load} />}

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <select value={status} onChange={(e) => setStatus(e.target.value)} style={iconBtn}>
          {STATUSES.map((s) => <option key={s} value={s}>{s || "All statuses"}</option>)}
        </select>
      </div>

      <div style={panel}>
        {loading ? (
          <div style={{ padding: 14 }}><SkeletonRows rows={5} height={48} /></div>
        ) : items.length === 0 ? (
          <EmptyState icon={Activity} title="No anomalies detected"
            hint={manage ? "Run a scan over recorded events." : "Stopped-vehicle detections will appear here."} />
        ) : (
          items.map((a) => (
            <div key={a.id} style={{ padding: "12px 14px", borderTop: `1px solid ${C.border}` }}>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ fontSize: 9, fontWeight: 700, color: KIND_COLOR[a.kind] || C.amber }}>
                  {KIND_LABEL[a.kind] || a.kind}
                </span>
                <span style={{ fontSize: 8, fontWeight: 700, color: C.violet, border: `1px solid ${C.violet}`, borderRadius: 3, padding: "0 4px" }}>
                  AI-GENERATED
                </span>
                <span style={{ fontFamily: "monospace", color: C.accent }}>{a.camera_code || a.camera_id}</span>
                <span style={{ fontFamily: "monospace", color: C.amber }}>{a.plate_number_normalized || "unknown"}</span>
                <ConfidenceBadge level={a.confidence_level} score={a.confidence_score} method={a.reasoning} />
                <span style={{ marginLeft: "auto", fontSize: 10, color: a.status === "NEW" ? C.red : C.muted }}>{a.status}</span>
              </div>
              <div style={{ color: C.muted, fontSize: 11, marginTop: 4 }}>
                {anomalyDetail(a)} ·
                {" "}{fmtDateTime(a.first_seen)} → {fmtDateTime(a.last_seen)}
                {a.location_desc ? ` · ${a.location_desc}` : ""}
              </div>
              {a.reasoning && <div style={{ color: C.dim, fontSize: 10, marginTop: 2 }}>{a.reasoning}</div>}
              <div style={{ display: "flex", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
                {a.alert_id && (
                  <Link to={`/alerts?focus=${a.alert_id}`} style={linkBtn}>View alert</Link>
                )}
                {a.plate_number_normalized && a.plate_number_normalized !== "UNKNOWN" && (
                  <Link to={`/investigation?plate=${a.plate_number_normalized}`} style={linkBtn}>Trace vehicle</Link>
                )}
                {manage && a.status === "NEW" && (
                  <>
                    <button style={linkBtn} onClick={() => review(a.id, "REVIEWED")}>Mark reviewed</button>
                    <button style={{ ...linkBtn, color: C.red }} onClick={() => review(a.id, "DISMISSED")}>Dismiss</button>
                  </>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      <Pager offset={offset} total={total} onPage={setOffset} loading={loading} page={PAGE} />
    </div>
  );
}

const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" };
const iconBtn = { background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "5px 8px", fontSize: 11, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4 };
const linkBtn = { background: "transparent", border: "none", color: C.accent, fontSize: 10, cursor: "pointer", padding: 0, textDecoration: "none" };
