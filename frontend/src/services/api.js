import axios from "axios";
import {
  CAMERAS,
  INITIAL_ALERTS,
  MOCK_STATS,
  WATCHLIST_DETECTIONS,
} from "../lib/mockData.js";

// ─── Endpoints (DEVELOPER_README Isha §8 / §11) ──────────────────────────────
// Exact contract lives in docs/API_CONTRACTS.md on the `testing` branch, which
// is NOT present in this workspace. The normalisers below are tolerant to the
// most likely field spellings so that real payloads and the offline mock are
// interchangeable; tighten them once the contract file is available.
const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export const ENDPOINTS = {
  stats: "/dashboard/stats",
  cameras: "/cameras",
  recentAlerts: "/alerts/recent",
  acknowledge: (id) => `/alerts/${id}/acknowledge`,
};

export const http = axios.create({
  baseURL: API_BASE,
  timeout: 6000,
  headers: { "Content-Type": "application/json" },
});

// ─── Normalisers ────────────────────────────────────────────────────────────
const pick = (obj, keys, fallback) => {
  for (const k of keys) if (obj?.[k] !== undefined && obj[k] !== null) return obj[k];
  return fallback;
};

export function normalizeCamera(raw) {
  const lat = Number(pick(raw, ["lat", "latitude", "location_lat"], NaN));
  const lng = Number(pick(raw, ["lng", "lon", "longitude", "location_lng"], NaN));
  const coords = raw?.location?.coordinates; // GeoJSON [lng, lat]
  return {
    id: String(pick(raw, ["id", "camera_id", "cam_id"], "CAM-?")),
    name: pick(raw, ["name", "label", "location_name"], "Unnamed camera"),
    zone: pick(raw, ["zone", "sector", "area"], "—"),
    lat: Number.isFinite(lat) ? lat : Array.isArray(coords) ? coords[1] : null,
    lng: Number.isFinite(lng) ? lng : Array.isArray(coords) ? coords[0] : null,
    status: String(pick(raw, ["status", "state"], "active")).toLowerCase(),
    resolution: pick(raw, ["resolution", "stream_resolution"], "—"),
    fps: pick(raw, ["fps", "frame_rate"], "—"),
    protocol: String(pick(raw, ["protocol", "stream_protocol"], "RTSP")).toUpperCase(),
    streamUrl: pick(raw, ["stream_url", "hls_url", "webrtc_url", "rtsp_url"], null),
  };
}

export function normalizeAlert(raw) {
  return {
    id: pick(raw, ["id", "alert_id", "event_id"], `alert-${Date.now()}`),
    type: String(pick(raw, ["type", "alert_type", "category"], "ALERT")).toUpperCase(),
    cam: String(pick(raw, ["cam", "camera_id", "cam_id", "source"], "CAM-?")),
    vehicle: pick(raw, ["vehicle", "plate", "plate_number", "registration"], null),
    severity: String(pick(raw, ["severity", "priority", "level"], "medium")).toLowerCase(),
    msg: pick(raw, ["msg", "message", "description", "detail"], "Alert received"),
    time:
      pick(raw, ["time", "timestamp", "created_at"], null) != null
        ? formatTime(pick(raw, ["time", "timestamp", "created_at"], null))
        : new Date().toLocaleTimeString("en-IN", { hour12: false }),
    ack: Boolean(pick(raw, ["ack", "acknowledged", "is_acknowledged"], false)),
  };
}

function formatTime(value) {
  const d = new Date(value);
  if (!Number.isNaN(d.getTime())) return d.toLocaleTimeString("en-IN", { hour12: false });
  return String(value);
}

function normalizeStats(raw) {
  return {
    totalCameras: pick(raw, ["totalCameras", "total_cameras", "cameras_total"], MOCK_STATS.totalCameras),
    onlineFeeds: pick(raw, ["onlineFeeds", "online_feeds", "cameras_online"], MOCK_STATS.onlineFeeds),
    activeAlerts: pick(raw, ["activeAlerts", "active_alerts", "alerts_active"], MOCK_STATS.activeAlerts),
    todaysDetections: pick(raw, ["todaysDetections", "todays_detections", "detections_today"], MOCK_STATS.todaysDetections),
    anprReadsPerHour: pick(raw, ["anprReadsPerHour", "anpr_reads_per_hour"], MOCK_STATS.anprReadsPerHour),
    zonesOnline: pick(raw, ["zonesOnline", "zones_online"], MOCK_STATS.zonesOnline),
  };
}

// ─── Public API — every call degrades to mock data on failure ────────────────
async function safe(request, mock, label) {
  try {
    const { data } = await request();
    return { data, live: true, error: null };
  } catch (err) {
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.warn(`[api] ${label} unavailable, using mock fallback:`, err?.message || err);
    }
    return { data: mock, live: false, error: err };
  }
}

export async function fetchStats() {
  const res = await safe(() => http.get(ENDPOINTS.stats), MOCK_STATS, "stats");
  return { ...res, data: normalizeStats(res.data || {}) };
}

export async function fetchCameras() {
  const res = await safe(() => http.get(ENDPOINTS.cameras), CAMERAS, "cameras");
  const list = Array.isArray(res.data) ? res.data : res.data?.items || res.data?.cameras || [];
  return { ...res, data: list.map(normalizeCamera) };
}

export async function fetchRecentAlerts() {
  const res = await safe(() => http.get(ENDPOINTS.recentAlerts), INITIAL_ALERTS, "recent alerts");
  const list = Array.isArray(res.data) ? res.data : res.data?.items || res.data?.alerts || [];
  return { ...res, data: list.map(normalizeAlert) };
}

export async function fetchWatchlistDetections() {
  // No dedicated endpoint in Isha's contract — vehicle history is Vishakha's
  // domain. Derived client-side / mock only for the dashboard summary strip.
  return { data: WATCHLIST_DETECTIONS, live: false, error: null };
}

export async function acknowledgeAlert(id) {
  try {
    await http.post(ENDPOINTS.acknowledge(id));
    return { ok: true, live: true };
  } catch (err) {
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.warn("[api] acknowledge failed, updating UI optimistically:", err?.message || err);
    }
    return { ok: false, live: false, error: err };
  }
}
