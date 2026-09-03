# DEVELOPER EXECUTION GUIDE — VANSHAL

---

### 1. Developer Details
- **Developer Name**: Vanshal
- **Role**: Backend Microservice, PostGIS Database & Watchlist Engine Lead
- **Git Branch**: `feature/vanshal-backend`

---

### 2. Project Objective
Build the central FastAPI backend microservice and PostGIS spatial-temporal database platform for **SENTINEL**. Manage database entities (`cameras`, `vehicle_events`, `watchlist`, `alerts`, `users`, `audit_logs`), build the automated Watchlist Cross-Referencing Engine with 5-minute alert cooldown deduplication, dispatch real-time WebSocket alerts, and integrate MinIO object storage for snapshot evidence.

---

### 3. Exact Responsibility
You own the central backend services (`backend/`) and spatial database definitions (`database/`). You are responsible for FastAPI REST endpoint routing, SQLModel/SQLAlchemy database models, Alembic schema migrations, PostGIS spatial queries, Watchlist exact plate matching, alert deduplication logic, WebSocket client connection management, and MinIO S3 bucket storage.

---

### 4. Exact Features to Build
1. **FastAPI Core Application Framework**: Initialize FastAPI routing, CORS middleware, dependency injection, and JWT/RBAC security handlers.
2. **PostgreSQL 15 + PostGIS Database Schemas**: Create tables (`cameras`, `vehicle_events`, `watchlist`, `alerts`, `users`, `audit_logs`), spatial GiST indexes, and B-Tree indexes.
3. **Camera Registry API (`/api/v1/cameras`)**: CRUD endpoints returning camera lists and PostGIS GeoJSON feature collections.
4. **AI Event Ingestion API (`POST /api/v1/events/ai-detection`)**: Receive AI detection JSON payloads from Kavya, persist to `vehicle_events`, and upload snapshots to MinIO.
5. **Watchlist Matching Engine**: Normalize incoming registration plate strings and cross-reference against blacklisted/stolen vehicle records.
6. **Alert Cooldown Deduplicator**: Suppress duplicate alert generation for the same plate string on the same camera within a 5-minute (300 seconds) window.
7. **Real-Time WebSocket Alert Dispatcher (`WS /ws/alerts`)**: Broadcast instant alert JSON payloads to connected dashboard WebSocket clients.
8. **Vehicle Search & Trajectory API (`GET /api/v1/vehicles/search?plate={plate}`)**: Query chronological sightings and spatial trajectory history.

---

### 5. What NOT to Build
- Do NOT store raw video binary BLOBs inside PostgreSQL tables. Store file references and MinIO Object Storage URLs only.
- Do NOT build YOLO vehicle detection models or PaddleOCR engines (owned by Kavya).
- Do NOT build RTSP video stream capture workers (owned by Rishit).
- Do NOT build React UI components or Leaflet map UI widgets (owned by Isha & Vishakha).

---

### 6. Technologies
- **Framework**: FastAPI (Python 3.10+)
- **Database**: PostgreSQL 15+ with PostGIS 3.3 extension
- **ORM / Migrations**: SQLAlchemy 2.0 / SQLModel / Alembic
- **Object Storage**: MinIO Python SDK (S3-compatible API)
- **Sockets**: FastAPI Native WebSockets

---

### 7. Recommended Models / Libraries
- `fastapi` & `uvicorn`
- `sqlalchemy` & `sqlmodel`
- `psycopg2-binary` & `geoalchemy2`
- `minio`
- `python-jose` & `passlib`

---

### 8. Input
- AI detection event JSON payloads posted to `POST /api/v1/events/ai-detection` from Kavya's pipeline.
- REST HTTP queries and Watchlist entry management payloads from Isha and Vishakha's frontend consoles.

---

### 9. Processing Pipeline
```text
AI Event Ingest (POST /api/v1/events/ai-detection)
 │
 ▼
Save Record to PostgreSQL "vehicle_events" Table & Upload Images to MinIO Storage
 │
 ▼
Watchlist Engine ──► Query "watchlist" Table for Exact Plate Match
 │
 ├── Match Found ──► Check Cooldown Engine (Same Plate + Camera in Last 300 Seconds?)
 │                    ├── Cooldown Active ──► Suppress Alert Generation
 │                    └── Cooldown Expired ──► Save Record to "alerts" Table ──► Broadcast Payload via WS
 └── No Match    ──► Return Success (Normal Event Logged)
```

---

### 10. Output
- Persistent records stored in PostgreSQL + PostGIS tables.
- Evidence snapshot image files uploaded to MinIO Object Storage (`sentinel-evidence` bucket).
- Standardized REST JSON responses and real-time WebSocket alert push notifications.

---

### 11. Required API Contract
Must strictly comply with `testing` integration contracts documented in `docs/API_CONTRACTS.md`:
- **Camera Schema**: `docs/API_CONTRACTS.md#1-camera-object-schema`
- **AI Event Schema**: `docs/API_CONTRACTS.md#2-ai-event-object-schema`
- **Alert Schema**: `docs/API_CONTRACTS.md#3-alert-object-schema`
- **Vehicle History Schema**: `docs/API_CONTRACTS.md#4-vehicle-history-response-schema`
- **Error Format**: `docs/API_CONTRACTS.md#6-standardized-http-api-error-response-format`

---

### 12. Database Interaction
Primary administrator of PostgreSQL + PostGIS. Execute DDL schema migrations for 6 core tables:
- `cameras`: Camera metadata with `geometry(Point, 4326)` location column.
- `vehicle_events`: Logged AI detections with spatial-temporal indexes.
- `watchlist`: Blacklisted plate strings, offense category, and priority level.
- `alerts`: Watchlist detection hits with acknowledgment status.
- `users`: User credentials and RBAC roles (`ADMIN`, `OFFICER`, `OPERATOR`).
- `audit_logs`: System access logs.

---

### 13. Integration Dependencies
- **Upstream Providers**:
  - **Kavya (`feature/kavya-ai-anpr`)**: Consumes AI event JSON payloads.
  - **Prajin (`feature/prajin-tracking`)**: Integrates Prajin's cross-camera trajectory builder.
  - **Rishit (`feature/rishit-stream`)**: Receives camera stream status updates.
- **Downstream Consumers**:
  - **Isha (`feature/isha-frontend`)**: Supplies REST endpoints and WebSocket alert feeds.
  - **Vishakha (`feature/vishakha-investigation`)**: Supplies PostGIS GeoJSON endpoints and vehicle search trajectory API.

---

### 14. Exact Implementation Steps
1. Create `backend/` and `database/` folder structures (`backend/app/api/`, `backend/app/models/`, `backend/app/services/`).
2. Define SQLAlchemy/SQLModel models in `models/` for `Camera`, `VehicleEvent`, `Watchlist`, `Alert`, `User`, `AuditLog`.
3. Create PostGIS GiST index on `cameras.location` and B-Tree indexes on `vehicle_events.plate_number` and `timestamp`.
4. Build `minio_service.py` initializing bucket `sentinel-evidence` on MinIO server (`http://localhost:9000`).
5. Build `events.py` API route receiving AI detections, saving to DB, and invoking `watchlist_engine.py`.
6. Build `watchlist_engine.py` performing normalized string match and checking 5-minute alert cooldown.
7. Build `alert_dispatcher.py` managing active WebSocket connections in a `ConnectionManager` pool.
8. Build `vehicles.py` search API returning chronologically ordered sightings with PostGIS coordinates.

---

### 15. Error Handling
- **Database Disconnection**: Catch SQLAlchemy `OperationalError`, log error, and return HTTP 500 JSON payload.
- **Duplicate Watchlist Entry**: Return HTTP 409 Conflict if adding a plate already in watchlist.
- **MinIO Storage Unreachable**: Fallback to saving evidence snapshots to local disk folder if MinIO service is offline.

---

### 16. Testing Requirements
- Unit test watchlist matching logic on exact hits and non-hits.
- Test alert cooldown suppression logic for 2 identical events fired 10 seconds apart.
- Integration test WebSocket broadcast receipt when a watchlist match occurs.

---

### 17. Performance Requirements
- AI event ingestion API latency $< 20$ ms.
- Watchlist lookup & alert generation latency $< 15$ ms.
- Vehicle trajectory search query execution $< 50$ ms for 100,000+ event records.

---

### 18. Day 1 Tasks
Initialize FastAPI application structure, configure PostgreSQL database connection pool, create PostGIS schema migration scripts in `database/`.

---

### 19. Day 2 Tasks
Build Camera CRUD APIs, AI Event ingestion endpoint (`POST /api/v1/events/ai-detection`), and MinIO S3 object storage upload service.

---

### 20. Day 3 Tasks
Build Watchlist lookup engine, 5-minute alert cooldown deduplicator, and WebSocket real-time alert dispatcher (`WS /ws/alerts`).

---

### 21. Day 4 Tasks
Build Vehicle Search trajectory API (`GET /api/v1/vehicles/search`), implement JWT auth/RBAC middleware, and execute integration tests.

---

### 22. Definition of Done (DoD)
- [ ] PostgreSQL + PostGIS schemas initialize cleanly via Docker Compose.
- [ ] AI detection event matching a watchlist plate instantly creates an `alerts` record.
- [ ] Alert cooldown engine successfully suppresses duplicate alerts within 5-minute window.
- [ ] Real-time alert is pushed over WebSocket to connected dashboard clients in $< 100$ ms.
- [ ] Vehicle search query (`/api/v1/vehicles/search?plate=GJ01AB1234`) returns chronologically ordered sightings with PostGIS lat/long.
- [ ] Code committed to `feature/vanshal-backend` and Pull Request opened to `testing`.

---

### 23. Git Workflow
```bash
# 1. Work exclusively on your feature branch
git checkout feature/vanshal-backend

# 2. Add implementation files as you build
git add backend/ database/

# 3. Commit changes
git commit -m "feat(backend): implement FastAPI microservice, PostGIS schema, and Watchlist alert engine"

# 4. Push to GitHub
git push origin feature/vanshal-backend

# 5. Open Pull Request on GitHub:
# feature/vanshal-backend  ──►  testing (Central Integration Branch)
# NEVER push directly to main!
```

---

### 24. What Must Be Demonstrated Before PR
1. PostgreSQL + PostGIS database containing `cameras` and `vehicle_events` tables with spatial indexes.
2. Watchlist match triggering alert generation and pushing WebSocket alert payload.
3. Alert cooldown engine suppressing duplicate alert for second event fired 10 seconds later.
4. Vehicle search API returning chronologically ordered trajectory for `GJ01AB1234`.

---

### 25. Shared Technical Reference
For central system specifications, hybrid architecture decisions, and database schemas, refer to the integration blueprints on `testing`:
- `docs/ARCHITECTURE.md`
- `docs/API_CONTRACTS.md`
- `docs/TESTING.md`

---

### 26. Final Workspace Rule
This branch starts with **ONLY** `DEVELOPER_README.md`. As developer Vanshal, you will create the `backend/` and `database/` directories and implementation files as you code. Do NOT commit unnecessary root scaffold files.
