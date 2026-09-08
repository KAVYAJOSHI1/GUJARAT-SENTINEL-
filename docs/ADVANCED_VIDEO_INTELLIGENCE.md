# Advanced Video Intelligence (Phase 14) + Real Video Hardening (Phase 15)

> **Phase 15** builds on this: a real camera-playback abstraction with
> honest LIVE/DEGRADED/RECORDED/OFFLINE labelling, an ANPR quality pipeline
> that reports *why* a plate is UNKNOWN, character-level temporal fusion, a
> 3-panel live investigation workspace, a real Torch Re-ID backend +
> `/ai/reid/status`, a camera **video-quality** axis, `/system/metrics/summary`
> observability, an `/anpr-intelligence` dashboard, and a DEMO/MOCK/REAL
> feed-source abstraction. See `REAL_VIDEO_PIPELINE.md`, `ANPR_PIPELINE.md`,
> `LIVE_INVESTIGATION.md` and `SYSTEM_STATUS.md` §N.


The next-generation intelligence layer over the stable Sentinel platform.
**Additive throughout** — no change to ANPR / RTSP ingestion / worker
strategy / watchlist→alert / security. When government feeds return, every
feature consumes the same `vehicle_events` with no code change.

| # | Capability | Doc |
| :-- | :--- | :--- |
| 1 | **Vehicle Visual Re-ID** — pluggable appearance embedding + bounded cosine search | [`VEHICLE_REID.md`](VEHICLE_REID.md) |
| 2 | **Cross-Camera Correlation** — explainable 6-signal weighted score, CONFIRMED vs INFERRED | [`CROSS_CAMERA_INTELLIGENCE.md`](CROSS_CAMERA_INTELLIGENCE.md) |
| 3 | **Camera Transition Intelligence** — historical travel-time baselines | [`CROSS_CAMERA_INTELLIGENCE.md`](CROSS_CAMERA_INTELLIGENCE.md) §1 |
| 4 | **Traffic Intelligence** — volume / flow / trend / congestion (SQL aggregates) | [`TRAFFIC_INTELLIGENCE.md`](TRAFFIC_INTELLIGENCE.md) |
| 5 | **GIS Heatmap** — vehicle / alert / anomaly / incident density | [`TRAFFIC_INTELLIGENCE.md`](TRAFFIC_INTELLIGENCE.md) §2 |
| 6 | **Expanded Behaviour Analytics** — wrong-way + restricted-zone detectors | [`BEHAVIOR_ANALYTICS.md`](BEHAVIOR_ANALYTICS.md) |
| 7 | **AI Investigation Agent** — controlled multi-step, tool-planned, read-only | [`INVESTIGATION_AGENT.md`](INVESTIGATION_AGENT.md) |
| 8 | **Investigation Gap Detection** — evidence / coverage warnings | [`INVESTIGATION_AGENT.md`](INVESTIGATION_AGENT.md) §5 |
| 9 | **Camera Reliability Intelligence** — stability score from health history | [`CAMERA_RELIABILITY.md`](CAMERA_RELIABILITY.md) |
| 12 | **Investigation Graph** — deterministic, from persisted rows | this doc §4 |

---

## 1. Architecture

```
                       vehicle_events  (the single source of truth — unchanged)
                             │
   ┌─────────────────────────┼───────────────────────────────────────────┐
   ▼                         ▼                        ▼                   ▼
Re-ID index          Camera transition        Traffic aggregates    Behaviour scan
(vehicle_embeddings)  (camera_transition_stats)  (SQL, no store)     (anomaly_events)
   │                         │                        │                   │
   └──────────┬──────────────┘                        │                   │
              ▼                                        │                   │
   Cross-camera correlation ◄───────────────────────── journey ───────────┤
   (explainable weighted score)                                           │
              │                                                           ▼
              ▼                                                   alerts → incidents
   AI Investigation Agent  ──►  Tool Registry (13 bounded read-only tools)
   (multi-step, deterministic-first)          │
              │                               ├─► Investigation Gap Detection
              ▼                               └─► Investigation Graph
   evidence-grounded structured report
```

## 2. New database objects (all additive)

| Migration | Object |
| :--- | :--- |
| `0009` | `vehicle_embeddings` (JSON vector + metadata; unique per event) |
| `0010` | `camera_transition_stats` (travel-time distribution per ordered camera pair) |
| `0011` | `anomalykind` += `WRONG_WAY`, `RESTRICTED_ZONE`; `anomaly_events` += `zone_name` / `direction_deg` / `expected_direction_deg`; dedup index keyed on `kind`; `cameras` += `permitted_direction_deg` + `restricted_zones` (JSON, NULL default) |

Traffic, correlation, the agent, gap detection, camera reliability and the
graph are **pure read layers** — no schema of their own.

## 3. Models / libraries

- **No ML libraries in the backend image.** Re-ID default backend is a
  deterministic attribute embedding (pure Python). An optional
  `TorchReIDBackend` (ResNet-50) activates only where `torch` imports (the
  AI-pipeline container) and falls back silently.
- **No pgvector** on `postgis:15-3.3` → a repository abstraction does
  bounded brute-force cosine similarity.
- **No Neo4j** → the investigation graph is built from relational rows.
- **No ML forecasting** → camera reliability and transition intelligence
  are plain statistics.

## 4. Investigation Graph (§12)

`InvestigationGraphService.build_for_plate(plate)` → deterministic
`{nodes[], edges[]}` from persisted rows only:

```
Vehicle ─detected_as► Detection ─at_camera► Camera ─located_at► Location
                          │                    │
                          │                    └─transition► Camera
                          ▼
Vehicle ─raised_alert► Alert ─promoted_to► Incident ─has_evidence► Evidence
                          │                    │
                          │                    └─part_of_case► Case
                          └─from_anomaly► AnomalyEvent
Vehicle ─visual_match► Vehicle           Vehicle ─on_watchlist► Watchlist
```

Every node carries an `href` to its Sentinel page. Bounded by
`GRAPH_MAX_NODES` / `GRAPH_MAX_EDGES`. `GET /api/v1/ai/graph?plate=`.
Frontend: `/graph` — BFS-layered SVG, click a node to open it.

## 5. API surface (`/api/v1/...`, all JWT-authenticated, bounded)

```
POST /ai/reid/search · /compare            GET  /ai/reid/embedding/{id}   POST /ai/reid/backfill
POST /ai/correlation/analyze               GET  /ai/correlation/transitions[/{code}/neighbours]
                                           POST /ai/correlation/transitions/recompute
GET  /analytics/traffic/overview · /cameras · /trends · /heatmap
POST /ai/anomalies/scan  (kinds=[...])     GET  /ai/anomalies
PATCH /cameras/{id}/behavior-config
POST /ai/investigation/run                 GET  /ai/investigation/gaps
GET  /ai/camera-intelligence[/{code}]
GET  /ai/graph
```

Audited actions: `AI_REID_SEARCH`, `AI_REID_BACKFILL`,
`AI_CORRELATION_ANALYZE`, `AI_TRANSITION_RECOMPUTE`, `AI_ANOMALY_SCAN`,
`CAMERA_BEHAVIOR_CONFIG`, `AI_INVESTIGATION_AGENT`.

## 6. Security (unchanged posture)

JWT + RBAC + append-only audit + bounded queries everywhere. The AI is
**read-only by default**; the investigation agent's registry is a strict
allow-list of bounded `SELECT`s; the LLM (optional) only picks tool names,
never touches the DB, never generates SQL. `OPENAI_API_KEY` stays
server-side; no secret / RTSP credential is ever returned or logged.

## 7. Performance

`SCALE_TO_80000.md` still applies. Additions: Re-ID indexes best-effort
after commit (never blocks ingest) and caps every scan at
`REID_MAX_CANDIDATES`; transition + traffic + reliability are SQL
aggregates on the covering indexes; the agent caps at `AI_AGENT_MAX_STEPS`;
the graph is bounded. No Kafka / K8s / vector DB / heavy model was added.

## 8. Tests

`test_reid.py` (13) · `test_correlation.py` (14) · `test_traffic.py` (10) ·
`test_behavior_expanded.py` (12) · `test_investigation_agent.py` (13) ·
`test_camera_reliability.py` (9) · `test_investigation_graph.py` (6) — plus
the full pre-existing suite green.
