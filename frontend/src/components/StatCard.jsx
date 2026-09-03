import { C } from "../theme.js";
import Pulse from "./Pulse.jsx";
import { Skeleton } from "./ui/Skeleton.jsx";

export default function StatCard({ label, value, sub, icon: Icon, color = C.accent, pulse, loading }) {
  return (
    <div
      style={{
        background: C.panel,
        border: `1px solid ${C.border}`,
        borderRadius: 6,
        padding: "14px 18px",
        flex: 1,
        minWidth: 150,
      }}
    >
      <div
        style={{
          color: C.muted,
          fontSize: 10,
          textTransform: "uppercase",
          letterSpacing: 1.2,
          marginBottom: 6,
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        {Icon && <Icon size={12} />} {label}
      </div>
      {loading ? (
        <Skeleton width={72} height={28} />
      ) : (
        <div
          style={{
            color,
            fontSize: 28,
            fontWeight: 700,
            fontFamily: "'Space Mono', monospace",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          {pulse && <Pulse color={color} />} {value}
        </div>
      )}
      {sub && <div style={{ color: C.muted, fontSize: 11, marginTop: 4 }}>{sub}</div>}
    </div>
  );
}
