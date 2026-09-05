// ─── Short-lived media ticket cache ─────────────────────────────────────────
// Phase 4 security hardening: an <img>/<video> src can't send an Authorization
// header, so it has to carry a credential in the URL as `?token=`. Previously
// that was the long-lived session JWT — which then lands in access logs and
// browser history. Now it's a short-TTL, single-purpose ticket
// (`POST /api/v1/auth/media-ticket`, ~120s, `purpose="media"`), fetched with
// the real JWT and cached here so the evidence/video URL helpers can stay
// synchronous. The cache auto-refreshes well before expiry.
import { http, getToken } from "./api.js";

let _ticket = "";
let _expEpochMs = 0;
let _inflight = null;
let _timer = null;

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
}

/** One-shot exchange of the session JWT for a ~60s WebSocket handshake
 *  ticket (`purpose="ws"`). Not cached — the WS client asks for a fresh one
 *  on every (re)connect. */
export async function fetchWsTicket() {
  if (!getToken()) return "";
  const { data } = await http.post("/auth/ws-ticket");
  return data?.ticket || "";
}
