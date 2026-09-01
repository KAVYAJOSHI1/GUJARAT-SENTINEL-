# Implementation Specification — VANSHAL (Backend + Database + Watchlist + Alerts)

---

### 1. Ownership
- **Developer Name**: Vanshal
- **Module Ownership**: FastAPI Backend Microservice, PostgreSQL + PostGIS Schemas, Watchlist Engine & Real-Time Alert Engine
- **Git Branch**: `feature/vanshal-backend`

---

### 2. Objective
Architect and implement the central FastAPI backend microservice, manage PostgreSQL + PostGIS spatial-temporal database tables, build the automated Watchlist Cross-Referencing Engine with alert cooldown deduplication, dispatch real-time alerts over WebSockets, and manage MinIO object storage for snapshot evidence.

---

### 3. Responsibilities
- Develop FastAPI REST API services and project routing structure.
- Execute PostgreSQL + PostGIS database schema migrations (`cameras`, `vehicle_events`, `watchlist`, `alerts`, `users`, `audit_logs`).
- Build the **Watchlist Matching Engine**: cross-reference incoming AI detection plates against blacklisted/stolen vehicle records.
- Implement the **Alert Cooldown Engine**: suppress duplicate alerts for the same plate string on the same camera within a 5-minute window.
- Dispatch real-time WebSocket alert notifications to Isha & Vishakha's frontend modules.
- Manage MinIO S3 object storage for high-resolution vehicle snapshot evidence files.
- Implement JWT Authentication and Role-Based Access Control (RBAC).

---

### 4. Features to Implement
1. **Camera Registry API (`/api/v1/cameras`)**: CRUD camera metadata and return PostGIS GeoJSON feature collections.
2. **AI Event Ingestion Endpoint (`/api/v1/events/ai-detection`)**: Accept JSON event payloads from Kavya's AI pipeline and persist to PostGIS.
3. **Vehicle Search API (`/api/v1/vehicles/search`)**: Query vehicle chronological sightings trajectory by plate string `GJ01AB1234`.
4. **Watchlist Management API (`/api/v1/watchlist`)**: CRUD blacklisted plate entries, categories, and priorities.
5. **Real-Time Alert Dispatcher (`WS /ws/alerts`)**: Broadcast instant alert JSON payloads to connected dashboard WebSocket clients.
6. **MinIO Object Storage Service**: Upload and serve evidence snapshots and cropped plate images.

---

### 5. Module Architecture
```text
FastAPI Backend (app/main.py)
 ├── API Routers (app/api/v1/)
 │    ├── cameras.py    ──► Query / Update PostGIS Cameras Table
 │    ├── events.py     ──► Ingest AI Detections ──► Watchlist Matching Engine
 │    ├── vehicles.py   ──► Search Vehicle Trajectory History
 │    ├── watchlist.py  ──► Manage Blacklisted Plates
 │    └── alerts.py     ──► Fetch / Acknowledge Watchlist Matches
 ├── Core Services (app/services/)
 │    ├── watchlist_engine.py  ──► Matching & Cooldown Logic
 │    ├── alert_dispatcher.py  ──► WebSocket Notification Broadcaster
 │    └── minio_service.py     ──► S3 Snapshot Evidence Storage
 └── Database (app/models/ & app/core/database.py)
      └── PostgreSQL 15 + PostGIS Spatial-Temporal Tables
```

---

### 6. Technologies
- **Framework**: FastAPI (Python 3.10+)
- **Database**: PostgreSQL 15+ with PostGIS 3.3 extension
- **ORM / Migrations**: SQLAlchemy / SQLModel / Alembic
- **Object Storage**: MinIO Python SDK (S3-compatible)
- **Sockets**: FastAPI Native WebSockets

---

### 7. Folder Structure
```text
backend/
├── app/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── cameras.py
│   │   │   ├── events.py
│   │   │   ├── vehicles.py
│   │   │   ├── watchlist.py
│   │   │   └── alerts.py
│   │   └── api_router.py
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   └── database.py
│   ├── models/
│   │   ├── camera.py
│   │   ├── event.py
│   │   ├── watchlist.py
│   │   └── alert.py
│   ├── services/
│   │   ├── watchlist_engine.py
│   │   ├── alert_dispatcher.py
│   │   └── minio_service.py
│   └── main.py
├── Dockerfile
├── requirements.txt
└── README.md
```

---

### 8. Detailed Implementation Tasks
1. Setup FastAPI project routing layout and SQLAlchemy database session factory in `core/database.py`.
2. Define SQLModel / SQLAlchemy models for `Camera`, `VehicleEvent`, `Watchlist`, `Alert`, `User`, `AuditLog`.
3. Create PostGIS GiST spatial index on `cameras.location` and B-Tree indexes on `vehicle_events.plate_number` and `timestamp`.
4. Implement `minio_service.py` initializing bucket `sentinel-evidence` on MinIO server (`http://localhost:9000`).
5. Implement `events.py` handler receiving AI detections:
   - Save record to `vehicle_events`.
   - Invoke `watchlist_engine.check_watchlist(plate_number, camera_id, timestamp)`.
6. Implement `watchlist_engine.py`:
   - Query `watchlist` table for exact match on normalized plate string.
   - If matched, check `alerts` table for existing alert on same `plate_number` and `camera_id` within last 300 seconds (5 minutes).
   - If not in cooldown window, insert new record in `alerts` and broadcast via `alert_dispatcher.py`.
7. Implement `alert_dispatcher.py` managing active WebSocket client connections in `ConnectionManager` pool.
8. Implement `vehicles.py` search endpoint returning chronological sightings array and summary statistics.

---

### 9. Input
- REST HTTP request payloads from AI pipeline, Frontend UI, and Ingestion services.
- PostGIS spatial query parameters.

---

### 10. Output
- Saved database records in PostgreSQL + PostGIS.
- Uploaded snapshot files in MinIO Object Storage.
- Standardized REST JSON API responses and WebSocket alert broadcasts.

---

### 11. APIs Produced / Exposed
- `GET /api/v1/cameras`: Return camera list / GeoJSON feature collection.
- `POST /api/v1/events/ai-detection`: Ingest AI detection events.
- `GET /api/v1/vehicles/search?plate={plate}`: Vehicle chronological trajectory query.
- `GET /api/v1/watchlist` & `POST /api/v1/watchlist`: Manage watchlist entries.
- `POST /api/v1/alerts/{id}/acknowledge`: Mark alert acknowledged.
- `WS /ws/alerts`: Real-time alert push socket.

---

### 12. Database Interaction
Primary manager of all PostgreSQL + PostGIS database operations and schema migrations.

---

### 13. Dependencies on Other Members
- **Kavya & Prajin**: Consumes AI detection events from Kavya and tracking trajectories from Prajin.
- **Isha & Vishakha**: Supplies REST APIs and WebSocket alert streams for Isha's dashboard and Vishakha's GIS search map.

---

### 14. Integration Contract
Must strictly adhere to `docs/API_CONTRACTS.md` for all JSON schemas and HTTP error codes.

---

### 15. Error Handling & Edge Cases
- **Duplicate Alert Suppression**: The cooldown engine suppresses duplicate alerts for the same vehicle on the same camera within 5 minutes.
- **Database Connection Failure**: Catch SQLAlchemy operational errors and return HTTP 500 JSON error payload.
- **MinIO Storage Disconnect**: Fallback to local disk storage if MinIO object storage is unreachable.

---

### 16. Testing Requirements
- Unit test watchlist matching logic on exact hits and non-hits.
- Test alert cooldown suppression logic for 2 identical events fired 10 seconds apart.
- Integration test WebSocket broadcast receipt when a watchlist match occurs.

---

### 17. Performance Requirements
- AI event ingestion API latency $< 20$ ms.
- Watchlist lookup & alert generation latency $< 15$ ms.
- Vehicle search query execution $< 50$ ms for 100,000+ event records.

---

### 18. Day 1 Plan
Setup FastAPI application layout, PostgreSQL database connection pool, and PostGIS schema migration scripts.

---

### 19. Day 2 Plan
Implement Camera APIs, AI Event ingestion endpoint, and MinIO object storage service.

---

### 20. Day 3 Plan
Build Watchlist lookup engine, alert cooldown deduplicator, and WebSocket alert dispatcher.

---

### 21. Day 4 Plan
Implement Vehicle Search trajectory query API, JWT auth/RBAC, and integration tests on `testing`.

---

### 22. Definition of Done (DoD)
- [ ] PostgreSQL + PostGIS schemas initialize cleanly via Docker Compose.
- [ ] AI detection event matching a watchlist plate instantly generates an `alert` record.
- [ ] Alert cooldown engine successfully suppresses duplicate alerts within 5-minute window.
- [ ] Real-time alert is pushed over WebSocket to connected dashboard clients in $< 100$ ms.
- [ ] Vehicle search query (`/api/v1/vehicles/search?plate=GJ01AB1234`) returns chronologically ordered sightings with PostGIS lat/long.
- [ ] Code committed to `feature/vanshal-backend` and verified on `testing`.

---

### 23. Deliverables
- Complete `backend/` FastAPI microservice source codebase.
- PostgreSQL + PostGIS database schema initialization scripts (`database/init.sql`).

---

### 24. What NOT to do
- Do NOT store raw video binary BLOBs inside PostgreSQL; store metadata and image file references only.
- Do NOT fabricate live government DB credentials; use internal representative database tables.
- Do NOT push directly to `main`.

---

### 25. Merge Checklist
- [ ] PostGIS table migrations executed cleanly
- [ ] Watchlist matching & WebSocket alert push verified
- [ ] PR opened from `feature/vanshal-backend` to `testing`
