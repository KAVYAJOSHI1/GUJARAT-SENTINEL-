import { Car } from "lucide-react";
import { C, SEVERITY_COLOR } from "../theme.js";
import SeverityBadge from "./SeverityBadge.jsx";

export default function AlertRow({ alert, onAck }) {
  const borderCol = SEVERITY_COLOR[alert.severity] || C.muted;
  return (
    <div
      style={{
        display: "flex",
        gap: 12,
        alignItems: "flex-start",
        padding: "10px 14px",
        borderLeft: `3px solid ${alert.ack ? C.dim : borderCol}`,
        background: alert.ack ? "transparent" : `${borderCol}14`,
        opacity: alert.ack ? 0.55 : 1,
        marginBottom: 4,
        borderRadius: "0 4px 4px 0",
        transition: "opacity 0.2s, background 0.2s",
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 3, flexWrap: "wrap" }}>
          <SeverityBadge s={alert.severity} />
          <span style={{ color: C.muted, fontSize: 10, fontFamily: "monospace" }}>{alert.type}</span>
          <span style={{ color: C.accent, fontSize: 10, fontFamily: "monospace" }}>{alert.cam}</span>
        </div>
        <div style={{ color: C.text, fontSize: 12 }}>{alert.msg}</div>
        {alert.vehicle && (
          <div
            style={{
              color: C.amber,
              fontSize: 11,
              fontFamily: "monospace",
              marginTop: 2,
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <Car size={11} /> {alert.vehicle}
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
