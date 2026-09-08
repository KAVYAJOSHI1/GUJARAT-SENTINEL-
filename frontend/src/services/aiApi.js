// ─── Phase 12 — AI intelligence layer API ─────────────────────────────────
// Reuses the shared axios instance (same baseURL / interceptors / auth) —
// one API architecture. No mock fallback: AI results are real backend data
// or an explicit error.
import { http } from "./api.js";

export async function aiStatus() {
  const { data } = await http.get("/ai/status");
  return data;
}

export async function aiSuggestions() {
  try {
    const { data } = await http.get("/ai/suggestions");
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

export async function aiInvestigate(query, contextPlate) {
  const { data } = await http.post("/ai/investigate", { query },
    contextPlate ? { params: { plate: contextPlate } } : undefined);
  return data;
}

export async function aiSearch(query, { limit = 50, offset = 0 } = {}) {
  const { data } = await http.post("/ai/search", { query, limit, offset });
  return data;
}

export async function aiIncidentSummary(id) {
  const { data } = await http.post(`/ai/incidents/${encodeURIComponent(id)}/summary`);
  return data;
}

export async function aiCaseSummary(id) {
  const { data } = await http.post(`/ai/cases/${encodeURIComponent(id)}/summary`);
  return data;
}

export async function listAnomalies(params = {}) {
  const { data } = await http.get("/ai/anomalies", { params });
  return data;
}

export async function scanAnomalies(body = {}) {
  const { data } = await http.post("/ai/anomalies/scan", body);
  return data;
}

export async function reviewAnomaly(id, status) {
  const { data } = await http.post(`/ai/anomalies/${encodeURIComponent(id)}/review`, { status });
  return data;
}
