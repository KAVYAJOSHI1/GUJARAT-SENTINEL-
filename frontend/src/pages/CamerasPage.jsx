import { useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { C } from "../theme.js";
import CameraGrid from "../components/CameraGrid.jsx";
import CameraModal from "../components/CameraModal.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";

const SOURCE_FILTERS = ["ALL", "REAL", "MOCK"];

export default function CamerasPage() {
  const { cameras, loading, backendLive, retrying, reload, latestDetectionByCamera, detectionCountByCamera } =
    useOutletContext();
  const [selectedCam, setSelectedCam] = useState(null);
  const [zone, setZone] = useState("All");
  const [source, setSource] = useState("ALL");

  const zones = useMemo(
    () => ["All", ...Array.from(new Set(cameras.map((c) => c.zone))).sort()],
    [cameras]
  );

  const bySource = source === "ALL" ? cameras : cameras.filter((c) => (source === "MOCK" ? c.isMock : !c.isMock));
  const visible = zone === "All" ? bySource : bySource.filter((c) => c.zone === zone);

  const counts = {
    active: cameras.filter((c) => c.status === "active").length,
    alert: cameras.filter((c) => c.status === "alert").length,
    offline: cameras.filter((c) => c.status === "offline").length,
  };
  const hasMock = cameras.some((c) => c.isMock);

  return (
    <div>
      {!backendLive && (
        <ErrorBanner message="Backend connection lost — showing simulated data. Retrying…" onRetry={reload} retrying={retrying} />
      )}

      <div style={{ marginBottom: 14, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div style={{ fontWeight: 600 }}>Camera Network — {visible.length} feeds</div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          {hasMock && (
            <>
              {SOURCE_FILTERS.map((s) => (
                <button
                  key={s}
                  onClick={() => setSource(s)}
                  style={{
                    background: s === source ? C.accentGlow : "transparent",
                    border: `1px solid ${s === source ? C.accent : C.border}`,
                    color: s === source ? C.accent : C.muted,
                    borderRadius: 4,
                    padding: "4px 12px",
                    fontSize: 11,
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                >
                  {s}
                </button>
              ))}
              <span style={{ width: 1, height: 16, background: C.border }} />
            </>
          )}
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
          ["Online", C.green, counts.active],
          ["Incident", C.amber, counts.alert],
          ["Offline", C.red, counts.offline],
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
        detectionCountByCamera={detectionCountByCamera}
      />

      <CameraModal cam={selectedCam} onClose={() => setSelectedCam(null)} />
    </div>
  );
}
