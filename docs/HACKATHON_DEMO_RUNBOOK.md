# SENTINEL — Hackathon Demo Runbook

Everything below runs **with government CCTV disconnected** and **no LLM
key** (deterministic AI provider). One command up, one command to reset.

---

## 1. Start (fresh, seeded)

```bash
git checkout penultimate
docker compose up -d --build          # postgis + minio + backend + frontend
# entrypoint: alembic 0001→0008 → admin seed → AI demo seed (SEED_AI_DEMO=1)
```

Wait ~30–60 s (first run builds images + `npm ci`). Then:

* Frontend: <http://localhost:3000>
* API:      <http://localhost:8000> (`GET /health` → `{"status":"ok"}`)
* Admin password: printed by the backend container, or set `ADMIN_PASSWORD` in `.env`.
  `docker compose logs backend | grep password`

### Health check

```bash
curl -s localhost:8000/health
docker compose ps            # all 4 containers healthy / up
```

## 2. Reset the demo data

```bash
./scripts/reset_demo.sh          # in-place: wipes only the demo rows + re-seeds
./scripts/reset_demo.sh --full   # full teardown + rebuild + reseed
```

The in-place reset removes exactly: 8 demo cameras (`CAM-01…CAM-08`), the
`GJ18TC0450` journey, `INC-<year>-9001`, `CASE-<year>-9001`, and the
stopped-vehicle anomaly + its alert. Real data and the `GJ18TC0450`
watchlist entry are untouched. Deterministic — verified idempotent.

## 3. What the seed creates (all real DB rows, production code paths)

| Entity | Detail |
| :--- | :--- |
| Cameras | `CAM-01 … CAM-08`, real west-Ahmedabad coordinates, `REAL` source |
| Journey | `GJ18TC0450` seen at `CAM-01 → CAM-02 → CAM-04 → CAM-06 → CAM-08` over ~40 min, geolocated, white car; on the watchlist |
| Alert | a real `WATCHLIST` alert on the first sighting |
| Incident / Case | `INC-<yr>-9001` (from the alert) + `CASE-<yr>-9001` with evidence links |
| Other traffic | "white SUVs after 9 PM", "unknown vehicles 20:00–22:00" |
| Anomaly | a stopped vehicle at `CAM-04` (track 7714, ~14 detections / ~210 s / < 15 m) → `anomaly_events` row + an `ANOMALY` alert |

---

## 4. The 2-minute demo script (exact clicks)

> Log in as `admin`.

| # | Click / do | What the judge sees |
| :-- | :--- | :--- |
| 1 | **Overview** (landing) | KPI row: total/online/offline cameras, vehicles detected, watchlist hits, active alerts, **AI Anomalies**, incidents, open cases. Panels: Live Incidents · Recent Cases · **AI Anomaly Events**. Quick actions incl. **AI Copilot**. |
| 2 | **Cameras** → **Management console →** | Table: every camera, `REAL`/`MOCK`, online/offline, last heartbeat, last detection, coords. Filter `Source = REAL`. |
| 3 | Click camera **CAM-04** | Modal: metadata, **health history** transitions, "Open in Investigation". |
| 4 | **Copilot** tab | Suggested questions. Click **"Where was GJ18TC0450 seen?"** |
| 5 | — | Grounded answer ("detected 5 times across 5 cameras…"), **AI MATCH: HIGH** chip, interpreted-filter chips, **timeline**, **GIS mini-map** with 5 points, related **ALERT / INCIDENT / CASE** links. |
| 6 | Ask **"Show its journey."** | `CAM-01 → CAM-02 → CAM-04 → CAM-06 → CAM-08` |
| 7 | Click **"Open full investigation & GIS"** | Investigation console: **Journey Intelligence** — CONFIRMED sightings chained by **INFERRED** transitions (gap, distance, ~speed, confidence). Movement Timeline + trail on the dark map. |
| 8 | **Search** tab → NL box: **"white cars after 9 PM"** | Chips: `Colour: WHITE`, `Type: CAR`, `Time: after 21:00`. Then the normal Advanced Search results. |
| 9 | Open `INC-<yr>-9001` → **Generate AI Summary** | "AI-GENERATED SUMMARY", first/last detection, cameras, evidence count, **investigation gaps**. |
| 10 | Open `CASE-<yr>-9001` → **Generate AI Summary** + **Case Timeline** | Case headline + linked incident + evidence + derived timeline. |
| 11 | **Anomalies** tab | The stopped-vehicle anomaly at CAM-04, confidence chip, "View alert" → the `ANOMALY`-source alert. |
| 12 | **Reports** → **Incident Report** → **CSV** / **PDF** | Downloads real aggregates. |
| 13 | **Admin → Audit** | `AI_INVESTIGATION`, `AI_SEARCH`, `AI_INCIDENT_SUMMARY`, `AI_ANOMALY_SCAN`, `VEHICLE_SEARCH`, `REPORT_EXPORT` rows — every action logged. |
| 14 | (optional) Log in as an `OPERATOR` | Read-only: Copilot / search / summaries work; anomaly **scan** → 403. |

**Talking point:** *Every number on screen came from PostgreSQL. Nothing is
hard-coded. The AI runs with no internet and no LLM key. When the
government feeds come back, the same pipeline fills the same tables — no
code change.*

---

## 5. API-only demo (no browser)

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"'"$ADMIN_PASSWORD"'"}' | jq -r .access_token)

curl -s -X POST localhost:8000/api/v1/ai/investigate -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"query":"Where was GJ18TC0450 seen in the last 6 hours?"}' | jq
curl -s -X POST localhost:8000/api/v1/ai/search -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"query":"white cars after 9 PM"}' | jq '.parsed, .search.total'
curl -s "localhost:8000/api/v1/vehicles/search?plate=GJ18TC0450" -H "Authorization: Bearer $TOKEN" | jq '.journey.transitions'
curl -s -X POST localhost:8000/api/v1/ai/anomalies/scan -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{}' | jq
```

---

## 6. Troubleshooting

| Symptom | Fix |
| :--- | :--- |
| Frontend `Connection reset` right after `up` | `npm ci` still running in the container — wait 2–3 min on first start. `docker compose logs -f frontend`. |
| Port 8000/3000 in use | set `BACKEND_HOST_PORT` / `FRONTEND_HOST_PORT` in `.env`. |
| No demo data | `SEED_AI_DEMO` must be truthy (compose default `1`). Run `./scripts/reset_demo.sh`. |
| "admin password?" | `docker compose logs backend \| grep -i password`, or set `ADMIN_PASSWORD` in `.env` and `./scripts/reset_demo.sh --full`. |
| Copilot says "not available in recorded evidence" for GJ18TC0450 | demo not seeded — run `./scripts/reset_demo.sh`. |
| Anomaly missing | `curl -X POST …/ai/anomalies/scan` or wait one scan interval (300 s). |
| Real cameras show `UNKNOWN` plates | expected — wide-area government feeds; ANPR emits `UNKNOWN`, never a guess. |

## 7. Enabling a real LLM (optional, not needed for the demo)

```bash
# .env
AI_LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```
The LLM then only re-words the deterministic answer. Remove it → fully offline again.
