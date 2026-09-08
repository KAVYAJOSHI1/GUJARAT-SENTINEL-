import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, CornerDownLeft, Search } from "lucide-react";
import { C } from "../theme.js";
import { globalSearch } from "../services/opsApi.js";
import { normalizePlate } from "../utils/plate.js";

const GROUP_COLOR = {
  VEHICLES: C.amber, CAMERAS: C.accent, INCIDENTS: C.amber,
  CASES: C.violet, ALERTS: C.red, EVIDENCE: C.green, ACTIONS: C.accent,
};
const PLATE_RE = /^[A-Z]{2}[\s-]?\d{1,2}[\s-]?[A-Z]{0,3}[\s-]?\d{1,4}$/i;
const NL_RE = /\b(near|after|before|show|suspicious|which|what|where|between|journey|summar|gap)\b/i;

// Phase 16B — global command palette. Ctrl/⌘+K anywhere. Direct entity
// routing (plate / CAM- / INC- / CASE-), grouped Global-Search results,
// and a natural-language handoff to the AI Copilot. Keyboard-first.
export default function CommandPalette() {
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [sel, setSel] = useState(0);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);
  const timer = useRef(null);

  const close = useCallback(() => { setOpen(false); setQ(""); setRes(null); setSel(0); }, []);

  // global hotkey
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape" && open) {
        close();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 30); }, [open]);

  // debounced search
  useEffect(() => {
    clearTimeout(timer.current);
    const term = q.trim();
    if (term.length < 2) { setRes(null); return; }
    setBusy(true);
    timer.current = setTimeout(() => {
      globalSearch(term).then((d) => { setRes(d); setSel(0); }).catch(() => setRes(null)).finally(() => setBusy(false));
    }, 220);
    return () => clearTimeout(timer.current);
  }, [q]);

  // build the flat, ordered result list (actions first)
  const flat = useMemo(() => {
    const term = q.trim();
    const out = [];
    if (term) {
      const up = term.toUpperCase();
      if (PLATE_RE.test(term)) {
        out.push({ group: "ACTIONS", label: `Open vehicle ${normalizePlate(term)}`, href: `/workspace?plate=${normalizePlate(term)}` });
      }
      if (/^INC-/i.test(up)) out.push({ group: "ACTIONS", label: `Open incident ${up}`, href: `/incidents?focus=${up}` });
      if (/^CASE-/i.test(up)) out.push({ group: "ACTIONS", label: `Open case ${up}`, href: `/cases?focus=${up}` });
      if (/^CAM[-_]?\d/i.test(up)) out.push({ group: "ACTIONS", label: `Camera intelligence ${up}`, href: `/camera-intelligence/${up}` });
      if (NL_RE.test(term)) {
        out.push({ group: "ACTIONS", ai: true, label: `Ask SENTINEL: "${term}"`, href: `/copilot?q=${encodeURIComponent(term)}` });
      }
    }
    const groups = res?.groups || {};
    for (const [name, hits] of Object.entries(groups)) {
      for (const h of hits) out.push({ group: name, label: h.label, sub: h.sublabel, href: h.href });
    }
    return out;
  }, [q, res]);

  const goSel = useCallback(() => {
    const item = flat[sel];
    if (item) { nav(item.href); close(); }
    else if (q.trim()) { nav(`/search?q=${encodeURIComponent(q.trim())}`); close(); }
  }, [flat, sel, q, nav, close]);

  if (!open) return null;

  return (
    <div onMouseDown={close} style={{
      position: "fixed", inset: 0, background: "rgba(6,9,13,0.6)", zIndex: 4000,
      display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: "12vh",
    }}>
      <div onMouseDown={(e) => e.stopPropagation()} style={{
        width: "min(620px, 92vw)", background: C.surface, border: `1px solid ${C.accent}55`,
        borderRadius: 10, overflow: "hidden", boxShadow: "0 24px 60px rgba(0,0,0,0.5)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 14px", borderBottom: `1px solid ${C.border}` }}>
          <Search size={15} color={C.muted} />
          <input ref={inputRef} value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, flat.length - 1)); }
              else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
              else if (e.key === "Enter") { e.preventDefault(); goSel(); }
            }}
            placeholder="Search plate, CAM-07, INC-1024, CASE-204 — or ask a question…"
            style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: C.text, fontSize: 14 }} />
          <kbd style={kbd}>ESC</kbd>
        </div>

        <div style={{ maxHeight: "48vh", overflowY: "auto" }}>
          {busy && <div style={{ padding: 12, color: C.dim, fontSize: 11 }}>Searching…</div>}
          {!busy && q.trim().length >= 2 && flat.length === 0 && (
            <div style={{ padding: 14, color: C.muted, fontSize: 12 }}>
              No matches. <span style={{ color: C.accent }}>Enter</span> to open Advanced Search.
            </div>
          )}
          {flat.map((it, i) => (
            <button key={it.href + i} onMouseEnter={() => setSel(i)} onClick={goSel}
              style={{
                display: "flex", width: "100%", textAlign: "left", gap: 10, alignItems: "center",
                background: i === sel ? C.accentGlow : "transparent", border: "none",
                borderLeft: `2px solid ${i === sel ? C.accent : "transparent"}`,
                padding: "9px 14px", cursor: "pointer", color: C.text,
              }}>
              <span style={{ fontSize: 8, fontWeight: 800, color: GROUP_COLOR[it.group] || C.muted, minWidth: 62 }}>
                {it.group}
              </span>
              {it.ai && <Bot size={12} color={C.accent} />}
              <span style={{ flex: 1, fontSize: 12.5, fontFamily: it.group === "VEHICLES" || it.group === "ACTIONS" ? "monospace" : "inherit" }}>
                {it.label}
                {it.sub && <span style={{ color: C.muted, marginLeft: 8, fontFamily: "inherit" }}>{it.sub}</span>}
              </span>
              {i === sel && <CornerDownLeft size={12} color={C.muted} />}
            </button>
          ))}
          {!q.trim() && (
            <div style={{ padding: 14, color: C.dim, fontSize: 11, lineHeight: 1.8 }}>
              <div><kbd style={kbd}>↑</kbd><kbd style={kbd}>↓</kbd> navigate · <kbd style={kbd}>↵</kbd> open · <kbd style={kbd}>Ctrl</kbd>+<kbd style={kbd}>K</kbd> toggle</div>
              <div style={{ marginTop: 4 }}>Try: <code>GJ18TC0450</code> · <code>CAM-07</code> · <code>INC-2026-9001</code> · <code>show suspicious vehicles after 9 PM</code></div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const kbd = {
  background: C.panel, border: `1px solid ${C.border}`, borderRadius: 3,
  padding: "0 5px", fontSize: 9, color: C.muted, fontFamily: "monospace",
};
