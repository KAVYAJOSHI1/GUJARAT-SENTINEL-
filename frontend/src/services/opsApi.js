// ─── Operational API layer — Incidents / Cases / Notifications / Audit ──────
// Builds on the shared axios instance (`http`) from services/api.js: one API
// architecture, same baseURL / interceptors / auth. These endpoints back the
// Incident Center, Case files, System notification center and Admin activity
// log added in the operational-platform phase.
//
// Rule (same as observabilityApi.js): NO mock fallback. Operational data is
// real backend state or an explicit error — never fabricated rows.
import { http } from "./api.js";
import { normalizePlate } from "../utils/plate.js";

// ── Incidents ──────────────────────────────────────────────────────────────
export async function listIncidents(params = {}) {
  const { data } = await http.get("/incidents", { params });
  return data; // { items, total, limit, offset }
}

export async function getIncident(id) {
  const { data } = await http.get(`/incidents/${encodeURIComponent(id)}`);
  return data;
}

export async function createIncident(payload) {
  const { data } = await http.post("/incidents", payload);
  return data;
}

export async function updateIncident(id, payload) {
  const { data } = await http.patch(`/incidents/${encodeURIComponent(id)}`, payload);
  return data;
}

export async function setIncidentStatus(id, status) {
  const { data } = await http.post(`/incidents/${encodeURIComponent(id)}/status`, { status });
  return data;
}

export async function assignIncident(id, userId) {
  const { data } = await http.post(`/incidents/${encodeURIComponent(id)}/assign`, {
    user_id: userId || null,
  });
  return data;
}

export async function addIncidentNote(id, body) {
  const { data } = await http.post(`/incidents/${encodeURIComponent(id)}/notes`, { body });
  return data;
}

export async function attachIncidentEvidence(id, vehicleEventId, note) {
  const { data } = await http.post(`/incidents/${encodeURIComponent(id)}/evidence`, {
    vehicle_event_id: vehicleEventId,
    note: note || null,
  });
  return data;
}

export async function detachIncidentEvidence(id, linkId) {
  await http.delete(`/incidents/${encodeURIComponent(id)}/evidence/${encodeURIComponent(linkId)}`);
}

// ── Cases ──────────────────────────────────────────────────────────────────
export async function listCases(params = {}) {
  const { data } = await http.get("/cases", { params });
  return data;
}

export async function getCase(id) {
  const { data } = await http.get(`/cases/${encodeURIComponent(id)}`);
  return data;
}

export async function createCase(payload) {
  const body = { ...payload };
  if (body.primary_plate_number) body.primary_plate_number = normalizePlate(body.primary_plate_number);
  const { data } = await http.post("/cases", body);
  return data;
}

export async function updateCase(id, payload) {
  const { data } = await http.patch(`/cases/${encodeURIComponent(id)}`, payload);
  return data;
}

export async function assignCase(id, userId) {
  const { data } = await http.post(`/cases/${encodeURIComponent(id)}/assign`, {
    user_id: userId || null,
  });
  return data;
}

export async function addCaseNote(id, body) {
  const { data } = await http.post(`/cases/${encodeURIComponent(id)}/notes`, { body });
  return data;
}

export async function attachCaseIncident(id, incidentId) {
  const { data } = await http.post(`/cases/${encodeURIComponent(id)}/incidents`, {
    incident_id: incidentId,
  });
  return data;
}

export async function detachCaseIncident(id, incidentId) {
  await http.delete(`/cases/${encodeURIComponent(id)}/incidents/${encodeURIComponent(incidentId)}`);
}

export async function attachCaseEvidence(id, vehicleEventId, note) {
  const { data } = await http.post(`/cases/${encodeURIComponent(id)}/evidence`, {
    vehicle_event_id: vehicleEventId,
    note: note || null,
  });
  return data;
}

export async function detachCaseEvidence(id, linkId) {
  await http.delete(`/cases/${encodeURIComponent(id)}/evidence/${encodeURIComponent(linkId)}`);
}

// Case report CSV — streamed by the backend; trigger a browser download.
export async function downloadCaseReportCSV(id, caseNumber) {
  const res = await http.get(`/cases/${encodeURIComponent(id)}/report`, {
    params: { format: "csv" },
    responseType: "blob",
  });
  const url = URL.createObjectURL(new Blob([res.data], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `${caseNumber || "case"}_report.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Notifications ──────────────────────────────────────────────────────────
export async function listNotifications(params = {}) {
  const { data } = await http.get("/notifications", { params });
  return data;
}

export async function fetchUnreadCount() {
  try {
    const { data } = await http.get("/notifications/unread-count");
    return data.unread ?? 0;
  } catch {
    return 0;
  }
}

export async function markNotificationRead(id) {
  const { data } = await http.post(`/notifications/${encodeURIComponent(id)}/read`);
  return data;
}

export async function markAllNotificationsRead() {
  const { data } = await http.post("/notifications/read-all");
  return data;
}

// ── Audit / Activity ───────────────────────────────────────────────────────
export async function listAuditLogs(params = {}) {
  const { data } = await http.get("/admin/audit", { params });
  return data;
}

// ── Users (for assignment dropdowns) — reuses the existing admin users list
// if present; tolerates absence (returns []).
export async function listAssignableUsers() {
  try {
    const { data } = await http.get("/admin/users");
    const list = Array.isArray(data) ? data : data?.items || [];
    return list.map((u) => ({ id: u.id, username: u.username, role: u.role }));
  } catch {
    return [];
  }
}

// ── Phase 11 — Advanced / Global search ────────────────────────────────────
export async function searchVehicles(query) {
  const { data } = await http.post("/search/vehicles", query);
  return data; // { items, total, limit, offset, sort, took_ms }
}

export async function globalSearch(q) {
  const { data } = await http.get("/search/global", { params: { q } });
  return data; // { query, groups, total }
}

// ── Saved investigations ──────────────────────────────────────────────────
export async function listSavedSearches() {
  const { data } = await http.get("/saved-searches");
  return data;
}
export async function createSavedSearch(payload) {
  const { data } = await http.post("/saved-searches", payload);
  return data;
}
export async function updateSavedSearch(id, payload) {
  const { data } = await http.patch(`/saved-searches/${encodeURIComponent(id)}`, payload);
  return data;
}
export async function deleteSavedSearch(id) {
  await http.delete(`/saved-searches/${encodeURIComponent(id)}`);
}

// ── Watchlist management ──────────────────────────────────────────────────
export async function listWatchlist(params = {}) {
  const { data } = await http.get("/watchlist", { params });
  return data;
}
export async function watchlistCategories() {
  const { data } = await http.get("/watchlist/categories");
  return data;
}
export async function createWatchlistEntry(payload) {
  const { data } = await http.post("/watchlist", payload);
  return data;
}
export async function updateWatchlistEntry(id, payload) {
  const { data } = await http.patch(`/watchlist/${encodeURIComponent(id)}`, payload);
  return data;
}
export async function activateWatchlistEntry(id) {
  const { data } = await http.post(`/watchlist/${encodeURIComponent(id)}/activate`);
  return data;
}
export async function deactivateWatchlistEntry(id) {
  await http.delete(`/watchlist/${encodeURIComponent(id)}`);
}
export async function importWatchlistCSV(file, dryRun = false) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await http.post(`/watchlist/import.csv?dry_run=${dryRun}`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}
export async function downloadWatchlistCSV() {
  const res = await http.get("/watchlist/export.csv", { responseType: "blob" });
  triggerDownload(res.data, "watchlist_export.csv", "text/csv");
}

// ── Alert escalation workflow ─────────────────────────────────────────────
export async function assignAlert(id, userId) {
  const { data } = await http.post(`/alerts/${encodeURIComponent(id)}/assign`, { user_id: userId || null });
  return data;
}
export async function escalateAlert(id, reason) {
  const { data } = await http.post(`/alerts/${encodeURIComponent(id)}/escalate`, { reason });
  return data;
}
export async function resolveAlert(id, note) {
  const { data } = await http.post(`/alerts/${encodeURIComponent(id)}/resolve`, { note: note || null });
  return data;
}

// ── Timelines ─────────────────────────────────────────────────────────────
export async function incidentTimeline(id, category) {
  const { data } = await http.get(`/incidents/${encodeURIComponent(id)}/timeline`,
    { params: category ? { category } : {} });
  return data;
}
export async function caseTimeline(id, category) {
  const { data } = await http.get(`/cases/${encodeURIComponent(id)}/timeline`,
    { params: category ? { category } : {} });
  return data;
}

// ── Officer work queue ───────────────────────────────────────────────────
export async function fetchWorkQueue(sort = "priority") {
  const { data } = await http.get("/work-queue", { params: { sort } });
  return data;
}

// ── Reports ──────────────────────────────────────────────────────────────
export async function listReports() {
  const { data } = await http.get("/reports");
  return data;
}
export async function downloadReport(key, params = {}) {
  const res = await http.get(`/reports/${encodeURIComponent(key)}.csv`, {
    params, responseType: "blob",
  });
  triggerDownload(res.data, `${key}.csv`, "text/csv");
}

// Phase 13: same report, rendered client-side as a PDF (CSV stays primary).
export async function downloadReportPDF(key, name, params = {}) {
  const { exportCsvTextToPDF } = await import("../utils/reportExporter.js");
  const res = await http.get(`/reports/${encodeURIComponent(key)}.csv`, { params, responseType: "text" });
  exportCsvTextToPDF(name || key, typeof res.data === "string" ? res.data : String(res.data));
}

// ── Camera health history ────────────────────────────────────────────────
export async function cameraHealthHistory(cameraId) {
  const { data } = await http.get(`/cameras/${encodeURIComponent(cameraId)}/health/history`);
  return data;
}

function triggerDownload(blobData, filename, type) {
  const url = URL.createObjectURL(new Blob([blobData], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
