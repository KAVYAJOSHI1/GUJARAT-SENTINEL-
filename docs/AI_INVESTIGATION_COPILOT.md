# AI Investigation Copilot

`POST /api/v1/ai/investigate` — natural-language investigation questions
answered from **real Sentinel data only**.

```json
{ "query": "Where was GJ18TC0450 seen in the last 6 hours?" }
```
Optional query param `?plate=<PLATE>` supplies page context so
"this vehicle" resolves.

## Flow

```
question ─► parse_query()  ──►  intent + entities (plate, cameras, time window,
                                 time-of-day band, vehicle type/colour, duration,
                                 watchlist / unknown flags)
        ─► intent → tool    ──►  one of the 9 validated InvestigationTools
        ─► tool runs         ──►  existing indexed DB query (bounded, ≤ AI_MAX_RESULTS)
        ─► aggregate         ──►  results + timeline + map_points + related
                                 (alerts / incidents / cases)
        ─► confidence        ──►  score + level + match_method
        ─► answer            ──►  deterministic template, optionally re-worded by an
                                 LLM using ONLY those facts
```

## Supported intents / examples

| Intent | Example | Tool |
| :--- | :--- | :--- |
| `VEHICLE_SEARCH` | "Where was GJ18TC0450 seen?" | `search_vehicle` |
| `VEHICLE_LAST_SEEN` | "Where was GJ18TC0450 last seen?" | `search_vehicle` |
| `VEHICLE_JOURNEY` | "Show the journey of GJ18TC0450." | `get_vehicle_journey` |
| `CAMERA_SEARCH` | "Which cameras detected GJ18TC0450?" | `search_cameras` |
| `TIME_RANGE_SEARCH` | "Show vehicles near CAM-04 after 9 PM." | `search_detections` |
| `WATCHLIST_SEARCH` | "Show watchlist vehicles detected today." | `watchlist_detections` |
| `ALERT_SEARCH` | "Show all alerts related to GJ18TC0450." | `search_alerts` |
| `INCIDENT_SEARCH` | "Which incidents are associated with this vehicle?" | `search_incidents` |
| `CASE_SEARCH` | "Which cases involve GJ18TC0450?" | `search_cases` |
| `EVIDENCE_SEARCH` | "Show evidence related to this investigation." | `search_evidence` |

## Time parsing (deterministic)

* `last N hours/minutes/days`, `today`, `yesterday`, `this week` → `date_from` / `date_to`
* `after 9 PM`, `before 8 AM`, `between 8 PM and 10 PM` → `time_from` / `time_to` (wall-clock band)
* `for more than 5 minutes`, `longer than 90 seconds` → `min_duration_seconds` (per-track dwell)

## Response (abridged)

```jsonc
{
  "provider": "deterministic",
  "intent": "VEHICLE_SEARCH",
  "parsed": { "plate": "GJ18TC0450", "relative_window": "last 6 hour(s)", ... },
  "tool_calls": [ { "tool": "search_vehicle", "params": { "plate": "GJ18TC0450" } } ],
  "answer": "GJ18TC0450 was detected 5 time(s) across 5 camera(s) between 09:12 and 09:52. It is on the active watchlist.",
  "result_count": 5,
  "results": [ /* real vehicle_events rows */ ],
  "timeline": [ { "timestamp": "...", "camera_code": "CAM-01", "label": "..." }, ... ],
  "map_points": [ { "latitude": 23.01, "longitude": 72.56, "label": "..." }, ... ],
  "related": [ { "kind": "ALERT", "id": "...", "href": "/alerts?focus=..." }, ... ],
  "confidence_score": 0.85, "confidence_level": "HIGH",
  "match_method": "exact plate match on 5 sighting(s) across 5 camera(s)",
  "limitations": []
}
```

## Never-invent guarantees

* Every `results` row is a real `vehicle_events` / `alerts` / `incidents` /
  `cases` row — asserted by `tests/test_ai_copilot.py`.
* An empty result set answers **"… — not available in recorded evidence."**
  and sets `confidence_level: INSUFFICIENT`.
* A journey/last-seen/camera question with no plate is refused with a clear
  message (no guessing).
* `parsed.notes` / `limitations` surface anything the parser could not
  resolve.

## Frontend

`/copilot` — chat interface with suggested questions, the answer, the
interpreted filters (explainability), a confidence chip, the timeline, a
GIS mini-map of the sighting points, and links to the related
alert/incident/case records. "Ask AI about this vehicle" on the
Investigation console deep-links here.
