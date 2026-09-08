# AI Demo Runbook (offline — no government CCTV)

The entire Phase 12 AI layer is demonstrable from a fresh `docker compose
up`, with **no internet / no live feed / no LLM key**.

## 1. Start

```bash
docker compose up -d --build          # postgis + minio + backend + frontend
# backend entrypoint: alembic 0001→0008 → seed admin → seed_ai_demo.py
```

`SEED_AI_DEMO=1` (compose default) inserts **real database rows** via the
production code paths:

* 8 cameras `CAM-01 … CAM-08` (real Ahmedabad coordinates).
* `GJ18TC0450` journey — 5 geolocated sightings `CAM-01 → CAM-02 → CAM-04 →
  CAM-06 → CAM-08` over ~40 min, white car; on the watchlist.
* A real watchlist **Alert** on the first sighting + `INC-<year>-9001` +
  `CASE-<year>-9001` with evidence links.
* "white SUVs after 9 PM" + "unknown vehicles 20:00–22:00" detections.
* A **stopped vehicle** at `CAM-04` (track 7714, ~14 detections / ~210 s /
  < 15 m) → `seed_ai_demo.py` runs `BehaviorAnalyticsService` once → an
  `anomaly_events` row + an `ANOMALY` alert.

Idempotent — a marker row in `audit_logs` guards re-runs.

## 2. Acceptance walk-through

| # | Action | Expected |
| :-- | :--- | :--- |
| 1 | Log in (admin creds printed by the entrypoint, or your `.env`) | Command centre |
| 2 | Open **Copilot** (`/copilot`) | Chat + suggested questions; header shows `deterministic · offline-capable` |
| 3 | Ask **"Where was GJ18TC0450 seen?"** | "GJ18TC0450 was detected 5 time(s) across 5 camera(s) …", 5 result rows, `AI MATCH: HIGH` |
| 4 | — | Timeline of the 5 sightings (chronological) |
| 5 | — | GIS mini-map with the 5 camera points |
| 6 | Ask **"Show the journey of GJ18TC0450."** | `CAM-01 → CAM-02 → CAM-04 → CAM-06 → CAM-08` |
| 7 | Ask **"Show all vehicles detected after 9 PM."** (or use the NL box on `/search`) | Advanced Search results appear; interpreted filters shown (`time_from: 21:00`) |
| 8 | Open `INC-<year>-9001` → **Generate AI Summary** | "AI-GENERATED SUMMARY", first/last detection, cameras, evidence count, investigation gaps |
| 9 | Open `CASE-<year>-9001` → **Generate AI Summary** | Case headline, linked incidents, vehicle activity |
| 10 | Open **Anomalies** (`/anomalies`) | 1 STOPPED VEHICLE at `CAM-04`, confidence chip, "Held N min (14 detections …)" |
| 11 | Click the anomaly's **View alert** | An alert with `source: ANOMALY`, no watchlist entry |
| 12 | **Admin → Audit** | `AI_INVESTIGATION`, `AI_SEARCH`, `AI_INCIDENT_SUMMARY`, `AI_ANOMALY_SCAN` rows |
| 13 | Log in as an `OPERATOR` | Copilot / search / summaries work; `POST /ai/anomalies/scan` → 403 |
| 14 | Disconnect the internet | Everything above still works (deterministic provider) |

## 3. API-only demo

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"'"$ADMIN_PASSWORD"'"}' | jq -r .access_token)

curl -s -X POST localhost:8000/api/v1/ai/investigate -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"query":"Where was GJ18TC0450 seen in the last 6 hours?"}' | jq

curl -s -X POST localhost:8000/api/v1/ai/search -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"query":"show white cars after 9 PM"}' | jq .filters

curl -s -X POST localhost:8000/api/v1/ai/anomalies/scan -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{}' | jq
```

## 4. Enabling a real LLM (optional)

```bash
# .env
AI_LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

The LLM then only **re-words** the deterministic answer (using the same
facts) and can pick a tool. Remove the key / set `deterministic` to go
fully offline again — no other change.

## 5. Clean deployment (no demo data)

```bash
SEED_AI_DEMO=0 docker compose up -d
```
