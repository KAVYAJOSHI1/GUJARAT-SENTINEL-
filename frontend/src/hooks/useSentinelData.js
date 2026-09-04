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

  const [loading, setLoading] = useState(true);
  const [backendLive, setBackendLive] = useState(true);
  const [retrying, setRetrying] = useState(false);
  const [wsStatus, setWsStatus] = useState("connecting");

  const seenIds = useRef(new Set());
  const alertsRef = useRef([]);
  alertsRef.current = alerts;

  const load = useCallback(async () => {
    setRetrying(true);
    const [s, c, a, d] = await Promise.all([
      fetchStats(),
      fetchCameras(),
      fetchRecentAlerts(),
      fetchWatchlistDetections(),
    ]);
    setStats(s.data);
    setCameras(c.data);
    setAlerts(a.data);
    setDetections(d.data);
    a.data.forEach((al) => seenIds.current.add(String(al.id)));
    setBackendLive(s.live || c.live || a.live);
    setLoading(false);
    setRetrying(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // ── Light live refresh (stats / cameras / recent AI detections) ───────────
  // Alerts are NOT re-fetched here: new ones arrive over the WebSocket below,
  // and re-pulling the whole list would fight the optimistic ack state. One
  // interval, not per-component polling, so this stays cheap.
  useEffect(() => {
    const id = setInterval(async () => {
      const [s, c, d] = await Promise.all([fetchStats(), fetchCameras(), fetchWatchlistDetections()]);
      setStats(s.data);
      setCameras(c.data);
      setDetections(d.data);
      setBackendLive((prev) => s.live || c.live || prev);
    }, 10000);
    return () => clearInterval(id);
  }, []);

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

  return {
    stats,
    cameras,
    alerts,
    detections,
    latestDetectionByCamera,
    loading,
    backendLive,
    retrying,
    wsStatus,
    unackCount,
    critCount,
    reload: load,
    ackAlert,
    ackAll,
  };
}
