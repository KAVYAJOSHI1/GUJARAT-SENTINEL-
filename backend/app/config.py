"""
Central application configuration.
All values are overridable via environment variables / .env file.
"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- App ---
    APP_NAME: str = "SENTINEL Backend"
    ENV: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+psycopg2://sentinel:sentinel@localhost:5432/sentinel"
    )
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    # Recycle a pooled connection after this many seconds so a connection
    # silently dropped by Postgres / a proxy / a firewall idle-timeout is
    # replaced before it's handed to a request (pool_pre_ping already
    # catches most of these; this bounds the worst case). 0 disables.
    DB_POOL_RECYCLE_SECONDS: int = 1800
    # Server-side per-statement ceiling (ms) -- a runaway analytics/search
    # query is cancelled instead of holding a pooled connection forever.
    # 0 disables (Postgres default: no limit).
    DB_STATEMENT_TIMEOUT_MS: int = 15000

    # --- Security / JWT ---
    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8

    # --- Login rate limiting ---
    # In-process (per backend replica) failure counter on POST /auth/login.
    # After MAX_FAILURES failed attempts for the same (client-ip, username)
    # within WINDOW_SECONDS, further attempts for that key get 429 for
    # BLOCK_SECONDS. A successful login clears the counter. Distributed
    # (cross-replica) rate limiting is ROADMAP -- see SECURITY.md.
    LOGIN_RATE_LIMIT_ENABLED: bool = True
    LOGIN_RATE_LIMIT_MAX_FAILURES: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300
    LOGIN_RATE_LIMIT_BLOCK_SECONDS: int = 300

    # --- Short-lived, single-purpose tickets ---
    # A browser WebSocket handshake and an <img>/<video> src cannot send an
    # Authorization header, so those transports use a short-TTL, purpose-
    # scoped ticket (issued from a JWT-authenticated POST) instead of the
    # long-lived session JWT ever appearing in a URL or a WS subprotocol.
    WS_TICKET_TTL_SECONDS: int = 60
    MEDIA_TICKET_TTL_SECONDS: int = 120

    # --- Data retention ---
    # vehicle_events older than this are purged by a periodic sweep. Rows
    # referenced by an alert are NEVER purged (the alert, its watchlist
    # entry, and audit_logs are all retained regardless). Set
    # VEHICLE_EVENT_RETENTION_DAYS=0 to disable purging entirely.
    VEHICLE_EVENT_RETENTION_DAYS: int = 30
    RETENTION_SWEEP_INTERVAL_HOURS: int = 24
    RETENTION_SWEEP_ENABLED: bool = True

    # --- Camera health transition watcher (Phase 11) ---
    # The in-process background task that turns "a camera went silent" into a
    # real camera_health_history row + a CAMERA_OFFLINE/RECOVERED
    # notification. Off during the test suite (health transitions are
    # exercised directly). Safe to run in every replica -- the dedup check
    # against the last history row is idempotent.
    CAMERA_HEALTH_WATCH_ENABLED: bool = True
    CAMERA_HEALTH_WATCH_INTERVAL_S: int = 30

    # --- MinIO ---
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "sentinel-evidence"
    MINIO_SECURE: bool = False

    # --- Local fallback storage ---
    LOCAL_EVIDENCE_FALLBACK_DIR: str = "./data/evidence_fallback"

    # --- Watchlist / Alert engine ---
    ALERT_COOLDOWN_SECONDS: int = 300

    # --- Phase 12: AI intelligence layer ---
    # The whole AI layer works with NO external LLM. "deterministic" =
    # rule-based intent/entity extraction + templated answers (the default,
    # always available). "openai" = optional; requires OPENAI_API_KEY and
    # falls back to deterministic on any error. The LLM never gets DB access
    # or generates SQL -- it only picks from a fixed set of validated tools.
    AI_LLM_PROVIDER: str = "deterministic"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TIMEOUT_S: float = 20.0
    # Hard ceiling on rows any AI tool / copilot answer will pull from the DB.
    AI_MAX_RESULTS: int = 100

    # Stopped/loitering vehicle anomaly (BehaviorAnalyticsService). Operates
    # on stored ByteTrack vehicle_events -- never re-processes video.
    ANOMALY_STOPPED_MIN_SECONDS: int = 120
    ANOMALY_STOPPED_MIN_DETECTIONS: int = 6
    ANOMALY_STOPPED_MAX_DISPLACEMENT_M: float = 25.0
    ANOMALY_PRIORITY: str = "MEDIUM"
    ANOMALY_LOOKBACK_HOURS: int = 24

    # Phase 14 §6: wrong-way movement. A track whose net heading is >=
    # MIN_ANGLE_DEG off the camera's permitted_direction_deg, over >=
    # MIN_DISTANCE_M and >= MIN_DETECTIONS geolocated sightings.
    ANOMALY_WRONGWAY_MIN_ANGLE_DEG: float = 120.0
    ANOMALY_WRONGWAY_MIN_DISTANCE_M: float = 25.0
    ANOMALY_WRONGWAY_MIN_DETECTIONS: int = 3
    # Phase 14 §6: restricted-zone entry. >= MIN_INSIDE geolocated sightings
    # of a track fall inside a camera's restricted_zones polygon.
    ANOMALY_ZONE_MIN_INSIDE: int = 2
    # Periodic in-process scan of recent events for stopped vehicles. Off in
    # the test suite (behaviour is exercised directly). When government feeds
    # resume, new events flow through the existing ingest -> this scan picks
    # them up with no code change.
    AI_ANOMALY_SCAN_ENABLED: bool = True
    AI_ANOMALY_SCAN_INTERVAL_S: int = 300

    # Seed a deterministic AI demo dataset on first boot (idempotent) so the
    # AI features are demonstrable from `docker compose up` with no live
    # CCTV. Set by docker-compose; default off for plain / test runs.
    SEED_AI_DEMO: bool = False

    # --- Phase 15A: camera playback ---
    STREAM_LOW_FPS: float = 8.0        # below this a live source is DEGRADED

    # --- Phase 14: Vehicle Visual Re-ID ---
    # Appearance embedding backend: "attribute" (default -- deterministic,
    # no ML deps, always available) or "torch" (ResNet-50 on the crop, only
    # if torch/torchvision import -- the AI pipeline container). An upgraded
    # pipeline may also POST a precomputed `embedding[]` on the ingest event,
    # which is always stored verbatim regardless of this setting.
    REID_EMBEDDING_BACKEND: str = "attribute"
    # Phase 15E alias -- REID_BACKEND=attribute|torch. When set to "torch"
    # and torch/torchvision/PIL import, a CNN backbone is used; otherwise it
    # silently falls back to the attribute baseline (see GET /ai/reid/status).
    REID_BACKEND: str = "attribute"
    REID_TORCH_MODEL: str = "mobilenet_v3_small"   # mobilenet_v3_small | resnet50
    # Index an embedding for every ingested vehicle_event (best-effort, never
    # blocks ingest). Off in the test suite.
    REID_AUTO_INDEX: bool = True
    # Hard ceiling on rows a single similarity scan will load + compare.
    REID_MAX_CANDIDATES: int = 500
    # Max events one /ai/reid/backfill call will index.
    REID_BACKFILL_BATCH: int = 500
    # Cosine-similarity band thresholds. STRONG never means "confirmed" --
    # only a deterministic plate match does (correlation layer, Phase 14 §2).
    # STRONG is set high on purpose: with the attribute baseline, only
    # (near-)plate-identical vectors reach it. Same type+colour, different
    # vehicle lands at MODERATE ("a plausible lead"), never STRONG.
    REID_SIMILARITY_STRONG: float = 0.96
    REID_SIMILARITY_MODERATE: float = 0.80
    REID_SIMILARITY_WEAK: float = 0.65

    # --- Phase 14: Camera Transition Intelligence (§3) ---
    # Statistical travel-time baselines between camera pairs, from existing
    # vehicle_events (NOT ML). Recomputed by a slow background task + on
    # demand. Off in the test suite.
    CAMERA_TRANSITION_RECOMPUTE_ENABLED: bool = True
    CAMERA_TRANSITION_RECOMPUTE_INTERVAL_S: int = 3600
    CAMERA_TRANSITION_LOOKBACK_DAYS: int = 30
    CAMERA_TRANSITION_MAX_EVENTS: int = 50000
    CAMERA_TRANSITION_MIN_SAMPLES: int = 2
    CAMERA_TRANSITION_MAX_HOP_SECONDS: int = 3 * 3600
    CAMERA_TRANSITION_TOPN: int = 5
    # distance fallback model (urban) when there is no history
    CAMERA_TRANSITION_MODEL_MAX_KMH: float = 60.0
    CAMERA_TRANSITION_MODEL_MIN_KMH: float = 8.0   # crawling urban congestion
    CAMERA_TRANSITION_FAST_FACTOR: float = 0.7      # < 0.7 * typical_min -> FAST
    CAMERA_TRANSITION_IMPOSSIBLE_FACTOR: float = 4.0  # > 4 * typical_max -> hard cap

    # --- Phase 14: Traffic Analytics (§4, §5) ---
    # All SQL aggregates over existing vehicle_events -- no video reprocessing.
    TRAFFIC_TOPN: int = 10
    TRAFFIC_CONGESTION_MODERATE_PER_HOUR: float = 40.0
    TRAFFIC_CONGESTION_HIGH_PER_HOUR: float = 120.0

    # --- Phase 14: Cross-Camera Correlation (§2) ---
    # Explainable weighted score. Weights need not sum to 1 -- the overall is
    # normalised by the sum of the weights actually present.
    CORRELATION_W_PLATE: float = 0.40
    CORRELATION_W_APPEARANCE: float = 0.18
    CORRELATION_W_TEMPORAL: float = 0.18
    CORRELATION_W_GEOGRAPHIC: float = 0.12
    CORRELATION_W_TYPE: float = 0.07
    CORRELATION_W_COLOR: float = 0.05
    CORRELATION_CONF_MEDIUM: float = 0.72
    CORRELATION_CONF_LOW: float = 0.5
    CORRELATION_GEO_NEAR_M: float = 800.0
    CORRELATION_GEO_FAR_M: float = 8000.0

    # --- Phase 14: Investigation Graph (§12) ---
    GRAPH_MAX_NODES: int = 250
    GRAPH_MAX_EDGES: int = 500
    GRAPH_MAX_DETECTIONS: int = 60
    GRAPH_MAX_VISUAL_MATCHES: int = 6
    GRAPH_MAX_BRANCH: int = 25

    # --- Phase 14: Camera Reliability Intelligence (§9) ---
    # Statistics over camera_health_history -- NOT failure prediction.
    CAMERA_RELIABILITY_WINDOW_HOURS: int = 24
    CAMERA_RELIABILITY_FPS_FLOOR: float = 5.0
    CAMERA_RELIABILITY_RECONNECT_WARN: int = 3
    CAMERA_RELIABILITY_DISCONNECT_PENALTY: float = 12.0
    CAMERA_RELIABILITY_SLOW_RECOVERY_S: float = 300.0
    CAMERA_RELIABILITY_MIN_BASELINE_DETECTIONS: int = 20
    CAMERA_RELIABILITY_HIGH_SCORE: float = 80.0
    CAMERA_RELIABILITY_MEDIUM_SCORE: float = 55.0

    # --- Phase 14: Investigation Agent (§7) + Gap Detection (§8) ---
    AI_AGENT_ENABLED: bool = True
    AI_AGENT_MAX_STEPS: int = 14            # hard ceiling on tool calls per run
    GAP_LONG_INTERVAL_SECONDS: int = 45 * 60
    GAP_MISSING_COVERAGE_METERS: float = 2500.0
    GAP_PATH_CORRIDOR_METERS: float = 1500.0

    # --- AI event ingestion ---
    # Shared secret the AI pipeline sends as the `X-Ingest-Key` header on
    # POST /api/v1/events/ai-detection. When unset, that endpoint also
    # accepts a normal operator JWT. Set this in any real deployment.
    INGEST_API_KEY: Optional[str] = None
    # Auto-onboard a camera the first time an event references an unknown code.
    INGEST_AUTO_ONBOARD_CAMERAS: bool = True

    # --- CORS ---
    # Explicit allow-list. "*" is honoured ONLY when ENV is a development
    # value (see resolved_cors_origins()); in any other environment a "*"
    # entry is dropped and a warning is logged, so a stray wildcard never
    # ships to production. The frontend normally reaches the API same-origin
    # through the Vite/prod proxy, so this list only matters for direct
    # cross-origin API access (tooling, a separately-hosted dashboard).
    CORS_ALLOW_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def is_dev_env(self) -> bool:
        return self.ENV.strip().lower() in {"dev", "development", "local", "test", "testing"}

    def resolved_cors_origins(self) -> list[str]:
        """CORS origins with "*" stripped outside a development environment."""
        origins = list(self.CORS_ALLOW_ORIGINS or [])
        if "*" in origins and not self.is_dev_env():
            import logging

            logging.getLogger("sentinel.config").warning(
                "CORS_ALLOW_ORIGINS contains '*' but ENV=%s is not a development "
                "environment -- dropping the wildcard. Set an explicit origin list.",
                self.ENV,
            )
            origins = [o for o in origins if o != "*"]
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
