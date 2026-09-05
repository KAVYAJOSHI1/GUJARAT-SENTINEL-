import { makeSimulatedAlert } from "../lib/mockData.js";
import { getToken } from "./api.js";
import { fetchWsTicket } from "./mediaTicket.js";

// ─── Live alert WebSocket client (DEVELOPER_README Isha §5 / §8 / §15) ────────
// - connects to ws://localhost:8000/ws/alerts (proxied through Vite in dev)
// - exponential backoff reconnect: 2s → 4s → 8s (then holds at 8s)
// - when the socket cannot be established, falls back to a local simulator so
//   the demo still shows real-time toasts with no backend running.
//
// Auth (SENTINEL_System_Audit_Report.md §9/§10/§15 — "/ws/alerts accepts
// every connection, no token check at all"): the backend requires an
// authenticated handshake before it registers this connection. Phase 4:
// the credential is now a SHORT-LIVED WS ticket (~60s, purpose="ws"),
// fetched via `POST /api/v1/auth/ws-ticket` with the real session JWT
// right before each (re)connect — the long-lived JWT itself is never put
// on the wire here. A browser WebSocket can't set an Authorization header,
// so the ticket rides as a WS *subprotocol* (`new WebSocket(url, [ticket])`)
// — never a `?token=` query string, so it never lands in browser history
// or a request-line access log. If there's no session (not logged in) or
// the ticket is refused, the connection falls back to the same local alert
// simulator used for any other unreachable-backend case — clearly labeled
// SIMULATED, never presented as a live feed.

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

  async function connect() {
    if (closedByUser) return;
    // Check auth fresh on every attempt so a login/logout/re-login between
    // reconnects is picked up without recreating the wrapper.
    if (!getToken()) {
      // Not authenticated -- never dial the real socket; go straight to the
      // honestly-labeled simulator and keep checking.
      scheduleReconnect();
      return;
    }
    // Exchange the session JWT for a fresh ~60s WS ticket right before the
    // handshake -- the long-lived JWT never travels on the wire here.
    let ticket = "";
    try {
      ticket = await fetchWsTicket();
    } catch {
      scheduleReconnect();
      return;
    }
    if (closedByUser) return;
    if (!ticket) {
      scheduleReconnect();
      return;
    }
    try {
      ws = new WebSocket(url, [ticket]);
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
