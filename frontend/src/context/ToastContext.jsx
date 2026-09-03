import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

const ToastContext = createContext(null);

// Short synthesised chime for incoming alerts (README §5 — "acoustic popups").
// Uses the Web Audio API so there is no binary asset to ship. Higher pitch for
// critical alerts. Silently no-ops if the browser blocks audio before a gesture.
function playChime(severity) {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    const base = severity === "critical" ? 880 : severity === "high" ? 660 : 520;
    osc.type = "sine";
    osc.frequency.setValueAtTime(base, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(base * 1.5, ctx.currentTime + 0.12);
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.12, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.4);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.42);
    osc.onended = () => ctx.close();
  } catch {
    /* audio not available — visual toast still shows */
  }
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const [muted, setMuted] = useState(false);
  const mutedRef = useRef(muted);
  mutedRef.current = muted;

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (toast) => {
      const id = toast.id ?? `toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const entry = { id, severity: "medium", ...toast };
      setToasts((prev) => [entry, ...prev].slice(0, 4));
      if (!mutedRef.current && (entry.severity === "critical" || entry.severity === "high")) {
        playChime(entry.severity);
      }
      const ttl = entry.severity === "critical" ? 9000 : 6000;
      setTimeout(() => dismiss(id), ttl);
      return id;
    },
    [dismiss]
  );

  const value = useMemo(
    () => ({ toasts, push, dismiss, muted, toggleMuted: () => setMuted((m) => !m) }),
    [toasts, push, dismiss, muted]
  );

  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>;
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx;
}
