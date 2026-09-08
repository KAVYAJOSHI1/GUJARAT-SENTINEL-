// ─── Phase 14 §9 — Camera Reliability Intelligence ───────────────────────
// Statistics over camera_health_history. NOT failure prediction.
import { http } from "./api.js";

export async function cameraIntelligence(windowHours = 24) {
  const { data } = await http.get("/ai/camera-intelligence", { params: { window_hours: windowHours } });
  return data;
}

export async function cameraReliability(code, windowHours = 24) {
  const { data } = await http.get(`/ai/camera-intelligence/${encodeURIComponent(code)}`, {
    params: { window_hours: windowHours },
  });
  return data;
}
