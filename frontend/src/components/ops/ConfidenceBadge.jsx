import { C } from "../../theme.js";

const MAP = {
  HIGH: [C.green, "AI MATCH: HIGH"],
  MEDIUM: [C.amber, "AI MATCH: MEDIUM"],
  LOW: [C.violet, "AI MATCH: LOW"],
  INSUFFICIENT: [C.muted, "INSUFFICIENT DATA"],
};

// Explainability chip (Phase 12 §5). Always makes clear this is an AI
// inference, never a confirmed fact.
export default function ConfidenceBadge({ level, score, method }) {
  const [color, label] = MAP[level] || MAP.INSUFFICIENT;
  return (
    <span
      title={method || ""}
      style={{
        display: "inline-flex", alignItems: "center", gap: 5,
        background: `${color}1e`, color, border: `1px solid ${color}55`,
        borderRadius: 3, padding: "2px 8px", fontSize: 10, fontWeight: 700,
        letterSpacing: 0.5, textTransform: "uppercase",
      }}
    >
      {label}{score != null ? ` · ${Math.round(score * 100)}%` : ""}
    </span>
  );
}
