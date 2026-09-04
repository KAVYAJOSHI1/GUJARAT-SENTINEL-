import { useEffect } from "react";
import { X } from "lucide-react";
import { C } from "../theme.js";
import AlertFeed from "./AlertFeed.jsx";

// Slide-over alert drawer (README §4.4 — "Slide-over drawer detailing watchlist
// alerts with an Acknowledge button").
export default function AlertDrawer({ open, onClose, alerts, loading, critCount, onAck, onAckAll }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(6,9,13,0.55)",
        zIndex: 250,
        display: "flex",
        justifyContent: "flex-end",
        animation: "fadeIn 0.15s ease-out",
      }}
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(420px, 100%)",
          height: "100%",
          background: C.surface,
          borderLeft: `1px solid ${C.border}`,
          display: "flex",
          flexDirection: "column",
          animation: "drawerIn 0.2s ease-out",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "10px 14px",
            borderBottom: `1px solid ${C.border}`,
          }}
        >
          <span style={{ fontWeight: 700, fontSize: 13, color: C.text }}>Alert Drawer</span>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{ background: "transparent", border: "none", color: C.muted, cursor: "pointer", display: "flex" }}
          >
            <X size={16} />
          </button>
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <AlertFeed
            alerts={alerts}
            loading={loading}
            critCount={critCount}
            onAck={onAck}
            onAckAll={onAckAll}
            maxHeight="none"
            title="Watchlist Alerts"
          />
        </div>
      </aside>
    </div>
  );
}
