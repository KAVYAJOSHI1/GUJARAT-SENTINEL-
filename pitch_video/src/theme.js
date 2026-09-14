// Ported 1:1 from the actual product's brand sources — never invented here:
//   - frontend/src/styles/index.css   .hp-root block (the Orqis landing-page theme)
//   - frontend/src/theme.js           the C{} app-status palette (amber/red/green)
// This is the single source of truth for color/type in this video.
export const theme = {
  // ground (Orqis .hp-root)
  bg: "#0a110f",
  bg2: "#101a17",
  bg3: "#15221e",
  surface: "#131e1a",
  // text (Orqis .hp-root)
  text: "#f5f0e8",
  text2: "#8aa098",
  text3: "#5a6e66",
  // brand accent (Orqis .hp-root)
  accent: "#5ecfb8",
  accentLight: "#8ee4d0",
  viridian: "#1a3d32",
  // real operational-status semantics, from the app's own theme.js (C.amber/red/green) —
  // used ONLY for alert/status indicators, never as the brand accent
  amber: "#D9A441",
  red: "#E0574C",
  green: "#3FB37F",

  fontDisplay: "'Anton', sans-serif",
  fontMono: "'DM Mono', ui-monospace, monospace",
  fontSans: "'Inter', -apple-system, system-ui, sans-serif",
};

// Real seeded-scenario values (the same figures the actual landing page's
// Hero.jsx HUD cards use) — never invented, never the mockup's statewide numbers.
export const REAL_DEMO = {
  journey: ["CAM-01", "CAM-02", "CAM-04", "CAM-06", "CAM-08"],
  journeyLabels: {
    "CAM-01": "PALDI CIRCLE",
    "CAM-02": "NEHRU BRIDGE WEST",
    "CAM-04": "INCOME TAX CIRCLE",
    "CAM-06": "VIJAY CROSS ROAD",
    "CAM-08": "RANIP CROSS ROAD",
  },
  plate: "GJ18TC0450",
  caseId: "CASE-2026-9001",
  incidentId: "INC-2026-9001",
  anprConfidence: "93%",
  camerasLive: "8",
  alertLatency: "<1s",
  hallucinatedPlates: "0",
};
