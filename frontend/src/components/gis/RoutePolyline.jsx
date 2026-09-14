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

export default function RoutePolyline({ sightings = [], fit = true, activeId = null, onSelect }) {
  const map = useMap();

  useEffect(() => {
    const points = [...sightings]
      .filter((s) => Number.isFinite(s.lat) && Number.isFinite(s.lng))
      .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

    if (points.length === 0) return undefined;

    const latlngs = points.map((s) => [s.lat, s.lng]);
    const layer = L.layerGroup();

    let rafId = null;
    if (latlngs.length >= 2) {
      // Dashed + animated offset ("marching ants") so a reconstructed
      // journey visibly travels along the route rather than sitting as a
      // static line — the same beat as the pitch video's hero scene.
      const line = L.polyline(latlngs, { color: ACCENT, weight: 3, opacity: 0.9, dashArray: "10 8" });
      layer.addLayer(line);

      let offset = 0;
      const animate = () => {
        offset = (offset - 0.6 + 18) % 18;
        line.setStyle({ dashOffset: String(offset) });
        rafId = requestAnimationFrame(animate);
      };
      rafId = requestAnimationFrame(animate);

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
      const isActive = s.eventId === activeId;
      const cls = [i === 0 ? "is-start" : i === points.length - 1 ? "is-end" : "", isActive ? "is-journey-active" : ""]
        .filter(Boolean)
        .join(" ");
      const marker = L.marker([s.lat, s.lng], {
        icon: L.divIcon({
          className: "",
          html: `<div class="gis-seq-marker ${cls}">${i + 1}</div>`,
          iconSize: isActive ? [28, 28] : [22, 22],
          iconAnchor: isActive ? [14, 14] : [11, 11],
        }),
        zIndexOffset: isActive ? 2000 : 1000,
      });
      const t = s.timestamp ? new Date(s.timestamp).toLocaleString("en-IN", { hour12: false }) : "—";
      marker.bindTooltip(`<strong>#${i + 1} · ${s.cameraName}</strong><br/>${t}`, {
        direction: "top",
        offset: [0, -12],
      });
      // Journey task §6: clicking a map marker mirrors clicking its timeline
      // row -- same selection state drives both (see InvestigationPage).
      if (onSelect) {
        marker.on("click", () => onSelect(s));
      }
      layer.addLayer(marker);
    });

    layer.addTo(map);

    return () => {
      if (rafId != null) cancelAnimationFrame(rafId);
      map.removeLayer(layer);
    };
    // Deliberately NOT keyed on `sightings` (a fresh array/object each render
    // would tear down + rebuild every marker on every parent re-render) --
    // keyed on the values that actually change what gets drawn.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, JSON.stringify(sightings.map((s) => [s.eventId, s.lat, s.lng, s.cameraName, s.timestamp])), activeId, onSelect]);

  // Fit-to-bounds runs only when the underlying sighting SET changes, not on
  // every marker selection -- otherwise clicking a sighting during playback
  // would fight the "fly to this marker" pan with a full re-zoom-to-fit-all.
  useEffect(() => {
    if (!fit) return;
    const latlngs = sightings
      .filter((s) => Number.isFinite(s.lat) && Number.isFinite(s.lng))
      .map((s) => [s.lat, s.lng]);
    if (latlngs.length === 0) return;
    map.fitBounds(L.latLngBounds(latlngs), { padding: [48, 48], maxZoom: 14 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, JSON.stringify(sightings.map((s) => [s.eventId, s.lat, s.lng])), fit]);

  return null;
}
