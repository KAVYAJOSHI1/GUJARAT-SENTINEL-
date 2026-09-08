# Cross-Camera Correlation & Transition Intelligence (Phase 14 §2, §3)

An **explainable intelligence layer over** the existing journey system
(`_build_transitions` in `vehicles.py`) — it does not replace it. The
journey still shows CONFIRMED sightings chained by INFERRED transitions;
this layer scores *how strongly* two sightings correlate and *whether the
travel between them was feasible*.

> **Inference is never silently promoted to fact.** A hop is `CONFIRMED`
> only with an exact plate match **and** a feasible travel time. Everything
> else is `INFERRED` — a lead.

---

## 1. Camera Transition Intelligence (§3)

`camera_transition_stats` (migration `0010`) — one row per ordered camera
pair `A → B` ever seen as a consecutive same-plate hop in `vehicle_events`.
Plain statistics, **no ML**:

| Column | Meaning |
| :--- | :--- |
| `sample_count` | consecutive same-plate hops observed for this pair |
| `min / median / p90 / max / mean _seconds` | travel-time distribution |
| `distance_meters` | straight-line camera distance (both geolocated) |

`CameraTransitionService`:

- **`recompute()`** — walks each plate's sightings in time order, records
  every `A → B` hop (`0 < dt ≤ CAMERA_TRANSITION_MAX_HOP_SECONDS`),
  aggregates per pair with `≥ CAMERA_TRANSITION_MIN_SAMPLES`. Bounded by
  `CAMERA_TRANSITION_MAX_EVENTS`. Idempotent upsert. Runs on a slow
  background loop (`CAMERA_TRANSITION_RECOMPUTE_INTERVAL_S`, default 1 h;
  off in tests), on demand via the API, and in the demo seed.
- **`expected_travel(from, to)`** → a typical band with an explicit
  `source`:
  - `historical` — from the stats (`typical_min = min`, `typical_max = p90`);
  - `distance-model` — no history but both cameras geolocated: haversine ÷
    an urban speed band (`CAMERA_TRANSITION_MODEL_MIN/MAX_KMH`, 12–60 km/h);
  - `unknown` — no history and no geometry.
- **`classify(from, to, observed_seconds)`** → `PLAUSIBLE` /
  `FAST` / `SLOW` / `IMPOSSIBLE` / `UNKNOWN`.
- **`likely_next_cameras(id)` / `likely_previous_cameras(id)`** — the most
  frequent onward / prior hops with their observed share.

Journey transitions (`GET /vehicles/search`) now carry
`transition_classification` + `expected_travel_band` (a cheap stats lookup;
no embeddings computed on the journey path).

## 2. Cross-Camera Correlation (§2)

`VehicleCorrelationService.analyze_pair(a, b)` produces the breakdown the UI
renders:

| Signal | How it is scored |
| :--- | :--- |
| `plate_score` | `1.0` exact normalised match · `0.82` differ by ≤ 1 char (OCR) · `0.35` one/both `UNKNOWN` · `0.0` different |
| `appearance_score` | cosine of the two Re-ID embeddings (Phase 14 §1) |
| `type_score` | `1.0` same · `0.5` one missing · `0.0` different |
| `color_score` | `1.0` same · `0.6` one missing · `0.2` different (colour reads are noisy) |
| `temporal_score` | from `classify()`: PLAUSIBLE `1.0` · SLOW `0.55` · FAST `0.45` · UNKNOWN `0.5` · IMPOSSIBLE `0.05` |
| `geographic_score` | `1.0` ≤ 800 m, decays to `0.3` beyond 8 km |

```
overall_score = Σ(weight_i · score_i) / Σ(weight_i)      # weights need not sum to 1
```

Default weights (`CORRELATION_W_*`): plate 0.40, appearance 0.18, temporal
0.18, geographic 0.12, type 0.07, colour 0.05.

**Verdict / confidence:**

| Condition | verdict | confidence |
| :--- | :--- | :--- |
| exact plate **and** feasible time | `CONFIRMED` | HIGH |
| exact plate but IMPOSSIBLE time | `INFERRED` | LOW |
| `overall ≥ 0.72` | `INFERRED` | MEDIUM |
| `overall ≥ 0.5` | `INFERRED` | LOW |
| else | `INFERRED` | INSUFFICIENT |

`analyze_plate_journey(plate)` runs this for every consecutive hop of a
plate and returns `{confirmed, inferred, hops[]}`.

Every response includes `scores`, `explanations` (one human sentence per
signal), `weights`, `match_method`, and a `disclaimer`.

## 3. API (`/api/v1/ai/correlation/*`, JWT-authenticated)

| Endpoint | Role | Purpose |
| :--- | :--- | :--- |
| `POST /analyze` | any auth | `{event_id_a, event_id_b}` → one `CorrelationBreakdown`; `{plate}` → `CorrelationJourneyResponse`. Audited `AI_CORRELATION_ANALYZE`. |
| `GET /transitions` | any auth | list `camera_transition_stats` (optionally by `camera_code`). |
| `GET /transitions/{code}/neighbours` | any auth | likely next / previous cameras. |
| `POST /transitions/recompute` | ADMIN/OFFICER | rebuild the stats. Audited `AI_TRANSITION_RECOMPUTE`. |

## 4. Config

`CAMERA_TRANSITION_*` (recompute cadence, lookback, min samples, model
speed band, classification factors) and `CORRELATION_W_*` /
`CORRELATION_CONF_*` / `CORRELATION_GEO_*` in `app/config.py`.

## 5. Tests

`backend/tests/test_correlation.py` (14): recompute + classify (PLAUSIBLE /
FAST / IMPOSSIBLE / SLOW), distance-model fallback, unknown-geometry,
likely-next, exact-plate CONFIRMED, impossible-time never CONFIRMED,
different-plate INFERRED, fuzzy plate, plate-journey analysis, endpoint +
audit, plate endpoint, auth 401, recompute RBAC, journey-transition
classification wiring.

## 6. Limitations

- `MIN_SAMPLES` (2) means a brand-new deployment relies on the
  distance-model band until enough hops accrue.
- The correlation `appearance_score` uses the attribute baseline embedding
  unless the `torch` Re-ID backend is enabled — see `VEHICLE_REID.md`.
- No route-graph / road-network model; "geographic" is straight-line only.
- Loopbacks (`A → B → A`) are recorded as two distinct ordered pairs, which
  is correct but can look surprising in the stats table.
