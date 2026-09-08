import { ArrowDown, MapPin } from "lucide-react";
import { C } from "../../theme.js";
import { fmtDateTime, fmtTime } from "../../utils/datetime.js";

const CONF = {
  HIGH: [C.green, "HIGH"],
  MEDIUM: [C.amber, "MEDIUM"],
  LOW: [C.muted, "LOW"],
};

function fmtGap(s) {
  if (s == null) return "—";
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}

// Phase 13 — Journey Intelligence. CONFIRMED (observed) sightings chained by
// INFERRED (not observed) camera-to-camera transitions. Distance/speed are
// only shown when the backend computed them from real coordinates.
export default function JourneyIntelligence({ result, onSelectCamera }) {
  const sightings = result?.sightings || [];
  const transitions = result?.transitions || [];
  if (sightings.length === 0) return null;

  // build an interleaved [sighting, transition?, sighting, ...] list keyed by camera+time
  const tByFrom = new Map();
  for (const t of transitions) tByFrom.set(`${t.fromCameraId}|${t.fromTimestamp}`, t);

  return (
    <section style={panel}>
      <div style={panelHead}>
        <span>Journey Intelligence</span>
        <span style={{ color: C.muted, fontWeight: 400, fontSize: 10 }}>
          {result.confirmedSightings ?? sightings.length} confirmed sighting(s) ·{" "}
          {transitions.length} inferred transition(s)
        </span>
      </div>
      <div style={{ padding: 12 }}>
        {sightings.map((s, i) => {
          const t = tByFrom.get(`${s.cameraId}|${s.timestamp}`);
          return (
            <div key={s.eventId}>
              {/* CONFIRMED sighting */}
              <button
                onClick={() => onSelectCamera?.(s)}
                style={{
                  display: "block", width: "100%", textAlign: "left", cursor: "pointer",
                  background: C.panel, border: `1px solid ${C.border}`, borderLeft: `3px solid ${C.green}`,
                  borderRadius: 6, padding: "8px 10px",
                }}
              >
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <span style={{ fontSize: 8, fontWeight: 800, color: C.green, letterSpacing: 0.6 }}>CONFIRMED</span>
                  <span style={{ fontFamily: "monospace", color: C.accent, fontSize: 12 }}>
                    #{i + 1} {s.cameraCode || s.cameraId}
                  </span>
                  {s.isMock && (
                    <span style={{ color: C.violet, border: `1px solid ${C.violet}`, borderRadius: 3, padding: "0 4px", fontSize: 8, fontWeight: 700 }}>MOCK</span>
                  )}
                  <span style={{ marginLeft: "auto", color: C.muted, fontSize: 10, fontFamily: "monospace" }}>
                    {fmtDateTime(s.timestamp)} {fmtTime(s.timestamp)}
                  </span>
                </div>
                <div style={{ color: C.muted, fontSize: 10.5, marginTop: 3 }}>
                  {s.locationDesc || s.cameraName}
                  {!s.hasLocation && <span style={{ color: C.amber }}> · location unavailable</span>}
                </div>
                <div style={{ display: "flex", gap: 14, marginTop: 4, fontSize: 10, color: C.dim, flexWrap: "wrap" }}>
                  <span>plate <b style={{ color: C.text }}>{result.plate}</b></span>
                  {s.vehicleType && <span>type <b style={{ color: C.text }}>{s.vehicleType}</b></span>}
                  {s.vehicleColor && <span>colour <b style={{ color: C.text }}>{s.vehicleColor}</b></span>}
                  {Number.isFinite(s.ocrConfidence) && (
                    <span>conf <b style={{ color: C.text }}>{(s.ocrConfidence * 100).toFixed(0)}%</b></span>
                  )}
                </div>
              </button>

              {/* INFERRED transition */}
              {t && (
                <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0 6px 14px" }}>
                  <ArrowDown size={13} color={C.dim} />
                  <div style={{ fontSize: 10, color: C.muted, flex: 1 }}>
                    <span style={{ fontSize: 8, fontWeight: 800, color: C.amber, letterSpacing: 0.6, marginRight: 6 }}>
                      INFERRED
                    </span>
                    {t.fromCameraCode} → {t.toCameraCode} · gap {fmtGap(t.timeDiffSeconds)}
                    {t.distanceMeters != null && ` · ${(t.distanceMeters / 1000).toFixed(2)} km`}
                    {t.estimatedSpeedKmh != null
                      ? ` · ~${t.estimatedSpeedKmh} km/h`
                      : (t.notes || []).length
                        ? ` · ${t.notes[0]}`
                        : ""}
                    {(() => {
                      const [c, label] = CONF[t.confidenceLevel] || CONF.LOW;
                      return (
                        <span style={{ color: c, marginLeft: 6, fontWeight: 700 }}>[{label}]</span>
                      );
                    })()}
                  </div>
                </div>
              )}
            </div>
          );
        })}
        <div style={{ color: C.dim, fontSize: 9.5, marginTop: 6, display: "flex", alignItems: "center", gap: 4 }}>
          <MapPin size={10} /> Sightings are observed facts. Transitions between cameras are inferred — the
          vehicle was not seen moving. Distance/speed shown only when both cameras are geolocated.
        </div>
      </div>
    </section>
  );
}

const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden", marginBottom: 12 };
const panelHead = { padding: "10px 14px", borderBottom: `1px solid ${C.border}`, fontWeight: 600, fontSize: 12, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 };
