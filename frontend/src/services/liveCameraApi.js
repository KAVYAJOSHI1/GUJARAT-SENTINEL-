// Client for the standalone Live Camera & AI service
// (scripts/live_camera_ai_service.py), which now connects to a camera's
// real RTSP feed ONLY on demand -- the first time its status/stream is
// requested -- and releases it after it stops being polled. This client
// mirrors that: fetchLiveCameraList() is a cheap, side-effect-free read for
// populating the dropdown; fetchCameraStatus(id) is what actually causes
// the backend to open (and keep alive) that one camera's connection.
//
// Deliberately NOT routed through services/api.js's axios instance / JWT
// interceptor: this service is isolated on its own port, carries no camera
// credentials or session data, and serves nothing but public-on-the-LAN
// video feeds + detection JSON for this one page.
const BASE = (import.meta.env.VITE_LIVE_CAMERA_API_URL || "http://localhost:8600").replace(/\/+$/, "");

export const LIVE_CAMERA_LIST_URL = `${BASE}/api/v1/live-camera/cameras`;

export function cameraStatusUrl(cameraId) {
  return `${BASE}/api/v1/live-camera/${encodeURIComponent(cameraId)}/status`;
}

// `w` optionally caps the JPEG output width server-side -- detection, when
// applicable, already ran on the full-resolution frame; only the delivered
// image is resized.
export function rawStreamUrl(cameraId, { w } = {}) {
  const q = w ? `?w=${encodeURIComponent(w)}` : "";
  return `${BASE}/api/v1/live-camera/${encodeURIComponent(cameraId)}/stream/raw.mjpg${q}`;
}

export function annotatedStreamUrl(cameraId, { w } = {}) {
  const q = w ? `?w=${encodeURIComponent(w)}` : "";
  return `${BASE}/api/v1/live-camera/${encodeURIComponent(cameraId)}/stream/annotated.mjpg${q}`;
}

// The full camera list (id + real name from data/camera_registry.json) for
// populating the selector. Does NOT open any camera connection -- purely a
// read of the registry + whatever is already active. Never fabricated: a
// network failure returns an empty list with live:false.
export async function fetchLiveCameraList() {
  try {
    const res = await fetch(LIVE_CAMERA_LIST_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`status ${res.status}`);
    const data = await res.json();
    return {
      data: { ai_status: data.ai_status, ai_model_error: data.ai_model_error, cameras: data.cameras || [] },
      live: true,
      error: null,
    };
  } catch (err) {
    return { data: { ai_status: "UNAVAILABLE", ai_model_error: null, cameras: [] }, live: false, error: err };
  }
}

// Status of exactly ONE camera. This is the call that lazily opens (or
// keeps alive) that camera's real RTSP connection server-side -- so it
// should only ever be polled for the camera the user actually has selected,
// never for the whole fleet at once.
export async function fetchCameraStatus(cameraId) {
  try {
    const res = await fetch(cameraStatusUrl(cameraId), { cache: "no-store" });
    if (!res.ok) throw new Error(`status ${res.status}`);
    const data = await res.json();
    return { data, live: true, error: null };
  } catch (err) {
    return {
      data: {
        camera_id: cameraId, name: null, configured: false, active: false,
        status: "OFFLINE", last_error: "Live Camera & AI service unreachable",
        ai_status: "UNAVAILABLE", vehicles_detected: 0, detections: [],
      },
      live: false,
      error: err,
    };
  }
}
