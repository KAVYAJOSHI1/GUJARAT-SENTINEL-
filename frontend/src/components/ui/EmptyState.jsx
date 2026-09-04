import { Inbox } from "lucide-react";
import { C } from "../../theme.js";

// Empty-data placeholder (README §7 / §15 "No active camera feeds found").
export default function EmptyState({ icon: Icon = Inbox, title, hint }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        padding: "40px 24px",
        color: C.muted,
        textAlign: "center",
      }}
    >
      <Icon size={28} strokeWidth={1.5} />
      <div style={{ color: C.text, fontSize: 13, fontWeight: 600 }}>{title}</div>
      {hint && <div style={{ fontSize: 11 }}>{hint}</div>}
    </div>
  );
}
