# Natural-Language CCTV Search

`POST /api/v1/ai/search` — plain-English queries translated into the
**existing** Advanced Search (`POST /api/v1/search/vehicles`). There is one
search engine; the AI layer only builds its filter object.

```json
{ "query": "Show white cars near CAM-04 after 9 PM.", "limit": 50, "offset": 0 }
```

## Flow

```
query ─► parse_query()  (same parser as the Copilot — nlq.py)
      ─► VehicleSearchQuery  { plate, vehicle_type, vehicle_color, camera_code,
                               date_from/to, time_from/to, unknown_only,
                               min_duration_seconds, watchlist_only, sort, limit }
      ─► execute_vehicle_search()   ← the SAME function POST /search/vehicles calls
      ─► existing enriched results (watchlist / alert / incident / case links)
```

## Response

```jsonc
{
  "query": "Show white cars near CAM-04 after 9 PM.",
  "parsed": { "intent": "TIME_RANGE_SEARCH", "vehicle_color": "white",
              "vehicle_type": "car", "camera_codes": ["CAM-04"], "time_from": "21:00" },
  "filters": { "vehicle_color": "white", "vehicle_type": "car",
               "camera_code": "CAM-04", "time_from": "21:00", "sort": "latest", "limit": 50 },
  "search": { /* full VehicleSearchResponse — items, total, took_ms */ },
  "limitations": []
}
```

The **`filters`** object is returned verbatim so the officer sees exactly
what the AI ran — and the frontend hydrates the structured Advanced Search
form with it, so the officer can tweak and re-run.

## Example queries

| Query | Filters produced |
| :--- | :--- |
| "Show white SUVs after 9 PM." | `vehicle_color=white`, `vehicle_type=car`, `time_from=21:00` |
| "Find vehicles near CAM-04." | `camera_code=CAM-04` |
| "Find GJ18TC0450 yesterday." | `plate=GJ18TC0450`, `date_from`/`date_to` = yesterday |
| "Show unknown vehicles between 8 PM and 10 PM." | `unknown_only=true`, `time_from=20:00`, `time_to=22:00` |
| "Show vehicles detected for more than 5 minutes." | `min_duration_seconds=300` (per-camera/track dwell) |

## New search capabilities added this phase (additive to `/search/vehicles`)

* `vehicle_color` — exact, case-insensitive.
* `unknown_only` — `plate_number_normalized = 'UNKNOWN'`.
* `min_duration_seconds` — bounded per-`(camera_code, track_id)` dwell-time
  subquery (`max(timestamp) - min(timestamp) ≥ N`), constrained by the same
  date range.

Frontend: the `/search` page gains a natural-language box above the
structured form.
