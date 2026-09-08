// ─── Phase 14 §4/§5 — Traffic Intelligence API ───────────────────────────
// Shared axios instance (auth / baseURL / interceptors). No mock fallback —
// every figure is a live SQL aggregate over vehicle_events.
import { http } from "./api.js";

function clean(params = {}) {
  const out = {};
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0)) continue;
    out[k] = v;
  }
  return out;
}

export async function trafficOverview(params = {}) {
  const { data } = await http.get("/analytics/traffic/overview", { params: clean(params) });
  return data;
}

export async function trafficByCamera(params = {}) {
  const { data } = await http.get("/analytics/traffic/cameras", { params: clean(params) });
  return data;
}

export async function trafficTrends(params = {}) {
  const { data } = await http.get("/analytics/traffic/trends", { params: clean(params) });
  return data;
}

export async function trafficHeatmap(params = {}) {
  const { data } = await http.get("/analytics/traffic/heatmap", { params: clean(params) });
  return data;
}
