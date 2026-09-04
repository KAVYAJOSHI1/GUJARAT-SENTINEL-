import { useEffect } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet-polylinedecorator";

// Route Trajectory Vector Overlay (DEVELOPER_README §14.7):
// a polyline connecting camera coordinates in chronological order with
// directional arrowheads, plus numbered sequence markers. Sightings are
// assumed already sorted ASC by the normaliser, but we sort again defensively
// so out-of-order input still maps correctly (§16).
const ACCENT = "#4f9cd9";

// Compass bearing (deg) from point a → b, for the fallback arrow icons.
function bearing([lat1, lon1], [lat2, lon2]) {
  const toRad = (d) => (d * Math.PI) / 180;
  const y = Math.sin(toRad(lon2 - lon1)) * Math.cos(toRad(lat2));
  const x =
    Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) -
    Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(toRad(lon2 - lon1));
  return (Math.atan2(y, x) * 180) / Math.PI;
}

export default function RoutePolyline({ sightings = [], fit = true }) {
  const map = useMap();

  useEffect(() => {
    const points = [...sightings]
      .filter((s) => Number.isFinite(s.lat) && Number.isFinite(s.lng))
      .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

    if (points.length === 0) return undefined;

    const latlngs = points.map((s) => [s.lat, s.lng]);
    const layer = L.layerGroup();

    if (latlngs.length >= 2) {
      const line = L.polyline(latlngs, { color: ACCENT, weight: 3, opacity: 0.9 });
      layer.addLayer(line);

      // Preferred: leaflet-polylinedecorator arrowheads along the path.
      const hasDecorator = typeof L.polylineDecorator === "function" && L.Symbol?.arrowHead;
      if (hasDecorator) {
        layer.addLayer(
          L.polylineDecorator(line, {
            patterns: [
              {
                offset: 20,
                repeat: 70,
                symbol: L.Symbol.arrowHead({
                  pixelSize: 12,
                  polygon: false,
                  pathOptions: { stroke: true, color: ACCENT, weight: 3, opacity: 0.95 },
                }),
              },
            ],
          })
        );
      } else {
        // Fallback: a rotated chevron divIcon at each segment midpoint.
        for (let i = 0; i < latlngs.length - 1; i += 1) {
          const a = latlngs[i];
          const b = latlngs[i + 1];
          const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
          const deg = bearing(a, b);
          layer.addLayer(
            L.marker(mid, {
              interactive: false,
              icon: L.divIcon({
                className: "",
                html: `<div style="transform:rotate(${deg}deg);color:${ACCENT};font-size:16px;line-height:1;font-weight:700">➤</div>`,
                iconSize: [16, 16],
                iconAnchor: [8, 8],
              }),
            })
          );
        }
      }
    }

    points.forEach((s, i) => {
      const cls = i === 0 ? "is-start" : i === points.length - 1 ? "is-end" : "";
      const marker = L.marker([s.lat, s.lng], {
        icon: L.divIcon({
          className: "",
          html: `<div class="gis-seq-marker ${cls}">${i + 1}</div>`,
          iconSize: [22, 22],
          iconAnchor: [11, 11],
        }),
        zIndexOffset: 1000,
      });
      const t = s.timestamp ? new Date(s.timestamp).toLocaleString("en-IN", { hour12: false }) : "—";
      marker.bindTooltip(`<strong>#${i + 1} · ${s.cameraName}</strong><br/>${t}`, {
        direction: "top",
        offset: [0, -12],
      });
      layer.addLayer(marker);
    });

    layer.addTo(map);

    if (fit) {
      map.fitBounds(L.latLngBounds(latlngs), { padding: [48, 48], maxZoom: 14 });
    }

    return () => {
      map.removeLayer(layer);
    };
  }, [map, sightings, fit]);

  return null;
}
