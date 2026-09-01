# Team Specification — VANSHAL

## 1. Developer Profile & Module Ownership
- **Member Name**: Vanshal
- **Module Ownership**: Backend APIs + Database Schemas + Watchlist Engine + Real-Time Alerts
- **Git Branch**: `feature/vanshal-backend`

---

## 2. Core Responsibilities
- Architect and develop the core FastAPI backend application.
- Design and maintain the PostgreSQL + PostGIS database schema (`cameras`, `vehicle_events`, `watchlist`, `alerts`, `users`, `audit_logs`).
- Build the **Watchlist Cross-Referencing Engine**: automatically match incoming plate detections against blacklisted/stolen vehicle records.
- Implement the **Real-Time Alert Dispatcher** (WebSocket / SSE) to broadcast critical hits to Isha & Vishakha's dashboard interfaces.
- Manage MinIO / S3 object storage metadata for vehicle snapshot evidence files.
- Implement JWT Authentication and Role-Based Access Control (RBAC).

---

## 3. Database Schema Overview (PostgreSQL + PostGIS)

```sql
-- 1. Cameras Table (PostGIS Geometry)
CREATE TABLE cameras (
    camera_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    department VARCHAR(64) NOT NULL,
    location GEOMETRY(Point, 4326) NOT NULL,
    rtsp_url TEXT NOT NULL,
    status VARCHAR(32) DEFAULT 'ONLINE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Vehicle Events Table
CREATE TABLE vehicle_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id VARCHAR(64) REFERENCES cameras(camera_id),
    track_id INT,
    plate_number VARCHAR(32) INDEX,
    vehicle_type VARCHAR(32),
    confidence FLOAT,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    evidence_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Watchlist Table
CREATE TABLE watchlist (
    watchlist_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plate_number VARCHAR(32) UNIQUE NOT NULL,
    category VARCHAR(64) NOT NULL, -- e.g., 'Stolen', 'Wanted', 'Blacklisted'
    priority VARCHAR(16) NOT NULL, -- 'CRITICAL', 'HIGH', 'MEDIUM'
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Alerts Table
CREATE TABLE alerts (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID REFERENCES vehicle_events(event_id),
    watchlist_id UUID REFERENCES watchlist(watchlist_id),
    priority VARCHAR(16) NOT NULL,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. Technology Stack
- **Framework**: FastAPI (Python 3.10+)
- **Database**: PostgreSQL 15+ with PostGIS 3.3 extension
- **ORM / Migrations**: SQLAlchemy / SQLModel / Alembic
- **Object Storage**: MinIO Python SDK (S3-compatible)
- **Sockets**: Native FastAPI WebSockets

---

## 5. Interface & Data Contracts

### 5.1 REST Endpoints Produced
- `GET /api/v1/cameras`: Fetch camera list and PostGIS GeoJSON.
- `POST /api/v1/events/ai-detection`: Ingest AI detection events from Kavya.
- `GET /api/v1/vehicles/search`: Query vehicle history by plate string.
- `GET /api/v1/watchlist`: CRUD watchlist entries.
- `POST /api/v1/alerts/{id}/acknowledge`: Mark alert acknowledged.
- `WS /ws/alerts`: Real-time alert notification socket.

---

## 6. Expected Directory Layout (`backend/`)
```text
backend/
├── app/
│   ├── api/
│   │   ├── cameras.py
│   │   ├── events.py
│   │   ├── vehicles.py
│   │   ├── watchlist.py
│   │   └── alerts.py
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

## 7. Development Priorities
1. **Day 1**: Setup FastAPI app structure, PostgreSQL connection, and PostGIS table schemas.
2. **Day 2**: Implement Camera CRUD, AI Event ingestion REST endpoints, and MinIO storage service.
3. **Day 3**: Build Watchlist lookup engine and WebSocket alert dispatcher.
4. **Day 4**: Implement Vehicle Search & Route Query endpoints, JWT auth, and integration testing.

---

## 8. Definition of Done (DoD) & Testing Requirements
- [ ] PostgreSQL + PostGIS schema initializes cleanly via Docker Compose.
- [ ] Ingesting an AI detection matching a watchlist plate instantly generates an `alert` database entry.
- [ ] Real-time alert is pushed immediately over WebSocket to connected frontend clients.
- [ ] Vehicle search query (`/api/v1/vehicles/search?plate=GJ01AB1234`) returns chronologically ordered sightings with PostGIS lat/long.
- [ ] Code committed to `feature/vanshal-backend` and verified on `testing`.

---

## 9. Inter-Member Dependencies
- **Kavya & Prajin**: Consumes AI detection events from Kavya and tracking trajectories from Prajin.
- **Isha & Vishakha**: Provides REST endpoints and WebSocket alert streams for Isha's dashboard and Vishakha's GIS search map.
