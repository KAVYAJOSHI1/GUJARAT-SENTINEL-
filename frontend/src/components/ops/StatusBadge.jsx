import { C } from "../../theme.js";

// Status pill for incident / case lifecycle states. Colour convention matches
// the command-center severity language: blue = new/open, amber = in-progress,
// green = resolved, dim = closed.
const INCIDENT = {
  NEW: [C.accent, "In queue"],
  ACKNOWLEDGED: [C.violet, "Seen"],
  INVESTIGATING: [C.amber, "Working"],
  RESOLVED: [C.green, "Resolved"],
  CLOSED: [C.muted, "Closed"],
};

const CASE = {
  OPEN: [C.accent, "Open"],
  INVESTIGATING: [C.amber, "Working"],
  ON_HOLD: [C.violet, "On hold"],
  RESOLVED: [C.green, "Resolved"],
  CLOSED: [C.muted, "Closed"],
};

export default function StatusBadge({ status, kind = "incident" }) {
  const map = kind === "case" ? CASE : INCIDENT;
  const [color] = map[status] || [C.muted];
  return (
    <span
      style={{
        display: "inline-block",
        background: `${color}1e`,
        color,
        border: `1px solid ${color}44`,
        borderRadius: 3,
        padding: "1px 7px",
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: 0.6,
        textTransform: "uppercase",
        whiteSpace: "nowrap",
      }}
    >
      {String(status || "").replace(/_/g, " ")}
    </span>
  );
}
