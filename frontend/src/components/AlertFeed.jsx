import { BellRing } from "lucide-react";
import { C } from "../theme.js";
import AlertRow from "./AlertRow.jsx";
import EmptyState from "./ui/EmptyState.jsx";
import { SkeletonRows } from "./ui/Skeleton.jsx";

// Scrollable alert list with header actions. Used both inline on the dashboard
// and inside the slide-over <AlertDrawer/> (README §4.4).
export default function AlertFeed({
  alerts = [],
  loading = false,
  critCount = 0,
  onAck,
  onAckAll,
  maxHeight = 520,
  title = "Active Alerts",
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <div
        style={{
          padding: "12px 16px",
          borderBottom: `1px solid ${C.border}`,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexShrink: 0,
          gap: 8,
        }}
      >
        <span style={{ fontWeight: 600, fontSize: 13 }}>{title}</span>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {critCount > 0 && (
            <span style={{ color: C.red, fontSize: 11, fontWeight: 700 }}>{critCount} CRITICAL</span>
          )}
          {onAckAll && (
            <button
              onClick={onAckAll}
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
              ACK ALL
            </button>
          )}
        </div>
      </div>

      <div style={{ overflowY: "auto", flex: 1, padding: "8px 0", maxHeight }}>
        {loading ? (
          <div style={{ padding: "8px 14px" }}>
            <SkeletonRows rows={5} height={54} />
          </div>
        ) : alerts.length === 0 ? (
          <EmptyState icon={BellRing} title="No active alerts" hint="Incoming detections will appear here in real time." />
        ) : (
          alerts.map((a) => <AlertRow key={a.id} alert={a} onAck={onAck} />)
        )}
      </div>
    </div>
  );
}
