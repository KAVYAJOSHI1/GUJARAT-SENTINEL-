import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Car, Crosshair, MapPin } from "lucide-react";
import { C } from "../theme.js";
import { evidenceUrl, isMockCamera } from "../services/api.js";

// One real AI detection, evidence-first (README task §5): the actual
// evidence frame pulled from the live pipeline is the visual anchor, plate/
// confidence/camera/location/timestamp read off it. UNKNOWN is shown as-is,
// never invented.
export default function DetectionRow({ det, onViewEvidence }) {
  const navigate = useNavigate();
  const [imgFailed, setImgFailed] = useState(false);
  const thumb = det.id ? evidenceUrl(det.id) : null;
  const hasPlate = det.plate && det.plate !== "UNKNOWN";
  const hasLoc = det.lat != null && det.lng != null;
  const confidencePct = Number.isFinite(det.confidence) ? `${(det.confidence * 100).toFixed(1)}%` : null;

  return (
    <div
      style={{
        display: "flex",
        gap: 12,
        alignItems: "center",
        padding: "10px 14px",
        borderBottom: `1px solid ${C.border}`,
      }}
    >
      {/* Evidence image — the visual anchor of the card, not an afterthought. */}
      <div
        style={{
          width: 76,
          height: 76,
          borderRadius: 5,
          background: "#000",
          flexShrink: 0,
          overflow: "hidden",
          position: "relative",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          cursor: thumb ? "pointer" : "default",
        }}
        onClick={() => thumb && onViewEvidence?.(det)}
      >
        {thumb && !imgFailed ? (
          <img
            src={thumb}
            alt={`${det.cam} evidence`}
            onError={() => setImgFailed(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        ) : (
          <Car size={20} color={C.dim} />
        )}
        {isMockCamera(det.cam) && (
          <span style={{ position: "absolute", top: 2, left: 2, background: "rgba(0,0,0,0.7)", color: C.violet, fontSize: 7, fontWeight: 700, borderRadius: 2, padding: "0 3px" }}>
            MOCK
          </span>
        )}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
          <span
            style={{
              color: hasPlate ? C.text : C.muted,
              fontFamily: "monospace",
              fontSize: 14,
              fontWeight: 700,
            }}
          >
            {hasPlate ? det.plate : "UNKNOWN PLATE"}
          </span>
          {confidencePct && <span style={{ color: C.green, fontSize: 11, fontFamily: "monospace" }}>{confidencePct}</span>}
        </div>
        <div style={{ display: "flex", gap: 10, color: C.muted, fontSize: 10.5, marginTop: 3, flexWrap: "wrap", alignItems: "center" }}>
          <span>{det.vehicleType || "vehicle"}</span>
          <span style={{ color: C.accent, fontFamily: "monospace" }}>{det.cam}</span>
          {(det.locationDesc || det.camName) && (
            <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <MapPin size={10} /> {det.locationDesc || det.camName}
            </span>
          )}
          <span>{det.time}</span>
          {hasLoc && <span>{det.lat.toFixed(4)}, {det.lng.toFixed(4)}</span>}
        </div>
        <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
          {thumb && (
            <button onClick={() => onViewEvidence?.(det)} style={miniBtn(C.muted)}>
              View evidence
            </button>
          )}
          {hasPlate && (
            <button
              onClick={() => navigate(`/workspace?plate=${encodeURIComponent(det.plate)}`)}
              style={miniBtn(C.accent)}
            >
              <Crosshair size={10} /> Investigate
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

const miniBtn = (color) => ({
  display: "flex",
  alignItems: "center",
  gap: 4,
  background: "transparent",
  border: `1px solid ${color}`,
  color,
  borderRadius: 3,
  padding: "2px 8px",
  fontSize: 9.5,
  fontWeight: 600,
  cursor: "pointer",
});
