// Phase 16 — shared design primitives. One place for the badges / cards /
// headers that were being re-styled ad hoc across pages. Matches the
// existing dark command-centre design system (theme.js `C`).
import { Link } from "react-router-dom";
import { C } from "../../theme.js";

// ─── colour maps ─────────────────────────────────────────────────────────
export const SEVERITY_COLOR = {
  ESCALATED: C.red, CRITICAL: C.red, HIGH: C.amber, MEDIUM: C.violet, LOW: C.muted,
};
export const STATUS_COLOR = {
  NEW: C.red, ACKNOWLEDGED: C.amber, ESCALATED: C.red, INVESTIGATING: C.accent,
  RESOLVED: C.green, CLOSED: C.muted, OPEN: C.amber, ON_HOLD: C.violet,
  ONLINE: C.green, DEGRADED: C.amber, OFFLINE: C.red, REVIEWED: C.green, DISMISSED: C.muted,
};
export const SOURCE_COLOR = { REAL: C.green, MOCK: C.violet, DEMO: C.amber };
const CONF_COLOR = { HIGH: C.green, MEDIUM: C.amber, LOW: C.muted, INSUFFICIENT: C.dim };

// ─── badges ──────────────────────────────────────────────────────────────
export function Badge({ children, color = C.muted, filled = false, title, style }) {
  return (
    <span title={title} style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      background: filled ? color : "transparent",
      color: filled ? "#0b0f14" : color,
      border: `1px solid ${color}`, borderRadius: 3,
      padding: "1px 6px", fontSize: 9, fontWeight: 800, letterSpacing: 0.5,
      textTransform: "uppercase", whiteSpace: "nowrap", ...style,
    }}>
      {children}
    </span>
  );
}

export const SeverityBadge = ({ level }) => (
  <Badge color={SEVERITY_COLOR[level] || C.muted}>{level}</Badge>
);

export const StatusBadge = ({ status }) => (
  <Badge color={STATUS_COLOR[status] || C.muted}>{String(status).replace(/_/g, " ")}</Badge>
);

export const SourceBadge = ({ source }) => (
  <Badge color={SOURCE_COLOR[source] || C.green}>
    {source === "DEMO" ? "DEMO DATA" : source === "MOCK" ? "MOCK STREAM" : "REAL FEED"}
  </Badge>
);

export function ConfidenceBadge({ level, score, method }) {
  const col = CONF_COLOR[level] || C.muted;
  return (
    <span title={method || ""} style={{
      display: "inline-flex", alignItems: "center", gap: 4, color: col,
      border: `1px solid ${col}`, borderRadius: 3, padding: "1px 6px",
      fontSize: 9, fontWeight: 700,
    }}>
      {level}{score != null ? ` ${Math.round(score * 100)}%` : ""}
    </span>
  );
}

// CONFIRMED vs INFERRED — a first-class primitive so the distinction is
// visually identical everywhere.
export const VerdictBadge = ({ verdict }) => (
  <Badge color={verdict === "CONFIRMED" ? C.green : verdict === "NO_MATCH" ? C.red : C.amber}
    filled={verdict === "CONFIRMED"}>
    {verdict}
  </Badge>
);

// ─── cards / headers ─────────────────────────────────────────────────────
export function MetricCard({ label, value, sub, color = C.accent, onClick, active }) {
  return (
    <div onClick={onClick} style={{
      background: C.panel, border: `1px solid ${active ? color : C.border}`, borderRadius: 6,
      padding: "12px 16px", flex: "1 1 130px", minWidth: 120,
      cursor: onClick ? "pointer" : "default",
    }}>
      <div style={{ color: C.muted, fontSize: 9.5, textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ color, fontSize: 24, fontWeight: 700, fontFamily: "'Space Mono', monospace" }}>
        {value}
      </div>
      {sub && <div style={{ color: C.muted, fontSize: 10, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

export function SectionHeader({ icon: Icon, title, right, sub }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 12px", borderBottom: `1px solid ${C.border}` }}>
      {Icon && <Icon size={12} color={C.accent} />}
      <span style={{ fontWeight: 600, fontSize: 12, color: C.text }}>{title}</span>
      {sub && <span style={{ color: C.muted, fontSize: 10 }}>{sub}</span>}
      {right && <span style={{ marginLeft: "auto" }}>{right}</span>}
    </div>
  );
}

export const Panel = ({ children, style }) => (
  <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden", ...style }}>
    {children}
  </div>
);

// ─── links / buttons ─────────────────────────────────────────────────────
export function EntityLink({ to, kind, label, sub }) {
  return (
    <Link to={to} style={{
      display: "block", textDecoration: "none", color: C.text, padding: "6px 10px",
      borderRadius: 4, border: `1px solid ${C.border}`, background: C.panel, fontSize: 11,
    }}>
      {kind && <span style={{ color: C.muted, fontSize: 8.5, fontWeight: 700, marginRight: 5 }}>{kind}</span>}
      <span style={{ fontFamily: "monospace", color: C.accent }}>{label}</span>
      {sub && <span style={{ color: C.muted, marginLeft: 6 }}>{sub}</span>}
    </Link>
  );
}

export function CommandButton({ children, onClick, to, primary, danger, small, disabled, icon: Icon, title }) {
  const base = {
    display: "inline-flex", alignItems: "center", gap: 6, borderRadius: 5,
    padding: small ? "4px 9px" : "7px 13px", fontSize: small ? 10.5 : 12, fontWeight: 700,
    cursor: disabled ? "not-allowed" : "pointer", whiteSpace: "nowrap",
    opacity: disabled ? 0.5 : 1,
    background: primary ? C.accent : "transparent",
    color: primary ? "#0b0f14" : danger ? C.red : C.text,
    border: `1px solid ${primary ? C.accent : danger ? C.red : C.border}`,
    textDecoration: "none",
  };
  const inner = <>{Icon && <Icon size={small ? 11 : 13} />}{children}</>;
  if (to) return <Link to={to} style={base} title={title}>{inner}</Link>;
  return <button style={base} onClick={onClick} disabled={disabled} title={title}>{inner}</button>;
}

// ─── timeline / evidence ─────────────────────────────────────────────────
export function TimelineDot({ active, color = C.accent }) {
  return (
    <span style={{
      width: active ? 13 : 10, height: active ? 13 : 10, borderRadius: "50%",
      background: color, border: active ? `2px solid ${C.text}` : "none",
      boxShadow: active ? `0 0 8px ${color}` : "none", flexShrink: 0, display: "block",
    }} />
  );
}
