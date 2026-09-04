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
  login: "/auth/login",
  stats: "/dashboard/stats",
  cameras: "/cameras",
  camerasSync: "/cameras/sync",
  recentAlerts: "/alerts?limit=50",
  recentDetections: "/vehicles/events/recent?limit=50",
  acknowledge: (id) => `/alerts/${id}`,
  watchlist: "/watchlist",
};

export const http = axios.create({
  baseURL: API_BASE,
  timeout: 8000,
  headers: { "Content-Type": "application/json" },
});

// ─── Auth: JWT stored in localStorage, attached to every request ─────────────
const TOKEN_KEY = "sentinel_token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode */
  }
}

export function isAuthenticated() {
  return Boolean(getToken());
}

http.interceptors.request.use((config) => {
  const t = getToken();
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

let onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

http.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      setToken("");
      if (onUnauthorized) onUnauthorized();
    }
    return Promise.reject(err);
  }
);

export async function login(username, password) {
  const { data } = await http.post(ENDPOINTS.login, { username, password });
  const token = data?.access_token || data?.token;
  if (!token) throw new Error("no token in login response");
  setToken(token);
  return token;
}

export function logout() {
  setToken("");
}

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
  const status = String(pick(raw, ["status"], "")).toUpperCase();
  return {
    id: pick(raw, ["id", "alert_id", "event_id"], `alert-${Date.now()}`),
    type: String(pick(raw, ["type", "alert_type", "category"], "WATCHLIST")).toUpperCase(),
    cam: String(pick(raw, ["cam", "camera_code", "camera_id", "cam_id", "source"], "CAM-?")),
    vehicle: pick(
      raw,
      ["vehicle", "plate", "plate_number_normalized", "plate_number", "registration"],
      null
    ),
    severity: String(
      pick(raw, ["severity", "priority_level", "priority", "level"], "medium")
    ).toLowerCase(),
    msg: pick(raw, ["msg", "message", "description", "detail", "offense_category"], "Watchlist hit"),
    time:
      pick(raw, ["time", "timestamp", "created_at"], null) != null
        ? formatTime(pick(raw, ["time", "timestamp", "created_at"], null))
        : new Date().toLocaleTimeString("en-IN", { hour12: false }),
    ack: Boolean(pick(raw, ["ack", "acknowledged", "is_acknowledged"], false)) ||
      status === "ACKNOWLEDGED" ||
      status === "RESOLVED",
    snapshotUrl: pick(raw, ["snapshot_url", "evidence_snapshot_url"], null),
  };
}

export function normalizeDetection(raw) {
  return {
    id: pick(raw, ["event_id", "id"], `evt-${Date.now()}`),
    plate: pick(raw, ["plate", "plate_number", "plate_number_normalized"], "—"),
    cam: String(pick(raw, ["camera_code", "camera_id", "cam"], "CAM-?")),
    camName: pick(raw, ["camera_name", "cam_name"], null),
    trackId: pick(raw, ["track_id", "trackId"], null),
    confidence: pick(raw, ["confidence_score", "confidence"], null),
    time: formatTime(pick(raw, ["timestamp", "time", "created_at"], null)),
    snapshotUrl: pick(raw, ["snapshot_url"], null),
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
  // Real recent AI detections across all cameras (dashboard event feed).
  const res = await safe(
    () => http.get(ENDPOINTS.recentDetections),
    WATCHLIST_DETECTIONS,
    "recent detections"
  );
  const list = Array.isArray(res.data) ? res.data : res.data?.items || [];
  return { ...res, data: res.live ? list.map(normalizeDetection) : res.data };
}

export async function acknowledgeAlert(id) {
  try {
    await http.patch(ENDPOINTS.acknowledge(id), { status: "ACKNOWLEDGED" });
    return { ok: true, live: true };
  } catch (err) {
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.warn("[api] acknowledge failed, updating UI optimistically:", err?.message || err);
    }
    return { ok: false, live: false, error: err };
  }
}
