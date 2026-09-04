import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, MapPinned } from "lucide-react";
import { C } from "../theme.js";

// ─────────────────────────────────────────────────────────────────────────────
// NOT VISHAKHA'S FILE. This is only a temporary landing pad for the /investigation
// and /map routes so Isha's dashboard deep-links resolve during development.
//
// On feature/vishakha-investigation these routes are replaced by:
//   - frontend/src/pages/InvestigationPage.jsx   (owned by Vishakha)
//   - frontend/src/components/gis/GisMap.jsx      (owned by Vishakha)
// See App.jsx for the wiring point. Do not build GIS / vehicle-history UI here.
// ─────────────────────────────────────────────────────────────────────────────
export default function InvestigationPlaceholder() {
  const [params] = useSearchParams();
  const cam = params.get("cam");
  const plate = params.get("plate");

  return (
    <div
      style={{
        border: `1px dashed ${C.border}`,
        borderRadius: 8,
        padding: "48px 24px",
        textAlign: "center",
        color: C.muted,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 12,
      }}
    >
      <MapPinned size={30} strokeWidth={1.5} color={C.accent} />
      <div style={{ color: C.text, fontSize: 15, fontWeight: 700 }}>GIS Map &amp; Vehicle Investigation Console</div>
      <p style={{ maxWidth: 440, fontSize: 12, lineHeight: 1.6 }}>
        This route is owned by <strong style={{ color: C.text }}>Vishakha</strong> (<code>feature/vishakha-investigation</code>).
        Isha's command center links here so the hand-off contract is testable now.
      </p>

      {(cam || plate) && (
        <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 6, padding: "10px 14px", fontFamily: "monospace", fontSize: 12, color: C.text }}>
          Hand-off params → {cam ? `camera: ${cam}` : ""} {plate ? `plate: ${plate}` : ""}
        </div>
      )}

      <Link
        to="/"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          color: C.accent,
          border: `1px solid ${C.accent}55`,
          borderRadius: 4,
          padding: "6px 12px",
          fontSize: 11,
        }}
      >
        <ArrowLeft size={12} /> Back to Command Center
      </Link>
    </div>
  );
}
