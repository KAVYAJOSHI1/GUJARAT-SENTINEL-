import { makeSimulatedAlert } from "../lib/mockData.js";
import { getToken } from "./api.js";

// ─── Live alert WebSocket client (DEVELOPER_README Isha §5 / §8 / §15) ────────
// - connects to ws://localhost:8000/ws/alerts (proxied through Vite in dev)
// - exponential backoff reconnect: 2s → 4s → 8s (then holds at 8s)
// - when the socket cannot be established, falls back to a local simulator so
//   the demo still shows real-time toasts with no backend running.
//
// Auth (SENTINEL_System_Audit_Report.md §9/§10/§15 — "/ws/alerts accepts
// every connection, no token check at all"): the backend now requires the
// same session JWT the REST API uses before it will register this
// connection. A browser WebSocket can't set an Authorization header, so the
// token rides as a WS *subprotocol* (`new WebSocket(url, [token])`) instead
// of a `?token=` query string — unlike a query string, a subprotocol is
// never part of the URL, so it never lands in browser history or a
// request-line access log. If there's no token (not logged in) or the
// backend rejects it (missing/expired/invalid), the connection is refused
// and this falls back to the same local alert simulator used for any other
// unreachable-backend case — clearly labeled SIMULATED, never presented as
// a live feed (see ConnectionIndicator / AlertRow's "simulated" flag).

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
    // Read the token fresh on every attempt (not just once at socket
    // creation) so a login/logout/re-login between reconnect attempts is
    // picked up without needing to recreate the whole socket wrapper.
    const token = getToken();
    if (!token) {
      // Not authenticated -- never dial the real socket with no
      // credential (it would just be rejected server-side anyway); go
      // straight to the honestly-labeled simulator and keep checking.
      scheduleReconnect();
      return;
    }
    try {
      ws = new WebSocket(url, [token]);
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
