# SENTINEL — Cybersecurity, RBAC & Audit Compliance

> **How to read this document:** every line is tagged **IMPLEMENTED** (verified
> in the current `penultimate` branch code) or **ROADMAP** (a production
> target, not yet built). This file previously stated several ROADMAP items
> as if they were already implemented (RS256, AES-256 at rest, an
> "immutable" audit trail) — corrected below per
> `SENTINEL_System_Audit_Report.md` §10/§15/§20. Nothing here is deleted,
> only re-labeled, so the roadmap is still visible as a target.

---

## 1. Security Architecture Matrix

1. **Authentication** — **IMPLEMENTED**: OAuth2-style JWT bearer tokens via
   `python-jose`, **HS256** (a single shared symmetric secret,
   `JWT_SECRET_KEY`), 8-hour session expiry, bcrypt password hashing
   (`backend/app/core/security.py`).
   - **ROADMAP**: RS256 (asymmetric, public/private keypair) signing — not
     implemented; would matter if multiple independently-deployed services
     ever need to verify tokens without holding the signing secret itself.
2. **Role-Based Access Control (RBAC)** — **IMPLEMENTED**: `require_roles()`
   dependency factory enforced on camera CRUD, watchlist writes, and alert
   acknowledgment (`backend/app/core/rbac.py`).
   - `ADMIN`: full system configuration, camera CRUD (including delete),
     watchlist management.
   - `OFFICER`: vehicle search, investigation console, PDF evidence export
     (client-side), alert acknowledgment, watchlist writes, camera
     create/update/sync.
   - `OPERATOR`: real-time dashboard view & alert monitoring only.
3. **WebSocket authentication** — **IMPLEMENTED** (this hardening pass):
   `/ws/alerts` previously accepted any connection with no token check at
   all. It now requires the same JWT the REST API accepts, passed as a
   WebSocket subprotocol (not a `?token=` query string, to avoid the token
   landing in a URL / access log / browser history) — see
   `backend/app/api/ws_alerts.py`. Residual limitation: it is still the same
   long-lived (8h) session JWT, not a short-lived single-use ticket; see
   that module's docstring.
4. **Data Encryption**
   - In-Transit — **ROADMAP / deployment-environment concern**: TLS
     termination (HTTPS/WSS) is not something the application itself does;
     it depends on how a real deployment is fronted (reverse proxy /
     ingress). Nothing in the app code enforces or assumes TLS today.
   - At-Rest — **ROADMAP, not implemented**: evidence snapshot JPEGs are
     stored as plain, unencrypted files in MinIO (or local disk fallback).
     There is no AES-256 (or any) encryption-at-rest anywhere in this
     codebase today.
5. **Audit Logging** — **IMPLEMENTED** (this hardening pass), previously
   ROADMAP: the `audit_logs` table/model existed and was migrated but had
   zero writers. `backend/app/services/audit.py` is now called from login
   (success + failure), vehicle search, alert acknowledgment, watchlist
   create/deactivate, camera create/update/delete/sync, and evidence
   access. It is a normal application-level DB table, **not a
   cryptographically immutable / tamper-evident log** (no hash chaining,
   no WORM storage, no external log shipping) — "immutable" was an
   inaccurate claim in the previous version of this document and has been
   removed. PDF report export is entirely client-side (jsPDF, no server
   round-trip), so it cannot currently be captured by server-side audit
   logging — that would require a server-rendered export endpoint, which
   does not exist.
6. **Ingest authentication** — **IMPLEMENTED**: the AI→backend event
   ingestion endpoint (`POST /api/v1/events/ai-detection`) accepts either a
   shared `X-Ingest-Key` header (constant-time comparison via
   `hmac.compare_digest`) or a normal operator JWT
   (`backend/app/api/deps.py::require_ingest_auth`).
7. **RTSP credential handling** — **IMPLEMENTED**: RTSP usernames/passwords
   come only from environment variables, are injected into the connection
   URL just before use, and are redacted (`***:***@host`) before being
   logged (`ingestion/rtsp_auth.py`).
8. **Rate limiting on `/auth/login`** — **NOT IMPLEMENTED / ROADMAP**: there
   is no `slowapi` or equivalent throttling anywhere in the backend today;
   the login endpoint is brute-forceable as far as the application itself
   is concerned.
9. **Watchlist expiry enforcement** — **IMPLEMENTED** (this hardening
   pass): `watchlist.expires_at` was stored but never checked by the
   matching query. `app/services/watchlist_engine.py::active_watchlist_clause()`
   now excludes expired or inactive entries from both the alert-match
   lookup and the investigation search's "is this plate watchlisted" flag.
10. **CORS** — **IMPLEMENTED, dev-permissive default**: `CORS_ALLOW_ORIGINS`
    defaults to `["*"]` in `docker-compose.yml` — fine for local/hackathon
    demo use, must be tightened to a real origin allowlist before any
    production deployment.

---

## 2. What changed in this hardening pass vs. what's still open

| Item | Before | Now |
| :--- | :--- | :--- |
| `/ws/alerts` auth | none | JWT required (subprotocol transport) |
| Audit logging | table existed, zero writers | wired to 7 sensitive actions (see §1.5) |
| `watchlist.expires_at` | stored, never checked | enforced in the match + search-flag queries |
| Camera status vs. real health | DB column only, never updated by ingestion | `POST /api/v1/cameras/health` + freshness-checked effective status |
| Frontend live/mock/offline labeling | `backendLive` state existed, banner not always distinguishing | explicit OFFLINE/DEMO-DATA banner + per-alert SIMULATED tag + REAL/MOCK camera badges |
| RS256 vs HS256 doc claim | claimed RS256 | corrected to HS256 (actual) |
| AES-256 at rest | claimed implemented | corrected to ROADMAP (not implemented) |
| "Immutable" audit trail | claimed | corrected — normal DB table, not tamper-evident |

**Still open (ROADMAP, not addressed in this pass — out of scope per this
task's brief):** RS256 signing, TLS enforcement in-app, encryption at rest,
rate limiting on `/auth/login`, CORS tightened beyond `["*"]`, a real
labeled ANPR accuracy benchmark (see `README.md` correction), and a
data-retention/expiry policy for `vehicle_events`.
