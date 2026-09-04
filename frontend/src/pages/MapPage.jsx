import { useEffect, useMemo, useState } from "react";
import { useNavigate, useOutletContext, useSearchParams } from "react-router-dom";
import { MapPinned } from "lucide-react";
import { C } from "../theme.js";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import GisMap from "../components/gis/GisMap.jsx";
import CameraMarker from "../components/gis/CameraMarker.jsx";
import { fetchCamerasGeoJSON } from "../services/investigationApi.js";
import { CITY_ZOOM, GUJARAT_CENTER, GUJARAT_ZOOM } from "../lib/mockGisData.js";

// Standalone Interactive GIS Map (`/map`, DEVELOPER_README §4.1). Renders inside
// Isha's AppLayout (header/footer/nav preserved) — full-bleed dark Leaflet map
// with every PostGIS camera pin. Clicking a pin routes into the investigation
// console with that camera's context.
export default function MapPage() {
  const { cameras: layoutCameras = [], backendLive } = useOutletContext() || {};
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const camParam = params.get("cam");

  const [cameras, setCameras] = useState([]);
  const [live, setLive] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchCamerasGeoJSON().then((res) => {
      if (cancelled) return;
      setLive(res.live);
      if (res.data?.length) setCameras(res.data);
      else if (layoutCameras.length) setCameras(layoutCameras);
    });
    return () => {
      cancelled = true;
    };
  }, [layoutCameras]);

  const focus = useMemo(
    () => (camParam ? cameras.find((c) => c.id === camParam) : null),
    [camParam, cameras]
  );

  const counts = useMemo(
    () => ({
      total: cameras.length,
      alert: cameras.filter((c) => c.status === "alert").length,
      offline: cameras.filter((c) => c.status === "offline").length,
    }),
    [cameras]
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {!backendLive && <ErrorBanner message="Backend connection lost — map running on simulated camera inventory." />}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700, fontSize: 15 }}>
          <MapPinned size={16} color={C.accent} /> GIS Camera Map
        </div>
        <div style={{ display: "flex", gap: 14, fontSize: 12, color: C.muted }}>
          <span>{counts.total} cameras</span>
          <span style={{ color: C.red }}>{counts.alert} in alert</span>
          <span>{counts.offline} offline</span>
          {live === false && <span style={{ color: C.amber }}>simulated</span>}
        </div>
      </div>

      <GisMap
        center={focus ? [focus.lat, focus.lng] : GUJARAT_CENTER}
        zoom={focus ? CITY_ZOOM : GUJARAT_ZOOM}
        height="calc(100vh - 200px)"
      >
        {cameras.map((cam) => (
          <CameraMarker
            key={cam.id}
            camera={cam}
            onOpen={(c) => navigate(`/investigation?cam=${encodeURIComponent(c.id)}`)}
          />
        ))}
      </GisMap>
    </div>
  );
}
