// ─── Short-lived media ticket cache ─────────────────────────────────────────
// Phase 4 security hardening: an <img>/<video> src can't send an Authorization
// header, so it has to carry a credential in the URL as `?token=`. Previously
// that was the long-lived session JWT — which then lands in access logs and
// browser history. Now it's a short-TTL, single-purpose ticket
// (`POST /api/v1/auth/media-ticket`, ~120s, `purpose="media"`), fetched with
// the real JWT and cached here so the evidence/video URL helpers can stay
// synchronous. The cache auto-refreshes well before expiry.
//
// Phase "final hardening": on a HARD page reload (not SPA navigation) this
// module's cache resets to empty, since it is plain JS module state. A
// component that renders `<img src={evidenceUrl(id)}>` on its very first
// render — before the async ensureMediaTicket() below has resolved — used
// to fire that request with NO ?token= at all, get a real 401 from the
// backend (never a security bug: it correctly refused an absent
// credential), and several call sites (IncidentDetailPage, CaseDetailPage,
// EvidenceModal, the investigation workspace) had an `onError` handler
// that set a PERMANENT "failed" flag with no retry — so the evidence image
// stayed showing "unavailable" for the rest of that page's lifetime, not
// just for one console warning. `useMediaTicket()` below fixes this: it
// gives components a REACTIVE ticket value that re-renders them the
// moment a ticket actually becomes available, so nothing renders an <img>
// tag until it has a real credential to send. This does not weaken
// authentication in any way and does not change the ticket's TTL/scope —
// it only changes WHEN a component asks for one.
import { useEffect, useState } from "react";
import { http, getToken } from "./api.js";

let _ticket = "";
let _expEpochMs = 0;
let _inflight = null;
let _timer = null;
const _listeners = new Set();

function _notifyListeners() {
  _listeners.forEach((fn) => {
    try { fn(); } catch { /* a subscriber's own error must never break the others */ }
  });
}

const SKEW_MS = 15_000; // refresh this long before the server-stated expiry

function _scheduleRefresh(expiresInSec) {
  if (_timer) clearTimeout(_timer);
  const delay = Math.max(5_000, expiresInSec * 1000 - SKEW_MS);
  _timer = setTimeout(() => {
    // fire-and-forget; ignore failures (next ensure() call retries)
    ensureMediaTicket().catch(() => {});
  }, delay);
}

/** Return a valid media ticket, fetching/refreshing if needed. */
export async function ensureMediaTicket() {
  if (!getToken()) {
    clearMediaTicket();
    return "";
  }
  if (_ticket && Date.now() < _expEpochMs - SKEW_MS) return _ticket;
  if (_inflight) return _inflight;

  _inflight = http
    .post("/auth/media-ticket")
    .then(({ data }) => {
      _ticket = data?.ticket || "";
      const ttl = Number(data?.expires_in) || 120;
      _expEpochMs = Date.now() + ttl * 1000;
      _scheduleRefresh(ttl);
      _notifyListeners();
      return _ticket;
    })
    .catch((err) => {
      clearMediaTicket();
      throw err;
    })
    .finally(() => {
      _inflight = null;
    });

  return _inflight;
}

/** React hook: a REACTIVE media ticket -- "" until a real one is available,
 * then the actual ticket string, re-rendering the calling component
 * exactly when that happens. Use this to gate any <img>/<video> render
 * that depends on evidenceUrl()/mockVideoUrl() having a real ?token=,
 * instead of calling currentMediaTicket() once at render time (which can
 * be "" for the component's entire lifetime after a hard page reload,
 * since this module's cache is plain JS state that a hard reload clears --
 * see this file's top-of-file comment). */
export function useMediaTicket() {
  const [ticket, setTicketState] = useState(currentMediaTicket());

  useEffect(() => {
    let alive = true;
    const listener = () => { if (alive) setTicketState(currentMediaTicket()); };
    _listeners.add(listener);
    if (!ticket) {
      ensureMediaTicket().then((t) => { if (alive && t) setTicketState(t); }).catch(() => {});
    }
    return () => {
      alive = false;
      _listeners.delete(listener);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return ticket;
}

/** Synchronous read of the currently-cached ticket ("" if none yet). */
export function currentMediaTicket() {
  if (_ticket && Date.now() < _expEpochMs) return _ticket;
  return "";
}

export function clearMediaTicket() {
  _ticket = "";
  _expEpochMs = 0;
  if (_timer) {
    clearTimeout(_timer);
    _timer = null;
  }
  _notifyListeners();
}

/** One-shot exchange of the session JWT for a ~60s WebSocket handshake
 *  ticket (`purpose="ws"`). Not cached — the WS client asks for a fresh one
 *  on every (re)connect. */
export async function fetchWsTicket() {
  if (!getToken()) return "";
  const { data } = await http.post("/auth/ws-ticket");
  return data?.ticket || "";
}
