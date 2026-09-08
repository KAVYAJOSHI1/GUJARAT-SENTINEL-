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
