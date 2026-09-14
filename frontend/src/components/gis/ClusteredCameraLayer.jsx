import { useEffect } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import "leaflet.markercluster";
import { makeIcon } from "./CameraMarker.jsx";
import { isMockCamera } from "../../services/api.js";

const STATUS_LABEL = { active: "Online", alert: "Alert", offline: "Offline" };

// Imperative Leaflet layer (same pattern as RoutePolyline.jsx) rather than a
// declarative <Marker> tree: leaflet.markercluster is a plain Leaflet plugin
// with no react-leaflet binding compatible with this project's React-Leaflet
// v4 / React 18 pin, so cameras are added straight onto a real
// L.markerClusterGroup instead of pulling in a second clustering package
// with its own (incompatible) React 19 peer dependency.
//
// `excludeId` skips one camera (the console's current spotlight/focus target,
// rendered separately via <CameraMarker highlighted>) so it never gets
// swallowed into a cluster bubble.
export default function ClusteredCameraLayer({ cameras = [], onOpen, excludeId = null }) {
  const map = useMap();

  useEffect(() => {
    const group = L.markerClusterGroup({
      maxClusterRadius: 46,
      spiderfyOnMaxZoom: true,
      iconCreateFunction: (cluster) => {
        const children = cluster.getAllChildMarkers();
        const cls = children.some((m) => m.options.camStatus === "offline")
          ? "has-offline"
          : children.some((m) => m.options.camStatus === "alert")
          ? "has-alert"
          : "";
        const size = children.length >= 10 ? 40 : children.length >= 5 ? 34 : 28;
        return L.divIcon({
          className: "",
          html: `<div class="gis-cluster ${cls}">${children.length}</div>`,
          iconSize: [size, size],
        });
      },
    });

    cameras
      .filter((cam) => cam.id !== excludeId && cam.lat != null && cam.lng != null)
      .forEach((cam) => {
        const mock = isMockCamera(cam.id);
        const marker = L.marker([cam.lat, cam.lng], {
          icon: makeIcon(cam.status, false, mock),
          camStatus: cam.status,
        });
        marker.bindPopup(`
          <div style="min-width:168px">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:2px">
              <span style="font-weight:700;color:#4f9cd9">${cam.id} — ${cam.name}</span>
              ${mock ? '<span style="background:#9b8cee;color:#0b0f14;border-radius:3px;padding:0 5px;font-size:9px;font-weight:700;letter-spacing:.6px">MOCK</span>' : ""}
            </div>
            <div style="color:#8993a1">${cam.district || cam.zone || ""}</div>
            <div style="margin-top:4px">Status: <strong>${STATUS_LABEL[cam.status] || cam.status}</strong></div>
            <div style="color:#8993a1;font-family:monospace;font-size:11px;margin-top:2px">${cam.lat.toFixed(5)}, ${cam.lng.toFixed(5)}</div>
            ${onOpen ? '<button class="gis-cluster-investigate" style="margin-top:8px;width:100%;background:#1f2530;border:1px solid #4f9cd9;color:#4f9cd9;border-radius:4px;padding:4px 8px;font-size:11px;cursor:pointer">Investigate at this camera</button>' : ""}
          </div>
        `);
        if (onOpen) {
          marker.on("popupopen", (e) => {
            e.popup.getElement()?.querySelector(".gis-cluster-investigate")?.addEventListener("click", () => onOpen(cam));
          });
        }
        group.addLayer(marker);
      });

    group.addTo(map);
    return () => map.removeLayer(group);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, JSON.stringify(cameras.map((c) => [c.id, c.status, c.lat, c.lng])), excludeId, onOpen]);

  return null;
}
