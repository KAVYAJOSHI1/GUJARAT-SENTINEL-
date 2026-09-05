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
3. **WebSocket authentication** — **IMPLEMENTED**: `/ws/alerts` previously
   accepted any connection with no token check at all. It now requires a
   **short-lived, single-purpose WS ticket** (`purpose="ws"`, ~60s TTL,
   config `WS_TICKET_TTL_SECONDS`), obtained from
   `POST /api/v1/auth/ws-ticket` against a valid session JWT and passed as
   the WebSocket subprotocol (`new WebSocket(url, [ticket])` — never a
   `?token=` query string, so it never lands in a URL / access log /
   browser history). The long-lived session JWT is **not** accepted here
   (it carries no `purpose` claim). See `backend/app/api/ws_alerts.py` and
   `backend/app/api/v1/auth.py`.
4. **Data Encryption**
   - In-Transit — **ROADMAP / deployment-environment concern**: TLS
     termination (HTTPS/WSS) is not something the application itself does;
     it depends on how a real deployment is fronted (reverse proxy /
     ingress). Nothing in the app code enforces or assumes TLS today.
   - At-Rest — **ROADMAP, not implemented**: evidence snapshot JPEGs are
     stored as plain, unencrypted files in MinIO (or local disk fallback).
     There is no AES-256 (or any) encryption-at-rest anywhere in this
     codebase today.
5. **Audit Logging** — **IMPLEMENTED**: `backend/app/services/audit.py`
   writes an `audit_logs` row for: login success, login failure, **login
   rate-limited** (Phase 4), vehicle search, alert acknowledgment,
   watchlist create/deactivate, camera create/update/delete/sync, evidence
   access, and **retention purge** (Phase 4). The helper truncates `detail`
   and **never** receives a password, JWT, ticket, or RTSP credential —
   callers pass only already-non-secret fields (usernames, plate numbers,
   ids, counts, status values). It is a normal application-level DB table,
   **not a cryptographically immutable / tamper-evident log** (no hash
   chaining, no WORM storage, no external log shipping). PDF report export
   is entirely client-side (jsPDF, no server round-trip), so it cannot
   currently be captured by server-side audit logging — that would require
   a server-rendered export endpoint, which does not exist.
6. **Ingest authentication** — **IMPLEMENTED**: the AI→backend event
   ingestion endpoint (`POST /api/v1/events/ai-detection`) accepts either a
   shared `X-Ingest-Key` header (constant-time comparison via
   `hmac.compare_digest`) or a normal operator JWT
   (`backend/app/api/deps.py::require_ingest_auth`).
7. **RTSP credential handling** — **IMPLEMENTED**: RTSP usernames/passwords
   come only from environment variables, are injected into the connection
   URL just before use, and are redacted (`***:***@host`) before being
   logged (`ingestion/rtsp_auth.py`).
8. **Rate limiting on `/auth/login`** — **IMPLEMENTED** (Phase 4):
   `backend/app/services/rate_limit.py` counts failed attempts per
   `(client-ip, username)`. After `LOGIN_RATE_LIMIT_MAX_FAILURES` (default
   5) failures within `LOGIN_RATE_LIMIT_WINDOW_SECONDS` (default 300),
   further attempts for that key get **HTTP 429** with a `Retry-After`
   header for `LOGIN_RATE_LIMIT_BLOCK_SECONDS` (default 300); a successful
   login clears the counter. The 429 body is generic — it never reveals
   whether the username exists or echoes the attempted credential. All
   config keys are env-overridable; set `LOGIN_RATE_LIMIT_ENABLED=false` to
   disable.
   - **ROADMAP**: this counter is **per backend process** (in-memory). With
     multiple backend replicas the effective global limit is
     `replicas × MAX_FAILURES`. A shared-store (Redis) limiter that holds
     across replicas is not implemented.
9. **Watchlist expiry enforcement** — **IMPLEMENTED** (this hardening
   pass): `watchlist.expires_at` was stored but never checked by the
   matching query. `app/services/watchlist_engine.py::active_watchlist_clause()`
   now excludes expired or inactive entries from both the alert-match
   lookup and the investigation search's "is this plate watchlisted" flag.
10. **CORS** — **IMPLEMENTED, explicit allow-list**: `CORS_ALLOW_ORIGINS`
    defaults to `["http://localhost:3000", "http://localhost:5173"]` (the
    dev frontend origins) and `docker-compose.yml` sets
    `["http://localhost:3000"]`. A `"*"` wildcard is **honoured only when
    `ENV` is a development value** (`development`/`dev`/`local`/`test`) —
    in any other environment `Settings.resolved_cors_origins()` drops the
    `"*"` and logs a warning, so a stray wildcard can never ship to
    production. When the list *is* `"*"` (dev only), `allow_credentials` is
    forced to `False` per the CORS spec. The dashboard normally reaches the
    API same-origin through the Vite/prod proxy, so this list only affects
    direct cross-origin API access.
11. **Short-lived transport tickets** — **IMPLEMENTED** (Phase 4): browser
    transports that cannot send an `Authorization` header (the WebSocket
    handshake; `<img>`/`<video>` `src`) previously carried the long-lived
    session JWT (as a WS subprotocol or a `?token=` query param), so it
    landed in access logs / browser history. Now:
    - `POST /api/v1/auth/ws-ticket` → `purpose="ws"`, ~60s ticket for the
      alert socket.
    - `POST /api/v1/auth/media-ticket` → `purpose="media"`, ~120s ticket
      for evidence-image / mock-video `?token=`.
    Each ticket is a signed HS256 JWT with a short `exp` and an explicit
    `purpose`; it is accepted **only** by the one transport it names, and a
    normal session JWT passed to those transports is now rejected. The
    `Authorization: Bearer <session JWT>` header path (fetch/XHR) is
    unchanged.
12. **`vehicle_events` data retention** — **IMPLEMENTED** (Phase 4):
    a periodic sweep (`backend/app/services/retention.py`, started from the
    FastAPI lifespan; also `POST /api/v1/admin/retention/purge`, admin-only,
    audit-logged) deletes `vehicle_events` older than
    `VEHICLE_EVENT_RETENTION_DAYS` (default **30**). Rows referenced by an
    `alerts` row are **never** deleted regardless of age; `watchlist`,
    `alerts`, `audit_logs`, `users`, `cameras` are never touched. Set
    `VEHICLE_EVENT_RETENTION_DAYS=0` to disable. Addresses
    `SENTINEL_System_Audit_Report.md` §12's "mass ANPR retention of every
    vehicle movement is a real policy/privacy question".

---

## 2. What changed across the hardening passes vs. what's still open

**Phase 1 pass:**

| Item | Before | Now |
| :--- | :--- | :--- |
| `/ws/alerts` auth | none | authenticated handshake required |
| Audit logging | table existed, zero writers | wired to sensitive actions (see §1.5) |
| `watchlist.expires_at` | stored, never checked | enforced in the match + search-flag queries |
| Camera status vs. real health | DB column only, never updated by ingestion | `POST /api/v1/cameras/health` + freshness-checked effective status |
| Frontend live/mock/offline labeling | not always distinguishing | explicit OFFLINE/DEMO-DATA banner + SIMULATED tag + REAL/MOCK badges |
| RS256 / AES-256 / "immutable audit" doc claims | claimed implemented | corrected to HS256 / ROADMAP / normal DB table |

**Phase 4 pass (this one):**

| Item | Before | Now |
| :--- | :--- | :--- |
| `/auth/login` brute force | no throttle | per-(ip, username) failure counter → 429 + `Retry-After` (§1.8) |
| CORS | `["*"]` in compose | explicit allow-list; `"*"` dropped outside a dev `ENV` (§1.10) |
| WS credential | long-lived session JWT as subprotocol | short-lived `purpose="ws"` ticket (~60s) (§1.3, §1.11) |
| Evidence / mock-video `?token=` | long-lived session JWT in the URL | short-lived `purpose="media"` ticket (~120s) (§1.11) |
| `vehicle_events` retention | grows unbounded | 30-day (configurable) purge, alert-referenced rows protected (§1.12) |
| Audit coverage | login/search/ack/watchlist/camera/evidence | + `LOGIN_RATE_LIMITED`, `RETENTION_PURGE` (§1.5) |

**Still open (ROADMAP):** RS256 (asymmetric) JWT signing; TLS/HTTPS/WSS
enforcement in-app (a reverse-proxy/ingress concern); AES-256 encryption at
rest for evidence blobs; **distributed** (cross-replica, Redis-backed)
login rate limiting — the current limiter is per-process; a real labeled
ANPR accuracy benchmark (see `README.md`); GPU inference and the
Kafka/Kubernetes/Triton statewide architecture in `SCALABILITY.md`.
