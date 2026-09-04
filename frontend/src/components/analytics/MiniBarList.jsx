import { C } from "../../theme.js";

// Compact horizontal bar list for the Command Center analytics strip
// (README task §1 — "keep charts compact and professional... do not turn
// the page into an overly dense analytics dashboard"). No charting library:
// plain divs sized by percentage, computed from data the caller already
// fetched — this never issues its own request.
export default function MiniBarList({ title, icon: Icon, items = [], loading = false, emptyHint = "No data yet" }) {
  const max = Math.max(1, ...items.map((i) => i.value));

  return (
    <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6, padding: "10px 12px", flex: 1, minWidth: 200 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, color: C.muted, fontSize: 10, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
        {Icon && <Icon size={11} />} {title}
      </div>
      {loading ? (
        <div style={{ color: C.dim, fontSize: 11 }}>Loading…</div>
      ) : items.length === 0 ? (
        <div style={{ color: C.dim, fontSize: 11 }}>{emptyHint}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          {items.map((it) => (
            <div key={it.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 62, flexShrink: 0, color: C.muted, fontSize: 10, fontFamily: "monospace", textAlign: "right", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {it.label}
              </span>
              <div style={{ flex: 1, background: C.bg, borderRadius: 3, height: 8, overflow: "hidden" }}>
                <div
                  style={{
                    width: `${Math.max(4, (it.value / max) * 100)}%`,
                    height: "100%",
                    background: it.color || C.accent,
                    borderRadius: 3,
                    transition: "width 0.3s ease",
                  }}
                />
              </div>
              <span style={{ width: 22, flexShrink: 0, color: C.text, fontSize: 10, fontWeight: 700, fontFamily: "monospace" }}>
                {it.value}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
