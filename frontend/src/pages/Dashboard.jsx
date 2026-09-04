import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Activity, BellRing, Car, PanelRightOpen, ScanLine, Video } from "lucide-react";
import { C } from "../theme.js";
import StatCard from "../components/StatCard.jsx";
import CameraGrid from "../components/CameraGrid.jsx";
import CameraModal from "../components/CameraModal.jsx";
import AlertFeed from "../components/AlertFeed.jsx";
import AlertDrawer from "../components/AlertDrawer.jsx";
import DetectionFeed from "../components/DetectionFeed.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";

export default function Dashboard() {
  const {
    stats,
    cameras,
    alerts,
    detections,
    latestDetectionByCamera,
    loading,
    backendLive,
    retrying,
    critCount,
    reload,
    ackAlert,
    ackAll,
  } = useOutletContext();

  const [selectedCam, setSelectedCam] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const onlineFeeds = stats?.onlineFeeds ?? cameras.filter((c) => c.status !== "offline").length;
  const activeAlerts = alerts.filter((a) => !a.ack).length;

  return (
    <div>
      {!backendLive && (
        <ErrorBanner
          message="Backend connection lost — showing simulated data. Retrying…"
          onRetry={reload}
          retrying={retrying}
        />
      )}

      <div className="stat-row" style={{ marginBottom: 20 }}>
        <StatCard label="Total Cameras" value={stats?.totalCameras ?? cameras.length} sub="Registered feeds" icon={Video} color={C.accent} loading={loading} />
        <StatCard label="Online Feeds" value={onlineFeeds} sub={`${cameras.filter((c) => c.status === "alert").length} in alert`} icon={Activity} color={C.green} loading={loading} />
        <StatCard label="Active Alerts" value={activeAlerts} sub="Requires attention" icon={BellRing} color={activeAlerts > 0 ? C.red : C.green} pulse={activeAlerts > 0} loading={loading} />
        <StatCard label="Today's Detections" value={(stats?.todaysDetections ?? 0).toLocaleString("en-IN")} sub="ANPR + analytics" icon={ScanLine} color={C.amber} loading={loading} />
        <StatCard label="Watchlist Hits" value={detections.length} sub="This shift" icon={Car} color={C.violet} loading={loading} />
      </div>

      <div className="overview-grid">
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" }}>
          <div
            style={{
              padding: "12px 16px",
              borderBottom: `1px solid ${C.border}`,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span style={{ fontWeight: 600, fontSize: 13 }}>Live Camera Grid</span>
            <span style={{ color: C.muted, fontSize: 11 }}>{cameras.length} feeds</span>
          </div>
          <div style={{ padding: 12 }}>
            <CameraGrid
              cameras={cameras}
              columns={3}
              loading={loading}
              selectedId={selectedCam?.id}
              onSelect={setSelectedCam}
              detectionsByCamera={latestDetectionByCamera}
            />
          </div>
        </div>

        <div
          style={{
            background: C.surface,
            border: `1px solid ${C.border}`,
            borderRadius: 8,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ padding: "8px 12px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "flex-end" }}>
            <button
              onClick={() => setDrawerOpen(true)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                background: "transparent",
                border: `1px solid ${C.border}`,
                color: C.muted,
                borderRadius: 4,
                padding: "3px 10px",
                fontSize: 10,
                cursor: "pointer",
              }}
            >
              <PanelRightOpen size={12} /> Open drawer
            </button>
          </div>
          <div style={{ flex: 1, minHeight: 0 }}>
            <AlertFeed
              alerts={alerts}
              loading={loading}
              critCount={critCount}
              onAck={ackAlert}
              onAckAll={ackAll}
              maxHeight={520}
            />
          </div>
        </div>
      </div>

      <div
        style={{
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: 8,
          overflow: "hidden",
          marginTop: 16,
        }}
      >
        <DetectionFeed detections={detections} loading={loading} maxHeight={360} />
      </div>

      <CameraModal cam={selectedCam} onClose={() => setSelectedCam(null)} />
      <AlertDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        alerts={alerts}
        loading={loading}
        critCount={critCount}
        onAck={ackAlert}
        onAckAll={ackAll}
      />
    </div>
  );
}
