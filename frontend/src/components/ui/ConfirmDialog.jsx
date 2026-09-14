import { useEffect } from "react";
import { C } from "../../theme.js";

// Themed stand-in for window.confirm() — the raw browser dialog looks
// jarringly unstyled against the dark command-center theme.
export default function ConfirmDialog({ open, title = "Confirm", message, confirmLabel = "Confirm", danger = true, onConfirm, onCancel }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;
  const accent = danger ? C.red : C.accent;

  return (
    <div
      onClick={onCancel}
      style={{
        position: "fixed", inset: 0, background: "rgba(6,9,13,0.72)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 400, padding: 20, animation: "fadeIn 0.15s ease-out",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
        style={{
          background: C.surface, border: `1px solid ${accent}`, borderRadius: 8,
          width: "min(360px, 100%)", padding: 18,
        }}
      >
        <div style={{ fontWeight: 700, fontSize: 13, color: C.text, marginBottom: 8 }}>{title}</div>
        <div style={{ color: C.muted, fontSize: 12, marginBottom: 18, lineHeight: 1.5 }}>{message}</div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onCancel} style={cancelBtn}>Cancel</button>
          <button onClick={onConfirm} style={{ ...confirmBtn, background: accent, border: `1px solid ${accent}` }}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

const cancelBtn = {
  background: "transparent", border: `1px solid ${C.border}`, color: C.text,
  borderRadius: 4, padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
};
const confirmBtn = {
  color: "#0b0f14", borderRadius: 4, padding: "6px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer",
};
