import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowUpCircle, Car, Crosshair, FolderPlus, ImageOff, MapPin } from "lucide-react";
import { C, SEVERITY_COLOR } from "../theme.js";
import { canManageOps, evidenceUrl } from "../services/api.js";
import { useMediaTicket } from "../services/mediaTicket.js";
import { createIncident, escalateAlert } from "../services/opsApi.js";
import { useToast } from "../context/ToastContext.jsx";
import SeverityBadge from "./SeverityBadge.jsx";

// One incident card (README task §2 — Live Incident / Alert Center).
// Everything shown comes straight from the real Alert row (never invented):
// severity/type from the watchlist engine, plate + camera + location from
// the join the backend now does, evidence via the existing proxy.
export default function AlertRow({ alert, onAck, onViewEvidence }) {
  const navigate = useNavigate();
  const { push } = useToast();
  const [imgFailed, setImgFailed] = useState(false);
  const [creating, setCreating] = useState(false);
  const borderCol = SEVERITY_COLOR[alert.severity] || C.muted;
  const mediaTicket = useMediaTicket(); // don't render an evidence <img> before a real credential exists
  const thumb = alert.eventId && mediaTicket ? evidenceUrl(alert.eventId) : null;
  const trackable = alert.vehicle && alert.vehicle !== "UNKNOWN";
  // A real backend alert id is a UUID; the WS-fallback simulator uses
  // "alert-<ts>". Only real, persisted alerts can be promoted to incidents.
  const canPromote =
    canManageOps() && !alert.simulated && /^[0-9a-f-]{20,}$/i.test(String(alert.id || ""));

  const openIncident = async () => {
    setCreating(true);
    try {
      const inc = await createIncident({ alert_id: alert.id });
      push({ title: `Incident ${inc.incident_number} opened`, severity: "medium" });
      navigate(`/incidents/${inc.id}`);
    } catch (e) {
      const details = e?.response?.data?.error?.details;
      if (e?.response?.status === 409 && details?.incident_id) {
        push({ title: `Alert already has ${details.incident_number}`, severity: "medium" });
        navigate(`/incidents/${details.incident_id}`);
      } else {
        push({ title: "Could not open incident", msg: e?.response?.data?.error?.message || "", severity: "high" });
      }
    } finally {
      setCreating(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        alignItems: "flex-start",
        padding: "10px 14px",
        borderLeft: `3px solid ${alert.ack ? C.dim : borderCol}`,
        background: alert.ack ? "transparent" : `${borderCol}14`,
        opacity: alert.ack ? 0.6 : 1,
        marginBottom: 4,
        borderRadius: "0 4px 4px 0",
        transition: "opacity 0.2s, background 0.2s",
      }}
    >
      {/* Evidence thumbnail — the same evidence proxy every other panel uses. */}
      <div
        style={{
          width: 52,
          height: 52,
          borderRadius: 4,
          background: "#000",
          flexShrink: 0,
          overflow: "hidden",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {thumb && !imgFailed ? (
          <img
            src={thumb}
            alt={`Evidence for ${alert.vehicle || alert.cam}`}
            onError={() => setImgFailed(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        ) : (
          <ImageOff size={16} color={C.dim} />
        )}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 3, flexWrap: "wrap" }}>
          <SeverityBadge s={alert.severity} />
          {alert.simulated && (
            <span
              title="Backend/WebSocket unreachable — this is a locally-generated demo alert, not a live detection"
              style={{
                color: C.violet,
                border: `1px solid ${C.violet}`,
                borderRadius: 3,
                padding: "1px 5px",
                fontSize: 8,
                fontWeight: 700,
                letterSpacing: 0.5,
                fontFamily: "monospace",
              }}
            >
              SIMULATED
            </span>
          )}
          {alert.isAnomaly && (
            <span
              title="AI-assisted anomaly detection — stopped / loitering vehicle. Not a watchlist match."
              style={{ color: C.violet, border: `1px solid ${C.violet}`, borderRadius: 3, padding: "0 5px", fontSize: 8, fontWeight: 700, letterSpacing: 0.5 }}
            >
              AI ANOMALY
            </span>
          )}
          <span style={{ color: C.muted, fontSize: 10, fontFamily: "monospace" }}>
            {alert.isAnomaly ? "STOPPED VEHICLE" : alert.type}
          </span>
          <span style={{ color: C.accent, fontSize: 10, fontFamily: "monospace" }}>{alert.cam}</span>
        </div>
        <div style={{ color: C.text, fontSize: 12 }}>{alert.msg}</div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 3 }}>
          {alert.vehicle && (
            <span style={{ color: C.amber, fontSize: 11, fontFamily: "monospace", display: "flex", alignItems: "center", gap: 4 }}>
              <Car size={11} /> {alert.vehicle}
            </span>
          )}
          {(alert.locationDesc || alert.camName) && (
            <span style={{ color: C.muted, fontSize: 10.5, display: "flex", alignItems: "center", gap: 4 }}>
              <MapPin size={10} /> {alert.locationDesc || alert.camName}
            </span>
          )}
        </div>

        <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
          {trackable && (
            <button
              onClick={() => navigate(`/workspace?plate=${encodeURIComponent(alert.vehicle)}&alert=${encodeURIComponent(alert.id)}`)}
              style={{ ...miniBtn(C.accent), background: C.accent, color: "#0b0f14" }}
            >
              <Crosshair size={10} /> Investigate
            </button>
          )}
          {thumb && (
            <button onClick={() => onViewEvidence?.(alert)} style={miniBtn(C.muted)}>
              View evidence
            </button>
          )}
          {canPromote && (
            <button onClick={openIncident} disabled={creating} style={miniBtn(C.amber)}>
              <FolderPlus size={10} /> {creating ? "Opening…" : "Create incident"}
            </button>
          )}
          {canPromote && alert.rawStatus !== "ESCALATED" && alert.rawStatus !== "RESOLVED" && (
            <button
              onClick={async () => {
                const reason = window.prompt("Escalation reason (goes to a supervisor):");
                if (!reason) return;
                try {
                  await escalateAlert(alert.id, reason);
                  push({ title: "Alert escalated", severity: "high" });
                } catch (e) {
                  push({ title: "Escalate failed", msg: e?.response?.data?.error?.message || "", severity: "high" });
                }
              }}
              style={miniBtn(C.red)}
            >
              <ArrowUpCircle size={10} /> Escalate
            </button>
          )}
        </div>
        {alert.rawStatus === "ESCALATED" && (
          <div style={{ marginTop: 6, color: C.red, fontSize: 10, fontWeight: 700 }}>
            ESCALATED{alert.escalationReason ? ` — ${alert.escalationReason}` : ""}
          </div>
        )}
      </div>

      <div style={{ textAlign: "right", flexShrink: 0 }}>
        <div style={{ color: C.muted, fontSize: 10, fontFamily: "monospace", marginBottom: 6 }}>{alert.time}</div>
        {!alert.ack && (
          <button
            onClick={() => onAck?.(alert.id)}
            style={{
              background: "transparent",
              border: `1px solid ${C.dim}`,
              color: C.muted,
              borderRadius: 3,
              padding: "2px 8px",
              fontSize: 10,
              cursor: "pointer",
            }}
          >
            ACK
          </button>
        )}
      </div>
    </div>
  );
}

const miniBtn = (color) => ({
  display: "flex",
  alignItems: "center",
  gap: 4,
  background: "transparent",
  border: `1px solid ${color}`,
  color,
  borderRadius: 3,
  padding: "2px 8px",
  fontSize: 9.5,
  fontWeight: 600,
  cursor: "pointer",
});
