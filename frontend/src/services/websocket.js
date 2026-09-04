import { makeSimulatedAlert } from "../lib/mockData.js";

// ─── Live alert WebSocket client (DEVELOPER_README Isha §5 / §8 / §15) ────────
// - connects to ws://localhost:8000/ws/alerts (proxied through Vite in dev)
// - exponential backoff reconnect: 2s → 4s → 8s (then holds at 8s)
// - when the socket cannot be established, falls back to a local simulator so
//   the demo still shows real-time toasts with no backend running.

function defaultWsUrl() {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/alerts`;
}

const BACKOFF = [2000, 4000, 8000];

export function createAlertSocket({ onAlert, onStatus, url = defaultWsUrl() }) {
  let ws = null;
  let attempt = 0;
  let closedByUser = false;
  let reconnectTimer = null;
  let simTimer = null;

  const status = (s) => onStatus?.(s);

  function startSimulator() {
    if (simTimer) return;
    status("simulated");
    simTimer = setInterval(() => {
      onAlert?.(makeSimulatedAlert());
    }, 12000);
  }

  function stopSimulator() {
    if (simTimer) {
      clearInterval(simTimer);
      simTimer = null;
    }
  }

  function scheduleReconnect() {
    const delay = BACKOFF[Math.min(attempt, BACKOFF.length - 1)];
    attempt += 1;
    status("reconnecting");
    // After we've exhausted the backoff ladder once, run the simulator so the
    // UI keeps producing alerts, but keep trying the real socket underneath.
    if (attempt > BACKOFF.length) startSimulator();
    reconnectTimer = setTimeout(connect, delay);
  }

  function connect() {
    if (closedByUser) return;
    try {
      ws = new WebSocket(url);
    } catch {
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      attempt = 0;
      stopSimulator();
      status("connected");
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const alerts = Array.isArray(payload) ? payload : [payload];
        alerts.forEach((a) => onAlert?.(a));
      } catch {
        // Non-JSON frame (e.g. a heartbeat) — ignore.
      }
    };

    ws.onerror = () => {
      // onclose fires next and handles reconnect.
    };

    ws.onclose = () => {
      if (closedByUser) return;
      scheduleReconnect();
    };
  }

  connect();

  return {
    close() {
      closedByUser = true;
      status("closed");
      clearTimeout(reconnectTimer);
      stopSimulator();
      ws?.close();
    },
  };
}
