import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, ChevronRight, Crosshair, MapPin } from "lucide-react";
import { C } from "../../theme.js";
import { isMockCamera } from "../../services/api.js";
import { formatPlate } from "../../utils/plate.js";

// Phase 7 — the one thing a command-center operator must not miss: unhandled
// HIGH / CRITICAL watchlist alerts, pinned to the top with plate, camera,
// location, time and a one-click route to the vehicle journey. Built purely
// from the real (already-normalised) alert list -- no synthetic incidents.
const SEV_RANK = { critical: 3, high: 2, medium: 1, low: 0 };

export default function IncidentBar({ alerts = [], onOpenDrawer }) {
  const navigate = useNavigate();

  const incidents = useMemo(
    () =>
      alerts
        .filter((a) => !a.ack && !a.simulated && (a.severity === "high" || a.severity === "critical"))
        .sort((a, b) => (SEV_RANK[b.severity] ?? 0) - (SEV_RANK[a.severity] ?? 0) || new Date(b.ts) - new Date(a.ts))
        .slice(0, 4),
    [alerts]
  );

  if (incidents.length === 0) return null;

  const critical = incidents.some((a) => a.severity === "critical");
  const accent = critical ? C.red : C.amber;

  return (
    <div
      style={{
        border: `1px solid ${accent}`,
        background: `${accent}12`,
        borderRadius: 8,
        marginBottom: 14,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          padding: "8px 14px",
          borderBottom: `1px solid ${accent}44`,
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700, fontSize: 12.5, color: accent, letterSpacing: 0.5 }}>
          <AlertTriangle size={15} />
          {incidents.length} ACTIVE {critical ? "CRITICAL" : "HIGH-PRIORITY"} INCIDENT{incidents.length === 1 ? "" : "S"}
        </span>
        {onOpenDrawer && (
          <button
            onClick={onOpenDrawer}
            style={{ background: "transparent", border: `1px solid ${accent}66`, color: accent, borderRadius: 4, padding: "3px 10px", fontSize: 10, fontWeight: 700, cursor: "pointer" }}
          >
            Incident center
          </button>
        )}
      </div>

      <div>
        {incidents.map((a) => {
          const plate = a.vehicle && a.vehicle !== "UNKNOWN" ? a.vehicle : null;
          return (
            <div
              key={a.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "9px 14px",
                borderTop: `1px solid ${accent}22`,
                fontSize: 11.5,
              }}
            >
              <span
                style={{
                  fontSize: 8.5,
                  fontWeight: 800,
                  letterSpacing: 0.6,
                  color: a.severity === "critical" ? C.red : C.amber,
                  border: `1px solid ${a.severity === "critical" ? C.red : C.amber}`,
                  borderRadius: 3,
                  padding: "1px 5px",
                  flexShrink: 0,
                }}
              >
                {a.severity.toUpperCase()}
              </span>

              <span style={{ fontFamily: "'Space Mono', monospace", fontWeight: 700, color: C.text, minWidth: 110 }}>
                {plate ? formatPlate(plate) : "UNKNOWN PLATE"}
              </span>

              <span style={{ color: C.muted, display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
                <MapPin size={11} /> {a.camName || a.cam}
                {isMockCamera(a.cam) && (
                  <span style={{ color: C.violet, border: `1px solid ${C.violet}`, borderRadius: 3, padding: "0 3px", fontSize: 8, fontWeight: 700 }}>MOCK</span>
                )}
              </span>

              <span style={{ color: C.muted, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {a.locationDesc || a.msg}
              </span>

              <span style={{ color: C.dim, fontFamily: "monospace", fontSize: 10, flexShrink: 0 }}>{a.time}</span>

              {plate && (
                <button
                  onClick={() => navigate(`/investigation?plate=${encodeURIComponent(plate)}`)}
                  style={{ display: "flex", alignItems: "center", gap: 4, background: accent, color: "#0b0f14", border: "none", borderRadius: 4, padding: "3px 9px", fontSize: 10, fontWeight: 700, cursor: "pointer", flexShrink: 0 }}
                >
                  <Crosshair size={11} /> Trace <ChevronRight size={11} />
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
