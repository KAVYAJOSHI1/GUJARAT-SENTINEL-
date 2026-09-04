import { useState } from "react";
import { Car } from "lucide-react";
import { C } from "../theme.js";
import { evidenceUrl } from "../services/api.js";

// One real AI detection event: camera, vehicle type, track ID, timestamp,
// location and (when readable) plate — with the actual evidence frame pulled
// from the live pipeline. UNKNOWN is shown as-is, never invented.
export default function DetectionRow({ det }) {
  const [imgFailed, setImgFailed] = useState(false);
  const thumb = det.id ? evidenceUrl(det.id) : null;
  const hasPlate = det.plate && det.plate !== "UNKNOWN";
  const hasLoc = det.lat != null && det.lng != null;

  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        alignItems: "center",
        padding: "8px 14px",
        borderBottom: `1px solid ${C.border}`,
      }}
    >
      <div
        style={{
          width: 44,
          height: 44,
          borderRadius: 4,
          background: "#000",
          flexShrink: 0,
          overflow: "hidden",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {thumb && !imgFailed ? (
          <img
            src={thumb}
            alt={`${det.cam} evidence`}
            onError={() => setImgFailed(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        ) : (
          <Car size={16} color={C.dim} />
        )}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
          <span style={{ color: C.accent, fontFamily: "monospace", fontSize: 11, fontWeight: 700 }}>
            {det.cam}
          </span>
          <span style={{ color: C.text, fontSize: 12 }}>{det.camName || ""}</span>
          <span
            style={{
              color: hasPlate ? C.text : C.muted,
              fontFamily: "monospace",
              fontSize: 12,
              fontWeight: hasPlate ? 700 : 400,
            }}
          >
            {det.plate}
          </span>
        </div>
        <div style={{ display: "flex", gap: 10, color: C.muted, fontSize: 10.5, marginTop: 2, flexWrap: "wrap" }}>
          <span>{det.vehicleType || "vehicle"}</span>
          <span>track #{det.trackId ?? "—"}</span>
          <span>{det.time}</span>
          {hasLoc && <span>{det.lat.toFixed(4)}, {det.lng.toFixed(4)}</span>}
        </div>
      </div>
    </div>
  );
}
