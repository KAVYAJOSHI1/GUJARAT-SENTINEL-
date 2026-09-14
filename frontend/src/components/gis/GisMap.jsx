import { useEffect } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "../../styles/gis.css";
import { GUJARAT_CENTER, GUJARAT_ZOOM } from "../../lib/mockGisData.js";

// Imperatively re-centres the (already-mounted) map when `focus` changes.
// react-leaflet treats <MapContainer center/zoom> as mount-only, so this is
// how the console pans to a specific camera after load (/investigation?cam=<id>).
function MapViewController({ focus }) {
  const map = useMap();
  useEffect(() => {
    if (!focus || focus.lat == null || focus.lng == null) return;
    map.flyTo([focus.lat, focus.lng], focus.zoom ?? map.getZoom(), { duration: 0.8 });
  }, [map, focus?.lat, focus?.lng, focus?.zoom]);
  return null;
}

// Base Leaflet map for the GIS subsystem (DEVELOPER_README §14.3):
// CartoDB Dark Matter tiles, centred on Gujarat, with zoom controls.
// Consumers drop <CameraMarker> / <RoutePolyline> in as children.
// `focus` = { lat, lng, zoom } pans the map there imperatively after mount.
export default function GisMap({
  center = GUJARAT_CENTER,
  zoom = GUJARAT_ZOOM,
  height = 420,
  focus = null,
  children,
  style,
}) {
  return (
    <div className="gis-map" style={{ height, width: "100%", borderRadius: 8, overflow: "hidden", ...style }}>
      <MapContainer
        center={center}
        zoom={zoom}
        scrollWheelZoom
        preferCanvas
        style={{ height: "100%", width: "100%" }}
      >
        {/* Esri's public dark-canvas basemap REST tiles (no key, no sign-up,
            no per-origin restriction). Previously this used CARTO's Fastly
            CDN mirror to dodge their "API KEY REQUIRED" overlay on
            unauthenticated dark_all tiles -- CARTO has since started
            enforcing that watermark on the mirror too, so every tile was
            rendering with "API KEY REQUIRED" stamped across it. Esri's
            Canvas/World_Dark_Gray_* services are genuinely free for this
            volume of use and don't depend on an unofficial CDN quirk.
            Two layers stacked per Esri's own usage pattern: unlabeled base
            + a reference layer carrying labels/roads on top. */}
        <TileLayer
          url="https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
          attribution="Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors, and the GIS User Community"
          maxZoom={16}
        />
        <TileLayer
          url="https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
          maxZoom={16}
        />
        <MapViewController focus={focus} />
        {children}
      </MapContainer>
    </div>
  );
}
