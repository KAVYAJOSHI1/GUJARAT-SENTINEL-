// ─── Design tokens (dark, corporate command-center) ──────────────────────────
// Single source of truth for colours. The exact same values are mirrored as CSS
// custom properties in src/styles/tokens.css so that CSS-only consumers
// (global styles, and Vishakha's Leaflet / GIS layer on feature/vishakha-
// investigation) stay visually consistent with these JS-styled components.
// If you change a value here, change it there too.
export const C = {
  bg: "#12161C",
  surface: "#181D25",
  panel: "#1F2530",
  border: "#2C333F",
  accent: "#4F9CD9",
  accentGlow: "rgba(79,156,217,0.12)",
  red: "#E0574C",
  redGlow: "rgba(224,87,76,0.12)",
  amber: "#D9A441",
  amberGlow: "rgba(217,164,65,0.12)",
  green: "#3FB37F",
  greenGlow: "rgba(63,179,127,0.12)",
  violet: "#9B8CEE",
  text: "#E5E9EE",
  muted: "#8993A1",
  dim: "#3A4250",
  // used only inside the simulated video-feed panels, which stay near-black
  feedText: "#CFE0EE",
  feedMuted: "#8FA6BC",
};

export const SEVERITY_COLOR = {
  critical: C.red,
  high: C.amber,
  medium: C.violet,
  low: C.muted,
};

// Camera/GIS marker status colours (command-center convention):
//   GREEN  = online / normal
//   RED    = offline (camera down — the serious, "needs attention" state)
//   AMBER  = active incident (an unacknowledged alert on an otherwise-live
//            camera — distinct from a hard offline failure)
//   accent (blue) = selected / focused, handled separately by callers
export const CAMERA_STATUS_COLOR = {
  active: C.green,
  alert: C.amber,
  degraded: C.amber,
  offline: C.red,
};

// Bundled locally (frontend/public/) so the header never depends on a live
// external request during a demo or screen recording.
export const LOGO_URL = "/gujarat-police-logo.png";
