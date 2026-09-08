# Live Investigation Workspace (Phase 15D)

A single professional screen for a vehicle investigation, wiring together
everything the platform already computes.

```
┌─────────────────────────────────────────────────────────────┐
│ Investigation Workspace   GJ18TC0450   [WATCHLIST · STOLEN]  │
├──────────────┬───────────────────────────┬──────────────────┤
│ LEFT         │ CENTER                    │ RIGHT            │
│ Vehicle      │ Camera evidence (player)  │ AI investigation │
│ identity     │ Journey map (PostGIS)     │ [Run Investigation]│
│ + filters    │                           │  summary / gaps  │
│              │                           │  anomalies /     │
│              │                           │  evidence /      │
│              │                           │  related / conf  │
├──────────────┴───────────────────────────┴──────────────────┤
│ JOURNEY TIMELINE   ● CAM-01 → ● CAM-02 → ● CAM-04 → ● CAM-08 │
└─────────────────────────────────────────────────────────────┘
```

Route: **`/workspace`** (`?plate=…`). Nav tab: **Workspace**.

---

## 1. Backend — `GET /api/v1/vehicles/profile?plate=`

The consolidated view opened from any search result. Everything derived
**live from persisted rows**, audited `VEHICLE_SEARCH`.

`VehicleProfile`:

| field | source |
| :--- | :--- |
| `total_sightings`, `first_seen`, `last_seen`, `distinct_cameras`, `geolocated_sightings` | `vehicle_events` |
| `vehicle_types`, `vehicle_colors` | most-common over the sightings |
| `is_watchlisted`, `watchlist_category` | active `watchlist` |
| `cameras[]` (`CameraSeen`) | per-camera sighting count + first/last + coords |
| `journey` | `VehicleJourneySummary` (Phase 13/14 — CONFIRMED sightings + INFERRED transitions with distance / speed / `transition_classification`) |
| `anpr_readable`, `anpr_unknown`, `anpr_failure_reasons{}` | Phase 15B `anpr_status` / `anpr_failure_reason` |
| `counts{alerts,incidents,cases,anomalies,evidence}` | direct FK lookups |
| `related[]` (`RelatedRecord`) | clickable ALERT / INCIDENT / CASE links |
| `visual_match_count` | `vehicle_embeddings` rows for the plate |

## 2. Frontend — `LiveInvestigationWorkspace.jsx`

- **LEFT** — identity card: sighting/camera/type/colour counts, ANPR
  readable-vs-unknown split + failure-reason tally, relationship count
  chips, jump-to-full-investigation / graph.
- **CENTER** — `CameraPlayer` for the last camera the vehicle passed
  (honest LIVE/RECORDED/OFFLINE mode, Phase 15A) + a Leaflet journey map
  (dashed polyline through the geolocated cameras, green start / red end).
- **RIGHT** — **[Run Investigation]** calls `POST /ai/investigation/run`
  (the read-only multi-step agent, Phase 14 §7): summary, per-section
  findings, **investigation gaps**, related-entity links, confidence, plan
  source. `READ-ONLY` chip.
- **VISUAL MATCHES** — the `VisualMatchesPanel` (Phase 14 Re-ID).
- **BOTTOM** — journey timeline: `● CAM → ● CAM` with per-transition
  `INFERRED` gap / distance / ~speed / classification, and the standing
  disclaimer *"Camera sightings are CONFIRMED; transitions between them are
  INFERRED (not observed)."*

## 3. Real vehicle search (§4)

The existing Advanced Search (`POST /search/vehicles`) already covers exact
plate, partial plate (trigram), type, colour, camera, date/time,
`min_confidence`, `watchlist_only`, `unknown_only`, `min_duration_seconds`,
`source` REAL/MOCK. Clicking any result opens `/workspace?plate=…` — the
complete investigation view above. Visual-similarity search is its own
surface (`/ai/reid/search`, shown in the workspace's Visual Matches panel).

## 4. Journey replay (§5)

The timeline + map here, plus the richer `JourneyIntelligence` scrubber on
`/investigation`, both consume the **same** `VehicleJourneySummary`
transitions — camera, timestamp, plate confidence, distance, estimated
travel time, `transition_classification` (PLAUSIBLE / FAST / SLOW /
IMPOSSIBLE / UNKNOWN). `CONFIRMED` (a real sighting) and `INFERRED` (the
movement between two sightings) are visually distinct and never conflated.

## 5. Tests

`backend/tests/test_vehicle_profile.py` (4): consolidation (sightings,
cameras, journey, counts, related, watchlist), ANPR failure-reason
breakdown, auth 401, empty for an unknown vehicle. Frontend `/workspace`
route serves 200; build clean.

## 6. Limitations

- The center camera player shows the **last** camera; a per-sighting
  evidence carousel is a future refinement.
- Journey replay has no time-scrubber on `/workspace` (it does on
  `/investigation`).
