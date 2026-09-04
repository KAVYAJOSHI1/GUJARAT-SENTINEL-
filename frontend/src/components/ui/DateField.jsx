import { useEffect, useMemo, useRef, useState } from "react";
import { Calendar, ChevronLeft, ChevronRight, X } from "lucide-react";
import { C } from "../../theme.js";

// Date-only field for SENTINEL: typed DD/MM/YYYY entry + a compact calendar
// popover themed with the command-center tokens (no native browser picker, no
// "--" placeholders, no time selection). Emits a JS Date (local midnight) or null.
//
// Reusable UI primitive — lives alongside Skeleton / EmptyState / ErrorBanner.

const WEEKDAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const pad = (n) => String(n).padStart(2, "0");

export function toDisplay(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return "";
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`;
}

// Parse "DD/MM/YYYY" (also tolerates "D/M/YYYY", "-" or "." separators).
export function parseDisplay(str) {
  const m = String(str).trim().match(/^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$/);
  if (!m) return null;
  const d = Number(m[1]);
  const mo = Number(m[2]);
  const y = Number(m[3]);
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  const date = new Date(y, mo - 1, d);
  return date.getMonth() === mo - 1 && date.getDate() === d ? date : null;
}

const sameDay = (a, b) =>
  a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

const atMidnight = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());

export default function DateField({ label, value = null, onChange, min = null, max = null, placeholder = "DD/MM/YYYY" }) {
  const [text, setText] = useState(toDisplay(value));
  const [open, setOpen] = useState(false);
  const [viewMonth, setViewMonth] = useState(() => value || new Date());
  const wrapRef = useRef(null);

  // Keep the text box in sync when the value changes from outside (e.g. reset).
  useEffect(() => {
    setText(toDisplay(value));
    if (value) setViewMonth(value);
  }, [value]);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const commitText = (raw) => {
    if (raw.trim() === "") {
      onChange?.(null);
      return;
    }
    const parsed = parseDisplay(raw);
    if (parsed) {
      onChange?.(atMidnight(parsed));
    } else {
      setText(toDisplay(value)); // revert invalid entry
    }
  };

  const minD = min ? atMidnight(min) : null;
  const maxD = max ? atMidnight(max) : null;
  const outOfRange = (d) => (minD && d < minD) || (maxD && d > maxD);

  const grid = useMemo(() => {
    const first = new Date(viewMonth.getFullYear(), viewMonth.getMonth(), 1);
    const startOffset = (first.getDay() + 6) % 7; // Monday-first
    const start = new Date(first);
    start.setDate(first.getDate() - startOffset);
    return Array.from({ length: 42 }, (_, i) => {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      return d;
    });
  }, [viewMonth]);

  const field = {
    background: C.bg,
    border: `1px solid ${C.border}`,
    color: C.text,
    borderRadius: 4,
    padding: "8px 44px 8px 10px",
    fontSize: 13,
    fontFamily: "'Space Mono', monospace",
    width: 150,
  };

  return (
    <div
      ref={wrapRef}
      style={{
        // Own stacking context above the isolated Leaflet map (.gis-map, z 0).
        // Lifted only while the calendar is open so a closed field never
        // shadows sibling UI. z 350 clears the map; below toasts (400).
        position: "relative",
        zIndex: open ? 350 : "auto",
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >
      {label && (
        <span style={{ color: C.muted, fontSize: 10, textTransform: "uppercase", letterSpacing: 1 }}>{label}</span>
      )}
      <div style={{ position: "relative" }}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onBlur={(e) => commitText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commitText(e.currentTarget.value);
            }
          }}
          placeholder={placeholder}
          inputMode="numeric"
          style={field}
        />
        <div style={{ position: "absolute", right: 4, top: 0, bottom: 0, display: "flex", alignItems: "center", gap: 2 }}>
          {value && (
            <button
              type="button"
              aria-label="Clear date"
              onClick={() => {
                setText("");
                onChange?.(null);
              }}
              style={iconBtn}
            >
              <X size={12} />
            </button>
          )}
          <button
            type="button"
            aria-label="Open calendar"
            onClick={() => {
              setViewMonth(value || new Date());
              setOpen((o) => !o);
            }}
            style={iconBtn}
          >
            <Calendar size={13} />
          </button>
        </div>
      </div>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            marginTop: 6,
            zIndex: 400,
            background: C.surface,
            border: `1px solid ${C.border}`,
            borderRadius: 8,
            padding: 10,
            width: 236,
            boxShadow: "0 12px 32px rgba(0,0,0,0.5)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <button type="button" style={iconBtn} aria-label="Previous month"
              onClick={() => setViewMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))}>
              <ChevronLeft size={14} />
            </button>
            <span style={{ fontSize: 12, fontWeight: 600, color: C.text }}>
              {MONTHS[viewMonth.getMonth()]} {viewMonth.getFullYear()}
            </span>
            <button type="button" style={iconBtn} aria-label="Next month"
              onClick={() => setViewMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))}>
              <ChevronRight size={14} />
            </button>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2, marginBottom: 4 }}>
            {WEEKDAYS.map((w) => (
              <div key={w} style={{ textAlign: "center", fontSize: 9, color: C.muted, textTransform: "uppercase", letterSpacing: 0.5, padding: "2px 0" }}>
                {w}
              </div>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2 }}>
            {grid.map((d) => {
              const inMonth = d.getMonth() === viewMonth.getMonth();
              const selected = sameDay(d, value);
              const disabled = outOfRange(d);
              return (
                <button
                  key={d.toISOString()}
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    onChange?.(atMidnight(d));
                    setOpen(false);
                  }}
                  style={{
                    height: 26,
                    borderRadius: 4,
                    border: selected ? `1px solid ${C.accent}` : "1px solid transparent",
                    background: selected ? C.accentGlow : "transparent",
                    color: disabled ? C.dim : selected ? C.accent : inMonth ? C.text : C.muted,
                    fontSize: 11,
                    fontFamily: "'Space Mono', monospace",
                    cursor: disabled ? "not-allowed" : "pointer",
                    opacity: disabled ? 0.4 : 1,
                  }}
                >
                  {d.getDate()}
                </button>
              );
            })}
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
            <button type="button" onClick={() => { onChange?.(atMidnight(new Date())); setOpen(false); }} style={linkBtn}>
              Today
            </button>
            <button type="button" onClick={() => { onChange?.(null); setText(""); setOpen(false); }} style={linkBtn}>
              Clear
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const iconBtn = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "transparent",
  border: "none",
  color: C.muted,
  cursor: "pointer",
  padding: 3,
};

const linkBtn = {
  background: "transparent",
  border: "none",
  color: C.accent,
  fontSize: 10,
  textTransform: "uppercase",
  letterSpacing: 0.8,
  cursor: "pointer",
  padding: "2px 4px",
};
