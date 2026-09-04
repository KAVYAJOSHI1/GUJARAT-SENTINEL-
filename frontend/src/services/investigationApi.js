// ─── GIS / Vehicle-Investigation API layer (Vishakha) ───────────────────────
// Builds directly on Isha's existing API setup: it reuses the shared axios
// instance (`http`) from services/api.js — same baseURL (VITE_API_BASE_URL ||
// "/api/v1"), timeout, proxy and headers — so there is ONE API architecture,
// not two. Only the endpoints and response shapes below are Vishakha's domain
// (DEVELOPER_README §8 / §11, docs/API_CONTRACTS.md §1 & §4).
import { getToken, http, mapCameraStatus } from "./api.js";
import {
  CAMERA_GEOJSON,
  GIS_CAMERAS,
  MOCK_VEHICLE_SEARCH,
} from "../lib/mockGisData.js";
import { normalizePlate } from "../utils/plate.js";

export const INVESTIGATION_ENDPOINTS = {
  camerasGeoJSON: "/cameras/geojson",
  vehicleSearch: "/vehicles/search",
  evidence: (eventId) => `/vehicles/evidence/${encodeURIComponent(eventId)}`,
};

// Absolute URL for an evidence snapshot file, usable as an <img src>.
// <img> can't send an Authorization header, so the JWT rides as ?token=.
export function evidenceUrl(eventId) {
  const base = http.defaults.baseURL || "/api/v1";
  let url = `${base}${INVESTIGATION_ENDPOINTS.evidence(eventId)}`;
  const t = getToken();
  if (t) url += `?token=${encodeURIComponent(t)}`;
  return url;
}

// ─── helpers (same tolerant style as services/api.js) ────────────────────────
const pick = (obj, keys, fallback) => {
  for (const k of keys) if (obj?.[k] !== undefined && obj[k] !== null) return obj[k];
  return fallback;
};

async function safe(request, mock, label) {
  try {
    const { data } = await request();
    return { data, live: true, error: null };
  } catch (err) {
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.warn(`[investigationApi] ${label} unavailable, using mock fallback:`, err?.message || err);
    }
    return { data: mock, live: false, error: err };
  }
}

// ─── normalisers ────────────────────────────────────────────────────────────
export function normalizeGisCamera(raw) {
  // Accepts a GeoJSON Feature, a {location:{coordinates}} record, or a flat row.
  const props = raw?.properties || raw;
  const coords = raw?.geometry?.coordinates || raw?.location?.coordinates;
  const lat = Number(pick(props, ["lat", "latitude", "location_lat"], Array.isArray(coords) ? coords[1] : NaN));
  const lng = Number(pick(props, ["lng", "lon", "longitude", "location_lng"], Array.isArray(coords) ? coords[0] : NaN));
  return {
    // GeoJSON features carry the camera's external code in properties.code
    // (feature-level `id` is the backend UUID) — prefer the human code.
    id: String(pick(props, ["code", "camera_id", "cam_id"], pick(raw, ["id"], "CAM-?"))),
    uuid: pick(raw, ["id"], null),
    name: pick(props, ["name", "camera_name", "label", "location_name"], "Unnamed camera"),
    district: pick(props, ["district", "city", "zone", "area"], "—"),
    status: mapCameraStatus(pick(props, ["status", "state"], "offline")),
    lat: Number.isFinite(lat) ? lat : null,
    lng: Number.isFinite(lng) ? lng : null,
  };
}

export function normalizeSighting(raw) {
  const loc = raw?.location || {};
  const lat = Number(pick(raw, ["latitude", "lat"], pick(loc, ["latitude", "lat"], NaN)));
  const lng = Number(pick(raw, ["longitude", "lng", "lon"], pick(loc, ["longitude", "lng", "lon"], NaN)));
  const coords = loc?.coordinates; // GeoJSON [lng, lat]
  const eventId = String(pick(raw, ["event_id", "id", "eventId"], `EVT-${Math.random().toString(36).slice(2)}`));
  return {
    eventId,
    cameraId: String(pick(raw, ["camera_id", "cam_id", "cameraId"], "CAM-?")),
    cameraName: pick(raw, ["camera_name", "cameraName", "name"], "Unknown camera"),
    timestamp: pick(raw, ["timestamp", "time", "created_at", "detected_at"], null),
    lat: Number.isFinite(lat) ? lat : Array.isArray(coords) ? coords[1] : null,
    lng: Number.isFinite(lng) ? lng : Array.isArray(coords) ? coords[0] : null,
    snapshotUrl: pick(raw, ["evidence_snapshot_url", "snapshot_url", "evidence_url", "image_url"], "") || "",
    plateCropUrl: pick(raw, ["plate_crop_url", "plate_image_url", "crop_url"], "") || "",
    ocrConfidence: Number(pick(raw, ["ocr_confidence", "confidence", "ocrConfidence"], NaN)),
    vehicleType: pick(raw, ["vehicle_type", "vehicleType", "type"], null),
  };
}

export function normalizeVehicleSearch(raw, fallbackPlate = "") {
  const rawSightings = Array.isArray(raw?.sightings)
    ? raw.sightings
    : raw?.data?.sightings || raw?.results || [];
  const sightings = rawSightings
    .map(normalizeSighting)
    .filter((s) => Number.isFinite(s.lat) && Number.isFinite(s.lng))
    .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp)); // chronological ASC

  const summary = raw?.summary || {};
  const cameraCount =
    pick(summary, ["total_cameras", "camera_count"], null) ??
    new Set(sightings.map((s) => s.cameraId)).size;

  return {
    plate: normalizePlate(pick(raw, ["query_plate", "plate", "plate_number"], fallbackPlate)),
    totalSightings: pick(raw, ["total_sightings"], sightings.length),
    firstSeen: pick(summary, ["first_seen", "firstSeen"], sightings[0]?.timestamp || null),
    lastSeen: pick(summary, ["last_seen", "lastSeen"], sightings[sightings.length - 1]?.timestamp || null),
    cameraCount,
    watchlistHit: Boolean(pick(summary, ["has_active_watchlist_hit", "watchlist_hit", "is_watchlisted"], false)),
    sightings,
  };
}

// ─── public API — degrades to mock on failure (mirrors services/api.js) ──────
export async function fetchCamerasGeoJSON() {
  const res = await safe(
    () => http.get(INVESTIGATION_ENDPOINTS.camerasGeoJSON),
    CAMERA_GEOJSON,
    "cameras/geojson"
  );
  const d = res.data;
  const list = Array.isArray(d?.features)
    ? d.features
    : Array.isArray(d)
    ? d
    : d?.items || d?.cameras || [];
  const cameras = list.map(normalizeGisCamera).filter((c) => c.lat != null && c.lng != null);
  return { ...res, data: cameras.length ? cameras : GIS_CAMERAS };
}

export async function searchVehicle(plate, { from, to } = {}) {
  const normalized = normalizePlate(plate);
  const params = { plate: normalized };
  if (from) params.from = from;
  if (to) params.to = to;
  const res = await safe(
    () => http.get(INVESTIGATION_ENDPOINTS.vehicleSearch, { params }),
    MOCK_VEHICLE_SEARCH,
    `vehicles/search ${normalized}`
  );
  return { ...res, data: normalizeVehicleSearch(res.data || {}, normalized) };
}

export async function fetchEvidence(eventId) {
  // The evidence endpoint serves a snapshot file (DEVELOPER_README §8). We only
  // need a resolvable URL; the modal handles load errors with a placeholder.
  return { url: evidenceUrl(eventId), live: null, error: null };
}
