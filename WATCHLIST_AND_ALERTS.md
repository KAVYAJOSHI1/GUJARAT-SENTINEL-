# SENTINEL — Watchlist Matching Engine & Real-Time Alert Router

---

## 1. Watchlist Processing Flow

```text
[ AI Event Ingest Payload ]
            │
            ▼
[ Plate Normalizer ] (Strip spaces, hyphens: e.g. GJ-01 AB 1234 -> GJ01AB1234)
            │
            ▼
[ Watchlist Table Lookup ] ──► (SELECT * FROM watchlist WHERE plate_number = 'GJ01AB1234')
            │
            ├── Match Found ──► Evaluate 5-Minute Alert Cooldown Engine
            │                    ├── Cooldown Active (<300s since last alert on same camera) ──► Suppress Duplicate
            │                    └── Cooldown Expired (>=300s) ──► Create Alert Record ──► WebSocket Broadcast
            └── No Match    ──► Log Normal Vehicle Event
```

---

## 2. Real-Time Alert Router & WebSockets

- **Alert Cooldown**: Prevents alert storms by enforcing a 300-second cooldown per target plate string per camera feed.
- **WebSocket Broadcast**: Emits instant alert JSON payloads over `ws://localhost:8000/ws/alerts` to connected React command center clients.
