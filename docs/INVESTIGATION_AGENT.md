# AI Investigation Agent (Phase 14 §7) + Gap Detection (§8)

Upgrades the single-shot Copilot (`/ai/investigate`) into a controlled
**multi-step investigation assistant**. The single-shot endpoint is
unchanged; this is `/ai/investigation/run`.

```
officer query ("Investigate GJ18TC0450")
   │
   ▼  Tool Planner  (deterministic; optional LLM only re-orders/subsets)
ordered plan of VALIDATED tool calls
   │
   ▼  execute step by step against the existing indexed DB paths
per-step results
   │
   ▼  reasoning / aggregation
evidence-grounded structured report + investigation gaps
```

---

## 1. Hard guarantees (enforced in code, not just documented)

- **READ-ONLY.** Every registered tool is a bounded `SELECT`. The agent
  performs **no** INSERT / UPDATE / DELETE, creates **no** alerts, and
  runs **no** arbitrary SQL. `test_investigation_agent.py` asserts the
  alert / incident / anomaly counts are unchanged after a run.
- **Strict registry.** The agent can only call tools in `ToolRegistry`.
  `registry.call("run_raw_sql", …)` raises `KeyError` (test-asserted).
- **LLM never touches data.** If `AI_LLM_PROVIDER=openai`, the model may
  only *pick tool names* from the registry; it never sees or writes SQL,
  never receives raw table access. Any error → the deterministic plan.
- **Nothing fabricated.** Every figure comes from a tool result; an empty
  result is reported as *"not available in recorded evidence"*. Confidence
  is `0.0` for an unknown plate.
- **Step cap.** At most `AI_AGENT_MAX_STEPS` (14) tool calls per run.

## 2. Tool registry

| Tool | Backing |
| :--- | :--- |
| `search_vehicle` · `get_vehicle_journey` · `search_cameras` · `search_alerts` · `search_incidents` · `search_cases` · `search_evidence` · `search_watchlist` | `InvestigationTools` (Phase 12) |
| `search_similar_vehicles` | `VehicleReIDService.find_similar` (Phase 14 §1) |
| `analyze_correlation` | `VehicleCorrelationService.analyze_plate_journey` (§2) |
| `search_anomalies` | bounded `anomaly_events` read (§4/§6) |
| `traffic_analysis` | `TrafficAnalyticsService.overview` (§4) |
| `detect_gaps` | `InvestigationGapService.detect` (§8) |

## 3. Deterministic plan (a plate query)

`search_vehicle → get_vehicle_journey → search_similar_vehicles →
analyze_correlation → search_alerts → search_anomalies → search_incidents →
search_cases → search_evidence → detect_gaps`.

Steps whose prerequisite is missing (e.g. no plate) are recorded as
`skipped` with a reason. The report lists every step + its one-line
`result_summary`.

## 4. Report structure (`AgentRunResponse`)

`summary` · `sections[]` (Vehicle & journey, Visual matches, Cross-camera
correlation, Alerts, Behaviour anomalies, Incidents, Cases, Evidence) ·
`gaps[]` · `related[]` (clickable INCIDENT / CASE / ALERT links) ·
`steps[]` · `plan_source` (`deterministic` | `llm`) · `confidence_*` ·
`read_only: true` · `disclaimer`.

## 5. Investigation Gap Detection (§8)

`GET /ai/investigation/gaps?plate=` → `InvestigationGapService.detect`:

| Gap kind | Trigger |
| :--- | :--- |
| `SINGLE_SIGHTING` | only one sighting — no corroboration |
| `LOW_CONFIDENCE_ANPR` | a sighting's `confidence_score < 0.55` |
| `LONG_TIME_GAP` | > `GAP_LONG_INTERVAL_SECONDS` (45 min) unobserved between two sightings |
| `MISSING_COVERAGE` | > `GAP_MISSING_COVERAGE_METERS` (2.5 km) hop with camera(s) on the path that recorded nothing |
| `CAMERA_OFFLINE_WINDOW` | such a path camera was `OFFLINE` (per `camera_health_history`) during the interval |
| `INCONSISTENT_TRAVEL` | the hop's travel time is `IMPOSSIBLE` / `SLOW` vs the transition baseline (§3) |

> **"This is not an accusation. It is an evidence/coverage warning."**
> Each gap carries a `severity` (low/medium/high), a `description`, and the
> `evidence_event_ids` it is derived from.

## 6. API

| Endpoint | Auth | Notes |
| :--- | :--- | :--- |
| `POST /api/v1/ai/investigation/run` | any auth | body `{query, plate?}`. Threadpool-run. Audited `AI_INVESTIGATION_AGENT`. 503 if `AI_AGENT_ENABLED=false`. |
| `GET /api/v1/ai/investigation/gaps?plate=` | any auth | standalone gap detection |

## 7. Frontend

`/copilot` gains a **DEEP** toggle (also auto-triggered by the word
"investigate"). A deep query renders `AgentReportCard`: `READ-ONLY` chip,
confidence badge, summary, the section grid, an **INVESTIGATION GAPS** block
("evidence/coverage warnings, not accusations"), related-entity links, a
collapsible **agent steps** trace, and the disclaimer.

## 8. Tests

`backend/tests/test_investigation_agent.py` (13): multi-step tool run,
no-plate honest, unknown-plate honest (confidence 0.0), read-only
(counts unchanged), registry rejects unknown tool; gap detection —
single-sighting, low-confidence ANPR, impossible travel, missing coverage,
no-sightings; run endpoint + audit, gaps endpoint, auth 401.

## 9. Limitations

- The deterministic planner is fixed-order; the optional LLM planner only
  re-orders / subsets it (it cannot invent a step).
- `MISSING_COVERAGE` uses a straight-line corridor test, not a road graph.
- `CAMERA_OFFLINE_WINDOW` needs `camera_health_history` rows — only present
  once a real ONLINE↔OFFLINE transition has been recorded.
