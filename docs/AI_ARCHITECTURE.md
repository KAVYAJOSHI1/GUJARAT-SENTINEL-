# SENTINEL — AI Intelligence Layer (Phase 12)

**Status:** implemented + tested (2026-09-08). Deterministic-first; no external
LLM required. Migration `0008`. Commit — see `SYSTEM_STATUS.md` §K.

---

## 1. Where it sits

```
Government CCTV  ─┐
Mock / demo feeds ┼─► Existing Ingestion ─► YOLO / ByteTrack / ANPR ─► vehicle_events
Seeded demo data ─┘                                                        │
                                                                           ▼
                                                    ┌──────────────────────────────────┐
                                                    │        AI INTELLIGENCE LAYER      │
                                                    │  (read-only over existing rows)   │
                                                    │  · Investigation Copilot          │
                                                    │  · Natural-language search        │
                                                    │  · Incident / Case AI summary     │
                                                    │  · Stopped-vehicle anomaly        │
                                                    └──────────────────────────────────┘
                                                                           │
             watchlist ─► alerts ─► incidents ─► evidence ─► cases ─► journey / GIS ─► audit
```

The AI layer **adds no new ingestion path**. It reads the same
`vehicle_events` / `alerts` / `incidents` / `cases` / `watchlist` /
`camera` rows every other module uses. When government feeds resume, new
events arrive through the unchanged ingest and the AI features pick them up
with **no code change** (the anomaly scan is a periodic read; Copilot &
search are on-demand reads).

## 2. Components

| Module | File | Purpose |
| :--- | :--- | :--- |
| NL query parser | `app/services/ai/nlq.py` | Deterministic intent + entity extraction. Shared by Copilot and NL search. No LLM, no DB. |
| Controlled tools | `app/services/ai/tools.py` | `InvestigationTools` — 9 named, parameter-validated, bounded read functions over the existing indexed queries. The **only** way AI touches data. |
| LLM provider | `app/services/ai/llm.py` | `LLMProvider` ABC · `DeterministicProvider` (default) · `OpenAIProvider` (optional, `httpx`, falls back on any error). |
| Copilot | `app/services/ai/copilot.py` | `InvestigationCopilotService` — parse → tool → aggregate → confidence → grounded answer. |
| Summaries | `app/services/ai/summary.py` | `build_incident_summary` / `build_case_summary` — deterministic structured summary + gaps. |
| Behaviour | `app/services/ai/behavior.py` | `BehaviorAnalyticsService.scan_stopped_vehicles` — the one anomaly detector; feeds the existing alert architecture. |
| Confidence | `app/services/ai/confidence.py` | FACT vs INFERENCE, `HIGH/MEDIUM/LOW/INSUFFICIENT`. |
| API | `app/api/v1/ai.py` | `/api/v1/ai/*` — all JWT-authenticated, RBAC-checked, audited. |

## 3. LLM safety model (§8)

* **The platform never requires an LLM.** `AI_LLM_PROVIDER=deterministic`
  (the default) is fully functional. `openai` needs `OPENAI_API_KEY`; if the
  key is absent or a call fails, it transparently returns the deterministic
  result.
* **The LLM has no database access and never writes SQL.** It can only
  (a) re-word an answer the backend already fact-checked, using **only** the
  structured facts it is handed, and (b) optionally pick one of the fixed
  `TOOL_SPECS` tools by name. The backend validates every parameter and runs
  the query itself.
* **Prompts are minimal.** The system prompt forbids adding facts; the user
  message carries the question + the already-computed facts (capped at 3 KB).
  Full prompts are not logged.

## 4. Confidence model (§5)

Every AI result carries `confidence_score` (0–1), `confidence_level`
(`HIGH`/`MEDIUM`/`LOW`/`INSUFFICIENT`) and a `match_method` / `reasoning`
string. Rules live in `confidence.py`:

* **Vehicle match** — FACT: exact `plate_number_normalized` sightings.
  INFERENCE: "these belong to one movement" — rises with more sightings
  across more distinct cameras.
* **Anomaly** — INFERENCE that a track is *stopped* vs a slow/congested
  pass — rises with longer dwell, more detections, smaller displacement.

The UI shows an `AI MATCH: HIGH` / `INSUFFICIENT DATA` chip and never
presents inference as confirmed fact.

## 5. Security (§9)

* Every `/api/v1/ai/*` endpoint requires a valid JWT.
* Copilot / NL search / summaries — any authenticated role (read-only).
* Anomaly **scan** and **review** — `ADMIN` / `OFFICER` only.
* Audited actions: `AI_INVESTIGATION`, `AI_SEARCH`, `AI_INCIDENT_SUMMARY`,
  `AI_CASE_SUMMARY`, `AI_ANOMALY_SCAN`, `AI_ANOMALY_REVIEW`.
* No RTSP credentials / JWT secrets / API keys are exposed or logged. The
  `OPENAI_API_KEY` is read from env only, never returned by any endpoint
  (`/ai/status` reports a boolean `llm_available`, not the key).

## 6. Performance (§11)

No Kafka / Kubernetes / cloud / vector DB. All queries are bounded
(`WHERE` + `LIMIT ≤ AI_MAX_RESULTS`, default 100) and use the existing
B-tree / GIN / covering indexes. The anomaly detector runs **one** grouped
aggregate over a bounded lookback window and never touches video.

## 7. Configuration

| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `AI_LLM_PROVIDER` | `deterministic` | `deterministic` \| `openai` |
| `OPENAI_API_KEY` | _unset_ | required only for `openai` |
| `OPENAI_MODEL` | `gpt-4o-mini` | |
| `AI_MAX_RESULTS` | `100` | hard ceiling on any AI query |
| `ANOMALY_STOPPED_MIN_SECONDS` | `120` | dwell threshold |
| `ANOMALY_STOPPED_MIN_DETECTIONS` | `6` | detection-count threshold |
| `ANOMALY_STOPPED_MAX_DISPLACEMENT_M` | `25` | movement ceiling (when GPS present) |
| `AI_ANOMALY_SCAN_ENABLED` | `true` | periodic in-process scan |
| `AI_ANOMALY_SCAN_INTERVAL_S` | `300` | scan cadence |
| `SEED_AI_DEMO` | `false` (compose: `1`) | seed the offline demo dataset |

## 8. Future live-feed activation

Nothing changes. The live pipeline already writes `vehicle_events` with
`track_id`, `latitude`, `longitude`, `vehicle_type`. When feeds resume:

* Copilot / search / summaries immediately reflect the new rows.
* The anomaly scan's next tick includes the new tracks.
* No migration, no new service, no architectural change.

The only future *enhancement* (not required) is populating
`vehicle_events.vehicle_color` from the detector — the column and the
search/Copilot filters already exist.
