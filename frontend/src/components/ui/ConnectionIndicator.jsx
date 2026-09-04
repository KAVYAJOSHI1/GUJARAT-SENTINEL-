import { C } from "../../theme.js";
import Pulse from "../Pulse.jsx";

// WebSocket link status pill (README §15 — yellow pulse while reconnecting).
const MAP = {
  connected: { color: C.green, label: "LIVE", pulse: false },
  connecting: { color: C.amber, label: "CONNECTING", pulse: true },
  reconnecting: { color: C.amber, label: "RECONNECTING", pulse: true },
  simulated: { color: C.violet, label: "SIMULATED", pulse: true },
  closed: { color: C.muted, label: "OFFLINE", pulse: false },
};

export default function ConnectionIndicator({ status }) {
  const s = MAP[status] || MAP.connecting;
  return (
    <span
      title={`Alert stream: ${s.label.toLowerCase()}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 9px",
        borderRadius: 999,
        border: `1px solid ${s.color}44`,
        background: `${s.color}14`,
        color: s.color,
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: 0.8,
      }}
    >
      {s.pulse ? (
        <Pulse color={s.color} size={7} />
      ) : (
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: s.color }} />
      )}
      {s.label}
    </span>
  );
}
