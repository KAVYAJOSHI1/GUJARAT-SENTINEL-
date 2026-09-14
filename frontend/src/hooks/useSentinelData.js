import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  acknowledgeAlert,
  fetchCameras,
  fetchRecentAlerts,
  fetchStats,
  fetchWatchlistDetections,
  normalizeAlert,
} from "../services/api.js";
import { createAlertSocket } from "../services/websocket.js";
import { fetchSystemHealth } from "../services/observabilityApi.js";
import { fetchUnreadCount, listCases, listIncidents } from "../services/opsApi.js";
import { listAnomalies } from "../services/aiApi.js";
import { useToast } from "../context/ToastContext.jsx";

// Central data layer for the command center. One instance lives in <App/> and
// is handed to the pages via react-router's <Outlet context>.
//  - concurrent fetch of stats + cameras + alerts (README §9.2)
//  - live WebSocket alert stream with toast dispatch (README §9.3–9.4)
//  - acknowledge via POST, optimistic UI (README §9.5)
//  - every source degrades to mock data when the backend is down
export function useSentinelData() {
  const { push } = useToast();

  const [stats, setStats] = useState(null);
  const [cameras, setCameras] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [detections, setDetections] = useState([]);
  // Command-center observability aggregate (Phase 7). `null` = not (yet)
  // available -- panels render an explicit "unavailable" state, never fake
  // numbers.
  const [health, setHealth] = useState(null);
  const [healthLive, setHealthLive] = useState(false);
  // Operational layer (incidents / cases / notifications). Small live slices
  // for the command center — full lists live on their own pages.
  const [incidents, setIncidents] = useState([]);
  const [cases, setCases] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [notifUnread, setNotifUnread] = useState(0);

  const [loading, setLoading] = useState(true);
  const [backendLive, setBackendLive] = useState(true);
  const [retrying, setRetrying] = useState(false);
  const [wsStatus, setWsStatus] = useState("connecting");
  const [lastRefresh, setLastRefresh] = useState(null);

  const seenIds = useRef(new Set());
  const alertsRef = useRef([]);
  alertsRef.current = alerts;

  const refreshOps = useCallback(async () => {
    // Never blocks the core dashboard: each call degrades to [] / 0 on error.
    const [inc, cas, anom, unread] = await Promise.all([
      listIncidents({ active_only: true, limit: 6 }).catch(() => null),
      listCases({ limit: 6 }).catch(() => null),
      listAnomalies({ limit: 6 }).catch(() => null),
      fetchUnreadCount(),
    ]);
    if (inc?.items) setIncidents(inc.items);
    if (cas?.items) setCases(cas.items);
    if (anom?.items) setAnomalies(anom.items);
    setNotifUnread(unread || 0);
  }, []);

  const load = useCallback(async () => {
    setRetrying(true);
    const [s, c, a, d, h] = await Promise.all([
      fetchStats(),
      fetchCameras(),
      fetchRecentAlerts(),
      fetchWatchlistDetections(),
      fetchSystemHealth(),
    ]);
    setStats(s.data);
    setCameras(c.data.filter((cam) => !cam.isMock));
    setAlerts(a.data);
    setDetections(d.data);
    setHealth(h.data);
    setHealthLive(h.live);
    a.data.forEach((al) => seenIds.current.add(String(al.id)));
    setBackendLive(s.live || c.live || a.live);
    setLoading(false);
    setRetrying(false);
    setLastRefresh(new Date());
    refreshOps();
  }, [refreshOps]);

  useEffect(() => {
    load();
  }, [load]);

  // ── Light live refresh (stats / cameras / recent AI detections) ───────────
  // Alerts are NOT re-fetched here: new ones arrive over the WebSocket below,
  // and re-pulling the whole list would fight the optimistic ack state. One
  // interval, not per-component polling, so this stays cheap.
  useEffect(() => {
    const id = setInterval(async () => {
      const [s, c, d, h] = await Promise.all([
        fetchStats(),
        fetchCameras(),
        fetchWatchlistDetections(),
        fetchSystemHealth(),
      ]);
      setStats(s.data);
      setCameras(c.data.filter((cam) => !cam.isMock));
      setDetections(d.data);
      setHealth(h.data);
      setHealthLive(h.live);
      setBackendLive((prev) => s.live || c.live || prev);
      setLastRefresh(new Date());
      refreshOps();
    }, 10000);
    return () => clearInterval(id);
  }, [refreshOps]);

  // ── Live alert stream ──────────────────────────────────────────────────────
  useEffect(() => {
    const sock = createAlertSocket({
      onStatus: setWsStatus,
      onAlert: (raw) => {
        const alert = normalizeAlert(raw);
        const key = String(alert.id);
        if (seenIds.current.has(key)) return;
        seenIds.current.add(key);
        setAlerts((prev) => [alert, ...prev].slice(0, 60));
        push({
          id: `t-${key}`,
          title: alert.type,
          msg: alert.msg,
          cam: alert.cam,
          vehicle: alert.vehicle,
          time: alert.time,
          severity: alert.severity,
        });
      },
    });
    return () => sock.close();
  }, [push]);

  // ── Acknowledge ───────────────────────────────────────────────────────────
  const ackAlert = useCallback(async (id) => {
    setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, ack: true } : a)));
    await acknowledgeAlert(id);
  }, []);

  const ackAll = useCallback(async () => {
    const pending = alertsRef.current.filter((a) => !a.ack);
    setAlerts((prev) => prev.map((a) => ({ ...a, ack: true })));
    await Promise.all(pending.map((a) => acknowledgeAlert(a.id)));
  }, []);

  // ── Derived ───────────────────────────────────────────────────────────────
  const unackCount = alerts.filter((a) => !a.ack).length;
  const critCount = alerts.filter((a) => !a.ack && a.severity === "critical").length;

  // Most recent detection per camera (drives the live-preview thumbnail).
  // `detections` is already newest-first from the backend.
  const latestDetectionByCamera = useMemo(() => {
    const map = {};
    for (const d of detections) {
      if (!map[d.cam]) map[d.cam] = d;
    }
    return map;
  }, [detections]);

  // Total detections seen per camera in the currently-loaded feed (README
  // task §7 — "Vehicle detections: X" on each camera card). Derived from the
  // same already-fetched list, no extra request.
  const detectionCountByCamera = useMemo(() => {
    const map = {};
    for (const d of detections) map[d.cam] = (map[d.cam] || 0) + 1;
    return map;
  }, [detections]);

  // Overlay an "alert" status onto any camera carrying an unacknowledged
  // alert, so the command-center / camera grid / GIS map can all show the
  // AMBER "active incident" state (README task §4/§7) from ONE computation
  // instead of every consumer re-deriving it. Never overrides "offline" --
  // a dead camera stays visually offline (RED) even if it also has a stale
  // unacked alert on record.
  const camerasWithIncidentStatus = useMemo(() => {
    if (!alerts.length) return cameras;
    const alertCams = new Set(alerts.filter((a) => !a.ack).map((a) => a.cam));
    if (!alertCams.size) return cameras;
    return cameras.map((c) =>
      alertCams.has(c.id) && c.status !== "offline" ? { ...c, status: "alert" } : c
    );
  }, [cameras, alerts]);

  return {
    stats,
    cameras: camerasWithIncidentStatus,
    alerts,
    detections,
    incidents,
    cases,
    anomalies,
    notifUnread,
    refreshNotifications: refreshOps,
    health,
    healthLive,
    latestDetectionByCamera,
    detectionCountByCamera,
    loading,
    backendLive,
    retrying,
    lastRefresh,
    wsStatus,
    unackCount,
    critCount,
    reload: load,
    ackAlert,
    ackAll,
  };
}
