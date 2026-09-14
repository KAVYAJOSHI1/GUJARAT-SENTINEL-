import { useMemo } from "react";
import L from "leaflet";
import { Marker, Popup, Tooltip } from "react-leaflet";
import { isMockCamera } from "../../services/api.js";

// PostGIS camera pin rendered as a coloured status dot (DEVELOPER_README §14.4).
// A divIcon is used so there are no Leaflet image-asset paths to wire up and the
// marker inherits the command-center palette from styles/gis.css.
//
//  highlighted → spotlight target marker + a permanent name label, for the
//                camera the console was opened on (/investigation?cam=<id>).
//  dim         → smaller, faded pin: context markers around a highlighted one.
const STATUS_LABEL = {
  active: "Online",
  alert: "Alert",
  offline: "Offline",
};

const statusClass = (status) =>
  status === "alert" ? "is-alert" : status === "offline" ? "is-offline" : "is-active";

// Small camera glyph (currentColor, inherits the marker's ring color) so a
// pin reads as "a camera" at a glance instead of an unlabeled colored dot.
const CAMERA_GLYPH =
  '<svg viewBox="0 0 24 24" fill="none" width="60%" height="60%"><rect x="2" y="7" width="14" height="11" rx="2.5" stroke="currentColor" stroke-width="2.4"/><path d="M16 10.5L22 7v10l-6-3.5" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round"/></svg>';

export function makeIcon(status, dim, mock) {
  const size = dim ? 14 : 20;
  const alertPulse = status === "alert" && !dim ? '<span class="gis-cam-pulse"></span>' : "";
  return L.divIcon({
    className: "",
    html: `<div class="gis-cam-marker ${statusClass(status)}${dim ? " is-dim" : ""}${mock ? " is-mock" : ""}">${alertPulse}${CAMERA_GLYPH}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -10],
  });
}

function makeFocusIcon(status) {
  return L.divIcon({
    className: "",
    html: `<div class="gis-cam-focus"><span class="gis-cam-focus-ring"></span><span class="gis-cam-focus-core ${statusClass(status)}"></span></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
    popupAnchor: [0, -12],
  });
}

export default function CameraMarker({ camera, onOpen, highlighted = false, dim = false }) {
  const { id, name, district, status, lat, lng } = camera;
  const mock = isMockCamera(id);
  const icon = useMemo(
    () => (highlighted ? makeFocusIcon(status) : makeIcon(status, dim, mock)),
    [highlighted, dim, status, mock]
  );

  if (lat == null || lng == null) return null;

  return (
    <Marker position={[lat, lng]} icon={icon} zIndexOffset={highlighted ? 1000 : 0}>
      {highlighted && (
        <Tooltip permanent direction="top" offset={[0, -12]} className="gis-focus-label">
          {id} — {name}
        </Tooltip>
      )}
      <Popup>
        <div style={{ minWidth: 168 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
            <span style={{ fontWeight: 700, color: "#4f9cd9" }}>
              {id} — {name}
            </span>
            {mock && (
              <span style={{ background: "#9b8cee", color: "#0b0f14", borderRadius: 3, padding: "0 5px", fontSize: 9, fontWeight: 700, letterSpacing: 0.6 }}>
                MOCK
              </span>
            )}
            {highlighted && (
              <span
                style={{
                  background: "#4f9cd9",
                  color: "#0b0f14",
                  borderRadius: 3,
                  padding: "0 5px",
                  fontSize: 9,
                  fontWeight: 700,
                  letterSpacing: 0.6,
                }}
              >
                SELECTED
              </span>
            )}
          </div>
          <div style={{ color: "#8993a1" }}>{district}</div>
          <div style={{ marginTop: 4 }}>
            Status: <strong>{STATUS_LABEL[status] || status}</strong>
          </div>
          <div style={{ color: "#8993a1", fontFamily: "monospace", fontSize: 11, marginTop: 2 }}>
            {lat.toFixed(5)}, {lng.toFixed(5)}
          </div>
          {onOpen && (
            <button
              onClick={() => onOpen(camera)}
              style={{
                marginTop: 8,
                width: "100%",
                background: "#1f2530",
                border: "1px solid #4f9cd9",
                color: "#4f9cd9",
                borderRadius: 4,
                padding: "4px 8px",
                fontSize: 11,
                cursor: "pointer",
              }}
            >
              Investigate at this camera
            </button>
          )}
        </div>
      </Popup>
    </Marker>
  );
}
