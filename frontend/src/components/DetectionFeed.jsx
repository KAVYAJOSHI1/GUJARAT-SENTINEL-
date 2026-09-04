import { useState } from "react";
import { ScanLine } from "lucide-react";
import { C } from "../theme.js";
import DetectionRow from "./DetectionRow.jsx";
import EmptyState from "./ui/EmptyState.jsx";
import { SkeletonRows } from "./ui/Skeleton.jsx";
import EvidenceModal from "./gis/EvidenceModal.jsx";

function detectionToSighting(det) {
  if (!det) return null;
  return {
    eventId: det.id,
    cameraId: det.cam,
    cameraName: det.camName || det.cam,
    timestamp: det.ts || det.time,
    lat: det.lat,
    lng: det.lng,
    snapshotUrl: det.snapshotUrl || null,
    plateCropUrl: null,
    ocrConfidence: det.confidence,
    vehicleType: det.vehicleType,
  };
}

// Live feed of consolidated AI detection events (one row per completed
// camera+track, not one per frame — the backend already de-duplicates this).
// This is the panel that makes the pipeline visible end to end: camera ->
// vehicle detection -> ByteTrack -> AI event -> backend, shown as it happens.
export default function DetectionFeed({ detections = [], loading = false, maxHeight = 420 }) {
  const [viewing, setViewing] = useState(null);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <div
        style={{
          padding: "12px 16px",
          borderBottom: `1px solid ${C.border}`,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexShrink: 0,
        }}
      >
        <span style={{ fontWeight: 600, fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
          <ScanLine size={13} color={C.accent} /> Live AI Detections
        </span>
        <span style={{ color: C.muted, fontSize: 11 }}>{detections.length} recent</span>
      </div>

      <div style={{ overflowY: "auto", flex: 1, maxHeight }}>
        {loading ? (
          <div style={{ padding: "8px 14px" }}>
            <SkeletonRows rows={5} height={44} />
          </div>
        ) : detections.length === 0 ? (
          <EmptyState
            icon={ScanLine}
            title="No detections yet"
            hint="Start the ingestion pipeline against a Sentinel camera to see live events here."
          />
        ) : (
          detections.map((d) => <DetectionRow key={d.id} det={d} onViewEvidence={setViewing} />)
        )}
      </div>

      <EvidenceModal
        sighting={detectionToSighting(viewing)}
        plate={viewing?.plate && viewing.plate !== "UNKNOWN" ? viewing.plate : "UNKNOWN PLATE"}
        onClose={() => setViewing(null)}
      />
    </div>
  );
}
