import { C } from "../theme.js";

export default function Footer({ backendLive }) {
  return (
    <footer
      style={{
        background: C.surface,
        borderTop: `1px solid ${C.border}`,
        padding: "6px 24px",
        display: "flex",
        alignItems: "center",
        gap: 24,
        rowGap: 4,
        flexWrap: "wrap",
        fontSize: 10,
        color: C.muted,
      }}
    >
      <span style={{ color: backendLive ? C.green : C.amber }}>
        ● {backendLive ? "SYSTEM OPERATIONAL" : "DEGRADED — MOCK DATA"}
      </span>
      <span>
        Backend: <span style={{ color: C.text }}>api.sentinel.gujarat.gov.in</span>
      </span>
      <span>
        Operator: <span style={{ color: C.text }}>ISHA / CMD-01</span>
      </span>
      <span>
        Shift: <span style={{ color: C.text }}>14:00 – 22:00</span>
      </span>
      <span style={{ marginLeft: "auto" }}>Gujarat Police — Integrated Traffic Management System</span>
    </footer>
  );
}
