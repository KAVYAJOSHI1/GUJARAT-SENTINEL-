// ─── Vehicle-intelligence analytics API ────────────────────────────────────
// GET /api/v1/analytics/overview — live DB aggregates for the "Vehicle
// Intelligence" panel. Unlike the compact dashboard strip (which is derived
// from the ~50 already-loaded recent events), these numbers are true
// aggregates over the whole vehicle_events / alerts tables.
//
// Phase 5 rule: NO mock fallback. If the request fails, callers must show an
// honest "unavailable" state, never fabricated numbers.
import { http } from "./api.js";

export async function fetchAnalyticsOverview({ windowHours = 24, top = 8 } = {}) {
  try {
    const { data } = await http.get("/analytics/overview", {
      params: { window_hours: windowHours, top },
    });
    return { data: normalizeOverview(data), live: true, error: null };
  } catch (err) {
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.warn("[analyticsApi] overview unavailable:", err?.message || err);
    }
    return { data: null, live: false, error: err };
  }
}

function normalizeOverview(raw) {
  const list = (arr) =>
    (Array.isArray(arr) ? arr : []).map((r) => ({
      label: String(r.label ?? "?"),
      value: Number(r.count ?? r.value ?? 0),
      detail: r.detail ?? null,
    }));
  return {
    generatedAt: raw?.generated_at || null,
    windowHours: Number(raw?.window_hours ?? 24),
    totalEvents: Number(raw?.total_events ?? 0),
    totalEventsInWindow: Number(raw?.total_events_in_window ?? 0),
    readableInWindow: Number(raw?.readable_reads_in_window ?? 0),
    unknownInWindow: Number(raw?.unknown_reads_in_window ?? 0),
    distinctPlatesInWindow: Number(raw?.distinct_plates_in_window ?? 0),
    byType: list(raw?.detections_by_type),
    byCamera: list(raw?.detections_by_camera),
    topPlates: list(raw?.top_plates),
    byHour: (Array.isArray(raw?.recent_activity_by_hour) ? raw.recent_activity_by_hour : []).map(
      (b) => ({ label: String(b.hour || "").slice(11, 16), value: Number(b.count ?? 0) })
    ),
    watchlistMatchesTotal: Number(raw?.watchlist_matches_total ?? 0),
    watchlistMatchesInWindow: Number(raw?.watchlist_matches_in_window ?? 0),
    activeAlerts: Number(raw?.active_alerts ?? 0),
  };
}
