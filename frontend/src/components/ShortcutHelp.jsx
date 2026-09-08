import { useEffect, useState } from "react";
import { C } from "../theme.js";

const SHORTCUTS = [
  ["Ctrl / ⌘ + K", "Global command palette"],
  ["?", "This help"],
  ["J", "Next investigation event"],
  ["K", "Previous investigation event"],
  ["E", "Open evidence for the selected sighting"],
  ["G", "Open the investigation graph"],
  ["A", "Acknowledge the focused alert"],
  ["Space", "Play / pause the journey scrubber"],
  ["Esc", "Close dialog / palette"],
];

// Phase 16 P2 — keyboard shortcut reference. Opens on `?` (when not typing).
export default function ShortcutHelp() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e) => {
      const t = e.target;
      const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
      if (!typing && e.key === "?") { e.preventDefault(); setOpen((v) => !v); }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  if (!open) return null;
  return (
    <div onClick={() => setOpen(false)} style={{
      position: "fixed", inset: 0, background: "rgba(6,9,13,0.6)", zIndex: 4000,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: "min(440px, 92vw)", background: C.surface, border: `1px solid ${C.border}`,
        borderRadius: 10, overflow: "hidden",
      }}>
        <div style={{ padding: "12px 16px", borderBottom: `1px solid ${C.border}`, fontWeight: 700 }}>
          Keyboard Shortcuts
        </div>
        <div style={{ padding: 12 }}>
          {SHORTCUTS.map(([k, d]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "5px 4px", fontSize: 12 }}>
              <span style={{ color: C.muted }}>{d}</span>
              <kbd style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 4, padding: "1px 7px", fontSize: 10, fontFamily: "monospace", color: C.text }}>{k}</kbd>
            </div>
          ))}
        </div>
        <div style={{ padding: "8px 16px", borderTop: `1px solid ${C.border}`, color: C.dim, fontSize: 10 }}>
          Shortcuts only fire when you are not typing in a field.
        </div>
      </div>
    </div>
  );
}
