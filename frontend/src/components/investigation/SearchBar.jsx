import { useState } from "react";
import { AlertTriangle, Search } from "lucide-react";
import { C } from "../../theme.js";
import { isValidPlate, normalizePlate, PLATE_EXAMPLE } from "../../utils/plate.js";
import DateField from "../ui/DateField.jsx";

// Vehicle Search Console (DEVELOPER_README §14.5): plate string lookup + optional
// DATE-ONLY range filters. Validates the Gujarat plate format client-side
// (§15 — "Please enter a valid registration number") and that From <= To.
export default function SearchBar({ initialPlate = "", loading, onSearch }) {
  const [plate, setPlate] = useState(initialPlate);
  const [from, setFrom] = useState(null); // Date | null
  const [to, setTo] = useState(null); // Date | null
  const [error, setError] = useState("");

  const submit = (e) => {
    e.preventDefault();

    if (!isValidPlate(plate)) {
      setError(`Please enter a valid registration number (e.g. ${PLATE_EXAMPLE}).`);
      return;
    }
    if (from && to && from > to) {
      setError("The “From” date cannot be later than the “To” date.");
      return;
    }
    setError("");

    // Convert to ISO for the search layer. "To" covers the whole day (23:59:59).
    const toEnd = to ? new Date(to.getFullYear(), to.getMonth(), to.getDate(), 23, 59, 59, 999) : undefined;
    onSearch(normalizePlate(plate), {
      from: from ? from.toISOString() : undefined,
      to: toEnd ? toEnd.toISOString() : undefined,
    });
  };

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, flex: "1 1 220px" }}>
          <span style={{ color: C.muted, fontSize: 10, textTransform: "uppercase", letterSpacing: 1 }}>
            Registration plate
          </span>
          <input
            value={plate}
            onChange={(e) => setPlate(e.target.value.toUpperCase())}
            placeholder={PLATE_EXAMPLE}
            autoFocus
            style={{
              background: C.bg,
              border: `1px solid ${C.border}`,
              color: C.text,
              borderRadius: 4,
              padding: "8px 10px",
              fontSize: 13,
              fontFamily: "'Space Mono', monospace",
              letterSpacing: 1.5,
            }}
          />
        </label>

        <DateField label="From" value={from} onChange={setFrom} max={to} />
        <DateField label="To" value={to} onChange={setTo} min={from} />

        <button
          type="submit"
          disabled={loading}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            background: C.accentGlow,
            border: `1px solid ${C.accent}`,
            color: C.accent,
            borderRadius: 4,
            padding: "8px 16px",
            fontSize: 12,
            fontWeight: 600,
            cursor: loading ? "default" : "pointer",
            height: 36,
          }}
        >
          <Search size={13} /> {loading ? "Searching…" : "Search"}
        </button>
      </div>

      {error && (
        <div
          role="alert"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            background: C.amberGlow,
            border: `1px solid ${C.amber}55`,
            color: C.text,
            borderRadius: 6,
            padding: "6px 12px",
            fontSize: 12,
          }}
        >
          <AlertTriangle size={14} color={C.amber} />
          {error}
        </div>
      )}
    </form>
  );
}
