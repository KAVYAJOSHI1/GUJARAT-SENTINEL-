import { AlertOctagon, AlertTriangle, Info, X } from "lucide-react";
import { C, SEVERITY_COLOR } from "../../theme.js";
import { useToast } from "../../context/ToastContext.jsx";

const ICON = { critical: AlertOctagon, high: AlertTriangle, medium: Info, low: Info };

// Real-time WebSocket toast stack (README §4.5 / §5). Fixed top-right,
// newest on top, auto-dismiss handled by the provider.
export default function ToastContainer() {
  const { toasts, dismiss } = useToast();
  if (!toasts.length) return null;

  return (
    <div
      style={{
        position: "fixed",
        bottom: 44,
        right: 16,
        zIndex: 400,
        display: "flex",
        flexDirection: "column-reverse",
        gap: 10,
        maxWidth: "calc(100vw - 32px)",
      }}
    >
      {toasts.map((t) => {
        const color = SEVERITY_COLOR[t.severity] || C.accent;
        const Icon = ICON[t.severity] || Info;
        return (
          <div
            key={t.id}
            role="status"
            style={{
              width: 320,
              maxWidth: "100%",
              background: C.surface,
              border: `1px solid ${color}`,
              borderLeft: `3px solid ${color}`,
              borderRadius: 6,
              padding: "10px 12px",
              display: "flex",
              gap: 10,
              boxShadow: "0 10px 30px rgba(0,0,0,0.45)",
              animation: "toastIn 0.22s cubic-bezier(0.2, 0.8, 0.2, 1)",
            }}
          >
            <Icon size={16} color={color} style={{ flexShrink: 0, marginTop: 1 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <span style={{ color, fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase" }}>
                  {t.title || t.type || "Alert"}
                </span>
                <span style={{ color: C.muted, fontSize: 10, fontFamily: "monospace" }}>{t.time}</span>
              </div>
              <div style={{ color: C.text, fontSize: 12, marginTop: 3 }}>{t.msg}</div>
              <div style={{ color: C.muted, fontSize: 10, marginTop: 3, fontFamily: "monospace" }}>
                {t.cam}
                {t.vehicle ? ` · ${t.vehicle}` : ""}
              </div>
            </div>
            <button
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss"
              style={{ background: "transparent", border: "none", color: C.muted, cursor: "pointer", display: "flex", height: "fit-content" }}
            >
              <X size={13} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
