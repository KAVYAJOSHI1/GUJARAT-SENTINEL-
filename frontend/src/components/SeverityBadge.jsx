import { C } from "../theme.js";

const MAP = {
  critical: [C.red, "#2E1917"],
  high: [C.amber, "#2E2415"],
  medium: [C.violet, "#221E33"],
  low: [C.muted, "#20242B"],
};

export default function SeverityBadge({ s }) {
  const [fg, bg] = MAP[s] || [C.muted, C.surface];
  return (
    <span
      style={{
        background: bg,
        color: fg,
        border: `1px solid ${fg}33`,
        borderRadius: 3,
        padding: "1px 7px",
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: 1,
        textTransform: "uppercase",
      }}
    >
      {s}
    </span>
  );
}
