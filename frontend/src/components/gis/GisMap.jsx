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
        {/* CartoDB "Dark Matter" basemap (DEVELOPER_README §6). Served from
            CARTO's Fastly CDN host: byte-identical tiles to
            {s}.basemaps.cartocdn.com but without the "API KEY REQUIRED"
            watermark CARTO now overlays on unauthenticated use of that host.
            No key, no sign-up. */}
        <TileLayer
          url="https://cartodb-basemaps-{s}.global.ssl.fastly.net/dark_all/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          subdomains="abcd"
          detectRetina={false}
          maxZoom={19}
        />
        <MapViewController focus={focus} />
        {children}
      </MapContainer>
    </div>
  );
}
