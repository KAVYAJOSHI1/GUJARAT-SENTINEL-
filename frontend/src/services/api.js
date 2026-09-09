import axios from "axios";
import {
  CAMERAS,
  INITIAL_ALERTS,
  MOCK_STATS,
  WATCHLIST_DETECTIONS,
} from "../lib/mockData.js";
// Circular import (mediaTicket.js imports http/getToken back) — safe: neither
// side touches the other's bindings at module-eval time, only inside functions.
import {
  clearMediaTicket,
  currentMediaTicket,
  ensureMediaTicket,
} from "./mediaTicket.js";

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

// Decode the (unverified) JWT payload for UI-only decisions — hiding an
// admin-only nav item, disabling a mutation button for a read-only role.
// The backend still enforces every permission; this is purely cosmetic.
export function currentSession() {
  const t = getToken();
  if (!t) return null;
  try {
    const payload = JSON.parse(
      atob(t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))
    );
    return { userId: payload.sub || null, role: payload.role || null };
  } catch {
    return null;
  }
}

export function currentRole() {
  return currentSession()?.role || null;
}

// ADMIN / OFFICER may manage incidents & cases; OPERATOR is read-only.
export function canManageOps() {
  const r = currentRole();
  return r === "ADMIN" || r === "OFFICER";
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
    const url = err?.config?.url || "";
    // A 401 from the media-ticket endpoint itself just means the session is
    // gone -- don't recurse, the primary-request 401 below handles logout.
    if (err?.response?.status === 401 && !url.includes("/auth/media-ticket")) {
      setToken("");
      clearMediaTicket();
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
  try { localStorage.setItem("sentinel_username", data?.username || username || ""); } catch { /* ignore */ }
  // Warm the media-ticket cache so the first evidence <img> already has a
  // usable ?token=.
  ensureMediaTicket().catch(() => {});
  return token;
}

// The signed-in username (UI-only: matching "assigned to me" rows, greeting).
export function currentUsername() {
  try { return localStorage.getItem("sentinel_username") || null; } catch { return null; }
}

export function logout() {
  setToken("");
  clearMediaTicket();
  try { localStorage.removeItem("sentinel_username"); } catch { /* ignore */ }
}

// Proxied evidence-image URL for one AI event, usable as <img src>.
// <img> can't send an Authorization header, so a SHORT-LIVED media ticket
// (purpose="media", ~120s) rides as ?token= — never the long-lived session
// JWT. The ticket comes from the auto-refreshing cache in mediaTicket.js;
// on a cold first render (e.g. right after a hard page reload) it can still
// be "" for a moment. Callers should gate the actual <img>/<video> render on
// `useMediaTicket()` (mediaTicket.js) being truthy rather than calling this
// unconditionally, so nothing fires a request with no credential at all.
//
export function evidenceUrl(eventId) {
  if (!eventId) return null;
  ensureMediaTicket().catch(() => {}); // warm for the next render
  const base = `${API_BASE}/vehicles/evidence/${encodeURIComponent(eventId)}`;
  const t = currentMediaTicket();
  return t ? `${base}?token=${encodeURIComponent(t)}` : base;
}

// Proxied raw video for one MOCK_CAM* camera, usable as <video src>. Real
// Sentinel cameras never resolve here (backend refuses any non-MOCK code) --
// their feed genuinely can't be embedded (Basic-auth RTSP, no CORS HLS).
export function mockVideoUrl(cameraId) {
  if (!cameraId) return null;
  ensureMediaTicket().catch(() => {});
  const base = `${API_BASE}/cameras/${encodeURIComponent(cameraId)}/mock-video`;
  const t = currentMediaTicket();
  return t ? `${base}?token=${encodeURIComponent(t)}` : base;
}

// ─── Normalisers ────────────────────────────────────────────────────────────
const pick = (obj, keys, fallback) => {
  for (const k of keys) if (obj?.[k] !== undefined && obj[k] !== null) return obj[k];
  return fallback;
};

// Backend CameraStatus is ONLINE / OFFLINE / DEGRADED. The UI's healthy state
// is called "active"; keep OFFLINE/DEGRADED as-is. ("alert" is derived from the
// alert list, never a camera field.)
export function mapCameraStatus(raw) {
  const s = String(raw || "").toLowerCase();
  if (s === "online" || s === "active") return "active";
  if (s === "offline") return "offline";
  if (s === "degraded") return "degraded";
  return s || "offline";
}

// "Paldi Circle, ..., Ahmedabad, Gujarat 380007, India" -> "Ahmedabad"
function zoneFromAddress(addr, fallback) {
  if (!addr) return fallback;
  const parts = String(addr).split(",").map((s) => s.trim()).filter(Boolean);
  const stateIdx = parts.findIndex((p) => /gujarat/i.test(p));
  if (stateIdx > 0) return parts[stateIdx - 1].replace(/\s*\d{5,6}$/, "").trim() || fallback;
  return parts.length >= 3 ? parts[parts.length - 3] : fallback;
}

// A camera is a LOCAL MOCK source (trafficdataset demo feed) iff its code
// carries the MOCK_ prefix the registry generator assigns (MOCK_CAM01, ...).
// Deliberately a naming convention, not a new backend field/schema change --
// see DEVELOPER_README.md "Mock cameras" for why. Never used to label a real
// Sentinel feed as mock or vice versa.
export function isMockCamera(codeOrId) {
  return /^mock[_-]?cam/i.test(String(codeOrId || ""));
}

export function normalizeCamera(raw) {
  const lat = Number(pick(raw, ["lat", "latitude", "location_lat"], NaN));
  const lng = Number(pick(raw, ["lng", "lon", "longitude", "location_lng"], NaN));
  const coords = raw?.location?.coordinates; // GeoJSON [lng, lat]
  const id = String(pick(raw, ["code", "camera_id", "cam_id", "id"], "CAM-?"));
  return {
    id,
    uuid: pick(raw, ["id"], null),
    code: pick(raw, ["code", "camera_id"], null),
    isMock: isMockCamera(id),
    name: pick(raw, ["name", "label", "location_name"], "Unnamed camera"),
    zone: zoneFromAddress(pick(raw, ["location_desc"], null), pick(raw, ["zone", "sector", "area"], "—")),
    locationDesc: pick(raw, ["location_desc"], null),
    lat: Number.isFinite(lat) ? lat : Array.isArray(coords) ? coords[1] : null,
    lng: Number.isFinite(lng) ? lng : Array.isArray(coords) ? coords[0] : null,
    status: mapCameraStatus(pick(raw, ["status", "state"], "offline")),
    resolution: pick(raw, ["resolution", "stream_resolution"], "—"),
    fps: pick(raw, ["fps", "frame_rate"], "—"),
    protocol: String(pick(raw, ["protocol", "stream_protocol"], "RTSP")).toUpperCase(),
    streamUrl: pick(raw, ["stream_url", "hls_url", "webrtc_url", "rtsp_url"], null),
    // Real stream-health telemetry (ingestion -> POST /cameras/health).
    // null until at least one health push has landed for this camera --
    // "never reported" is a distinct state from "offline".
    healthUpdatedAt: pick(raw, ["health_updated_at", "healthUpdatedAt"], null),
    frameDrops: pick(raw, ["frame_drop_count", "frameDrops"], null),
    reconnects: pick(raw, ["reconnect_count", "reconnects"], null),
    // Phase 13: authoritative REAL/MOCK flag + last detection time from the backend.
    isMockBackend: pick(raw, ["is_mock"], null),
    isDemo: pick(raw, ["is_demo"], false),
    feedSource: pick(raw, ["feed_source"], null),
    lastDetectionAt: pick(raw, ["last_detection_at", "lastDetectionAt"], null),
    rtspUrl: pick(raw, ["rtsp_url"], null),
    hlsUrl: pick(raw, ["hls_url"], null),
    webrtcUrl: pick(raw, ["webrtc_url"], null),
  };
}

export function normalizeAlert(raw) {
  const status = String(pick(raw, ["status"], "")).toUpperCase();
  const lat = Number(pick(raw, ["latitude", "lat"], NaN));
  const lng = Number(pick(raw, ["longitude", "lng", "lon"], NaN));
  return {
    id: pick(raw, ["id", "alert_id", "event_id"], `alert-${Date.now()}`),
    // The event behind this alert — lets the UI pull the real evidence
    // snapshot via the existing evidence proxy (GET /vehicles/evidence/{id}),
    // same mechanism DetectionRow already uses.
    eventId: pick(raw, ["vehicle_event_id", "eventId", "event_id"], null),
    type: String(pick(raw, ["type", "alert_type", "category"], "WATCHLIST MATCH")).toUpperCase(),
    cam: String(pick(raw, ["cam", "camera_code", "camera_id", "cam_id", "source"], "CAM-?")),
    camName: pick(raw, ["camera_name", "cam_name"], null),
    locationDesc: pick(raw, ["location_desc", "locationDesc"], null),
    lat: Number.isFinite(lat) ? lat : null,
    lng: Number.isFinite(lng) ? lng : null,
    vehicle: pick(
      raw,
      ["vehicle", "plate", "plate_number_normalized", "plate_number", "registration"],
      null
    ),
    severity: String(
      pick(raw, ["severity", "priority_level", "priority", "level"], "medium")
    ).toLowerCase(),
    msg: pick(raw, ["msg", "message", "description", "detail", "offense_category"], "Watchlist hit"),
    ts: pick(raw, ["timestamp", "created_at", "time"], null),
    time:
      pick(raw, ["time", "timestamp", "created_at"], null) != null
        ? formatTime(pick(raw, ["time", "timestamp", "created_at"], null))
        : new Date().toLocaleTimeString("en-IN", { hour12: false }),
    ack: Boolean(pick(raw, ["ack", "acknowledged", "is_acknowledged"], false)) ||
      status === "ACKNOWLEDGED" ||
      status === "RESOLVED" ||
      status === "ESCALATED",
    // Phase 12 — anomaly-sourced alert (stopped vehicle), no watchlist entry.
    source: String(pick(raw, ["source"], "WATCHLIST")).toUpperCase(),
    isAnomaly: String(pick(raw, ["source"], "")).toUpperCase() === "ANOMALY",
    anomalyEventId: pick(raw, ["anomaly_event_id"], null),
    // Phase 11 escalation workflow — raw backend status + escalation context.
    rawStatus: status || "NEW",
    assignedTo: pick(raw, ["assigned_to_username"], null),
    escalationReason: pick(raw, ["escalation_reason"], null),
    escalatedBy: pick(raw, ["escalated_by_username"], null),
    incidentId: pick(raw, ["incident_id"], null),
    incidentNumber: pick(raw, ["incident_number"], null),
    snapshotUrl: pick(raw, ["snapshot_url", "evidence_snapshot_url"], null),
    // True only for the local WS-fallback simulator (lib/mockData.js
    // makeSimulatedAlert) -- every real alert from the backend is left
    // false/undefined. Lets AlertRow mark it so it's never mistaken for a
    // live government-feed alert (SENTINEL_System_Audit_Report.md §14/§16).
    simulated: Boolean(pick(raw, ["simulated"], false)),
  };
}

export function normalizeDetection(raw) {
  const lat = Number(pick(raw, ["latitude", "lat"], NaN));
  const lng = Number(pick(raw, ["longitude", "lng", "lon"], NaN));
  return {
    id: String(pick(raw, ["event_id", "id"], `evt-${Date.now()}`)),
    plate: pick(raw, ["plate", "plate_number", "plate_number_normalized"], "UNKNOWN"),
    cam: String(pick(raw, ["camera_code", "camera_id", "cam"], "CAM-?")),
    camName: pick(raw, ["camera_name", "cam_name"], null),
    locationDesc: pick(raw, ["location_desc", "locationDesc"], null),
    vehicleType: pick(raw, ["vehicle_type", "vehicleType", "type"], null),
    trackId: pick(raw, ["track_id", "trackId"], null),
    confidence: pick(raw, ["confidence_score", "confidence"], null),
    lat: Number.isFinite(lat) ? lat : null,
    lng: Number.isFinite(lng) ? lng : null,
    ts: pick(raw, ["timestamp", "time", "created_at"], null),
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
  const totalCameras = pick(raw, ["totalCameras", "total_cameras", "cameras_total"], MOCK_STATS.totalCameras);
  const onlineFeeds = pick(raw, ["onlineFeeds", "online_feeds", "cameras_online"], MOCK_STATS.onlineFeeds);
  const degradedCameras = pick(raw, ["degradedCameras", "degraded_cameras"], 0);
  return {
    totalCameras,
    onlineFeeds,
    // Backend didn't add offline_cameras until this UI pass — fall back to
    // the arithmetic so older API responses still render a sane value.
    offlineCameras: pick(
      raw,
      ["offlineCameras", "offline_cameras"],
      Math.max(0, totalCameras - onlineFeeds - degradedCameras)
    ),
    degradedCameras,
    activeAlerts: pick(raw, ["activeAlerts", "active_alerts", "alerts_active"], MOCK_STATS.activeAlerts),
    watchlistMatches: pick(raw, ["watchlistMatches", "watchlist_matches"], MOCK_STATS.activeAlerts),
    // Operational counts (added with the incident/case layer). Absent on an
    // older backend -> 0, never a fabricated value.
    activeIncidents: pick(raw, ["activeIncidents", "active_incidents"], 0),
    openCases: pick(raw, ["openCases", "open_cases"], 0),
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
