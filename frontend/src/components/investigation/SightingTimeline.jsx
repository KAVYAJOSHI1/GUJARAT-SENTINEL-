import { ChevronRight, MapPin, MapPinOff } from "lucide-react";
import { C } from "../../theme.js";
import { isMockCamera } from "../../services/api.js";
import EmptyState from "../ui/EmptyState.jsx";

// Chronological Movement Timeline (DEVELOPER_README §14.6): vertical list of
// camera sightings sorted by timestamp ASC. Clicking a card opens the evidence
// modal. Sightings arrive pre-sorted from normalizeVehicleSearch().
const fmtTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? String(iso)
    : d.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
};

export default function SightingTimeline({ sightings = [], activeId, onSelect }) {
  if (sightings.length === 0) {
    return <EmptyState icon={MapPin} title="No sightings on the timeline" hint="Run a plate search to populate movement history." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {sightings.map((s, i) => {
        const isActive = s.eventId === activeId;
        const isLast = i === sightings.length - 1;
        return (
          <button
            key={s.eventId}
            onClick={() => onSelect?.(s)}
            style={{
              display: "flex",
              gap: 12,
              textAlign: "left",
              background: isActive ? C.accentGlow : "transparent",
              border: "none",
              borderLeft: `1px solid ${C.border}`,
              padding: "0 0 0 0",
              cursor: "pointer",
              position: "relative",
            }}
          >
            {/* rail + node */}
            <div style={{ position: "relative", width: 24, flexShrink: 0 }}>
              <span
                style={{
                  position: "absolute",
                  left: -5,
                  top: 16,
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  background: i === 0 ? C.green : isLast ? C.red : C.accent,
                  border: `2px solid ${C.bg}`,
                }}
              />
            </div>

            <div
              style={{
                flex: 1,
                margin: "6px 0",
                padding: "10px 12px",
                background: C.panel,
                border: `1px solid ${isActive ? C.accent : C.border}`,
                borderRadius: 6,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 8,
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.text, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                  <span style={{ color: C.muted, fontFamily: "monospace" }}>#{i + 1}</span>
                  {s.cameraName}
                  <span style={{ color: C.muted, fontWeight: 400 }}>({s.cameraId})</span>
                  {/* Journey task §9: never let a mock trafficdataset sighting
                      read as a real Sentinel camera sighting. */}
                  {isMockCamera(s.cameraCode || s.cameraId) && (
                    <span style={{ color: C.violet, border: `1px solid ${C.violet}`, borderRadius: 3, padding: "0 4px", fontSize: 8, fontWeight: 700, letterSpacing: 0.5 }}>
                      MOCK
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: C.muted, marginTop: 3, fontFamily: "monospace" }}>
                  {fmtTime(s.timestamp)}
                </div>
                {s.locationDesc && (
                  <div style={{ fontSize: 10.5, color: C.muted, marginTop: 2 }}>{s.locationDesc}</div>
                )}
                <div style={{ fontSize: 10, color: s.hasLocation ? C.dim : C.amber, marginTop: 2, fontFamily: "monospace", display: "flex", alignItems: "center", gap: 4 }}>
                  {s.hasLocation ? (
                    <>
                      <MapPin size={10} /> {s.lat.toFixed(5)}, {s.lng.toFixed(5)}
                    </>
                  ) : (
                    <>
                      <MapPinOff size={10} /> Location unavailable
                    </>
                  )}
                  {Number.isFinite(s.ocrConfidence) ? ` · OCR ${(s.ocrConfidence * 100).toFixed(0)}%` : ""}
                </div>
              </div>
              <ChevronRight size={15} color={C.muted} />
            </div>
          </button>
        );
      })}
    </div>
  );
}
