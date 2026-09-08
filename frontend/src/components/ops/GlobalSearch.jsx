import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { C } from "../../theme.js";
import { globalSearch } from "../../services/opsApi.js";

const GROUP_COLOR = {
  VEHICLES: C.amber, CAMERAS: C.accent, INCIDENTS: C.amber,
  CASES: C.violet, ALERTS: C.red, EVIDENCE: C.green,
};

// Global Quick Search (Phase 11 FEATURE 14). Debounced; groups results;
// clicking a hit navigates to the connected page.
export default function GlobalSearch() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [open, setOpen] = useState(false);
  const boxRef = useRef(null);
  const timer = useRef(null);

  useEffect(() => {
    const onDoc = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    clearTimeout(timer.current);
    if (q.trim().length < 2) {
      setRes(null);
      return;
    }
    timer.current = setTimeout(() => {
      globalSearch(q.trim())
        .then((d) => { setRes(d); setOpen(true); })
        .catch(() => setRes(null));
    }, 250);
    return () => clearTimeout(timer.current);
  }, [q]);

  const go = (href) => {
    setOpen(false);
    setQ("");
    navigate(href);
  };

  const groups = res?.groups || {};

  return (
    <div ref={boxRef} style={{ position: "relative" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 5, background: C.panel, border: `1px solid ${C.border}`, borderRadius: 4, padding: "3px 8px" }}>
        <Search size={12} color={C.muted} />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => res && setOpen(true)}
          onKeyDown={(e) => e.key === "Enter" && q.trim() && go(`/search`)}
          placeholder="Search plate, camera, INC-, CASE-…"
          style={{ background: "transparent", border: "none", color: C.text, fontSize: 11, width: 190, outline: "none" }}
        />
      </div>

      {open && res && (
        <div style={{
          position: "absolute", top: "calc(100% + 6px)", right: 0, width: 340, maxHeight: 420,
          overflowY: "auto", background: C.surface, border: `1px solid ${C.border}`,
          borderRadius: 6, zIndex: 300, boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
        }}>
          {res.total === 0 ? (
            <div style={{ padding: 14, color: C.muted, fontSize: 11 }}>No matches for “{res.query}”.</div>
          ) : (
            Object.entries(groups).filter(([, hits]) => hits.length).map(([name, hits]) => (
              <div key={name}>
                <div style={{ padding: "6px 12px", fontSize: 9, fontWeight: 700, letterSpacing: 0.8, color: GROUP_COLOR[name] || C.muted, textTransform: "uppercase", borderTop: `1px solid ${C.border}` }}>
                  {name}
                </div>
                {hits.map((h) => (
                  <button key={h.kind + h.id} onClick={() => go(h.href)} style={{
                    display: "block", width: "100%", textAlign: "left", background: "transparent",
                    border: "none", padding: "7px 12px", cursor: "pointer", color: C.text,
                  }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = C.panel)}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                    <div style={{ fontSize: 12, fontFamily: name === "VEHICLES" ? "monospace" : "inherit" }}>{h.label}</div>
                    {h.sublabel && <div style={{ fontSize: 10, color: C.muted }}>{h.sublabel}</div>}
                  </button>
                ))}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
