import { useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { C } from "../theme.js";
import CameraGrid from "../components/CameraGrid.jsx";
import CameraModal from "../components/CameraModal.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";

export default function CamerasPage() {
  const { cameras, loading, backendLive, retrying, reload, latestDetectionByCamera } = useOutletContext();
  const [selectedCam, setSelectedCam] = useState(null);
  const [zone, setZone] = useState("All");

  const zones = useMemo(
    () => ["All", ...Array.from(new Set(cameras.map((c) => c.zone))).sort()],
    [cameras]
  );

  const visible = zone === "All" ? cameras : cameras.filter((c) => c.zone === zone);

  const counts = {
    active: cameras.filter((c) => c.status === "active").length,
    alert: cameras.filter((c) => c.status === "alert").length,
    offline: cameras.filter((c) => c.status === "offline").length,
  };

  return (
    <div>
      {!backendLive && (
        <ErrorBanner message="Backend connection lost — showing simulated data. Retrying…" onRetry={reload} retrying={retrying} />
      )}

      <div style={{ marginBottom: 14, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div style={{ fontWeight: 600 }}>Camera Network — {cameras.length} feeds</div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {zones.map((z) => (
            <button
              key={z}
              onClick={() => setZone(z)}
              style={{
                background: z === zone ? C.accentGlow : "transparent",
                border: `1px solid ${z === zone ? C.accent : C.border}`,
                color: z === zone ? C.accent : C.muted,
                borderRadius: 4,
                padding: "4px 12px",
                fontSize: 11,
                cursor: "pointer",
              }}
            >
              {z}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", gap: 16, marginBottom: 14, flexWrap: "wrap" }}>
        {[
          ["Active", C.green, counts.active],
          ["Alert", C.red, counts.alert],
          ["Offline", C.muted, counts.offline],
        ].map(([l, c, n]) => (
          <div key={l} style={{ display: "flex", alignItems: "center", gap: 6, color: C.muted, fontSize: 12 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: c, display: "inline-block" }} />
            {l} ({n})
          </div>
        ))}
      </div>

      <CameraGrid
        cameras={visible}
        columns={4}
        loading={loading}
        skeletonCount={8}
        selectedId={selectedCam?.id}
        onSelect={setSelectedCam}
        detectionsByCamera={latestDetectionByCamera}
      />

      <CameraModal cam={selectedCam} onClose={() => setSelectedCam(null)} />
    </div>
  );
}
