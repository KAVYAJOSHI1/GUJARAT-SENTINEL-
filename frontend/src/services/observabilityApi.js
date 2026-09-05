// ─── Command-center observability API ──────────────────────────────────────
// GET /api/v1/dashboard/health — real system health aggregate (backend, DB,
// AI pipeline, cameras, event flow, alerts).
//
// Phase 7 rule: NO mock fallback. If the request fails, `data` is null and
// the caller must render an explicit "unavailable" state — never fabricated
// numbers.
import { http } from "./api.js";

export async function fetchSystemHealth() {
  try {
    const { data } = await http.get("/dashboard/health");
    return { data: normalizeHealth(data), live: true, error: null };
  } catch (err) {
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.warn("[observabilityApi] /dashboard/health unavailable:", err?.message || err);
    }
    return { data: null, live: false, error: err };
  }
}

const n = (v) => (v === null || v === undefined ? null : Number(v));

function normalizeHealth(raw) {
  if (!raw) return null;
  const ap = raw.ai_pipeline || {};
  const cam = raw.cameras || {};
  const ev = raw.events || {};
  const al = raw.alerts || {};
  return {
    generatedAt: raw.generated_at || null,
    backend: { status: raw.backend?.status || "unknown" },
    database: {
      status: raw.database?.status || "unknown",
      latencyMs: n(raw.database?.latency_ms),
    },
    aiPipeline: {
      status: ap.status || "unknown", // online | stale | unknown
      reportedAt: ap.reported_at || null,
      ageSeconds: n(ap.age_seconds),
      numWorkers: n(ap.num_workers),
      processedFps: n(ap.processed_fps),
      framesProcessed: n(ap.frames_processed),
      vehiclesDetected: n(ap.vehicles_detected),
      eventsGenerated: n(ap.events_generated),
      eventsDelivered: n(ap.events_delivered),
      eventsDropped: n(ap.events_dropped),
      queueDepth: n(ap.event_queue_depth),
      queueMaxDepth: n(ap.event_queue_max_depth),
      yolo: { p50: n(ap.yolo_latency_ms?.p50_ms), p95: n(ap.yolo_latency_ms?.p95_ms) },
      ocr: { p50: n(ap.ocr_latency_ms?.p50_ms), p95: n(ap.ocr_latency_ms?.p95_ms) },
      cpuPercent: n(ap.cpu_percent),
      rssMb: n(ap.rss_mb),
      camerasProcessing: n(ap.cameras_processing),
    },
    cameras: {
      total: n(cam.total) ?? 0,
      online: n(cam.online) ?? 0,
      degraded: n(cam.degraded) ?? 0,
      offline: n(cam.offline) ?? 0,
      stale: n(cam.stale) ?? 0,
      neverReported: n(cam.never_reported) ?? 0,
      oldestHealthAgeSeconds: n(cam.oldest_health_age_seconds),
    },
    events: {
      lastEventAt: ev.last_event_at || null,
      lastEventAgeSeconds: n(ev.last_event_age_seconds),
      last15min: n(ev.events_last_15min) ?? 0,
      readable15min: n(ev.readable_last_15min) ?? 0,
      unknown15min: n(ev.unknown_last_15min) ?? 0,
    },
    alerts: {
      total: n(al.total) ?? 0,
      active: n(al.active) ?? 0,
      acknowledged: n(al.acknowledged) ?? 0,
      highOrCriticalActive: n(al.high_or_critical_active) ?? 0,
    },
  };
}
