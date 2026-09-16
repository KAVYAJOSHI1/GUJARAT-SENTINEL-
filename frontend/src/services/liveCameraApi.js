// Client for the standalone Live Camera & AI service
// (scripts/live_camera_ai_service.py) that owns the single real
// CAM_AHM_001 RTSP camera. Deliberately NOT routed through services/api.js's
// axios instance / JWT interceptor: this service is isolated on its own
// port, carries no camera credentials or session data, and serves nothing
// but a public-on-the-LAN video feed + detection JSON for this one page.
const BASE = (import.meta.env.VITE_LIVE_CAMERA_API_URL || "http://localhost:8600").replace(/\/+$/, "");

export const LIVE_CAMERA_ENDPOINTS = {
  status: `${BASE}/api/v1/live-camera/status`,
  rawStream: `${BASE}/api/v1/live-camera/stream/raw.mjpg`,
  annotatedStream: `${BASE}/api/v1/live-camera/stream/annotated.mjpg`,
};

// Fetches the real, current camera/AI status. Never returns a fabricated
// status: a network failure is surfaced as status "OFFLINE" with an honest
// reason, not silently swapped for cached/fake data.
export async function fetchLiveCameraStatus() {
  try {
    const res = await fetch(LIVE_CAMERA_ENDPOINTS.status, { cache: "no-store" });
    if (!res.ok) throw new Error(`status ${res.status}`);
    const data = await res.json();
    return { data, live: true, error: null };
  } catch (err) {
    return {
      data: {
        camera_id: null,
        configured: false,
        status: "OFFLINE",
        last_error: "Live Camera & AI service unreachable",
        ai_status: "UNAVAILABLE",
        vehicles_detected: 0,
        detections: [],
      },
      live: false,
      error: err,
    };
  }
}
