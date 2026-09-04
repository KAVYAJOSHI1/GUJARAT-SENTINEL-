// ─── Vehicle registration plate helpers (Vishakha · feature/vishakha-investigation) ──
// Officers may type a plate in many shapes: "GJ01AB1234", "GJ-01-AB-1234",
// "gj 01 ab 1234", "G.J.01.AB.1234". Normalise to the canonical compact form
// the backend expects (DEVELOPER_README §9) and validate the Gujarat pattern.

// GJ + 2-digit RTO code + 1–2 letter series + 4-digit number.
const PLATE_RE = /^GJ\d{2}[A-Z]{1,2}\d{4}$/;

export function normalizePlate(raw) {
  return String(raw || "")
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "");
}

export function isValidPlate(raw) {
  return PLATE_RE.test(normalizePlate(raw));
}

// Pretty form for display / report headings: GJ-01-AB-1234
export function formatPlate(raw) {
  const p = normalizePlate(raw);
  const m = p.match(/^(GJ)(\d{2})([A-Z]{1,2})(\d{4})$/);
  return m ? `${m[1]}-${m[2]}-${m[3]}-${m[4]}` : p;
}

export const PLATE_EXAMPLE = "GJ01AB1234";
