# SENTINEL — Spatial Database Architecture (PostgreSQL + PostGIS)

---

## 1. Relational & Spatial Database Schema

SENTINEL uses **PostgreSQL 15** with the **PostGIS 3.3** spatial extension for spatial-temporal querying.

```sql
-- 1. Cameras Entity Table
CREATE TABLE cameras (
    camera_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    department VARCHAR(128) NOT NULL,
    location GEOMETRY(Point, 4326) NOT NULL,
    stream_url VARCHAR(512) NOT NULL,
    status VARCHAR(32) DEFAULT 'ONLINE'
);
CREATE INDEX idx_cameras_gis ON cameras USING GIST (location);

-- 2. Vehicle Events Table
CREATE TABLE vehicle_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id VARCHAR(64) REFERENCES cameras(camera_id),
    track_id INT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    plate_number VARCHAR(32) NOT NULL,
    vehicle_type VARCHAR(32) NOT NULL,
    ocr_confidence FLOAT NOT NULL,
    evidence_snapshot_path VARCHAR(512) NOT NULL
);
CREATE INDEX idx_events_plate ON vehicle_events (plate_number, timestamp DESC);
CREATE INDEX idx_events_timestamp ON vehicle_events (timestamp DESC);

-- 3. Watchlist Table
CREATE TABLE watchlist (
    watchlist_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plate_number VARCHAR(32) UNIQUE NOT NULL,
    offense_category VARCHAR(128) NOT NULL,
    priority VARCHAR(16) DEFAULT 'HIGH',
    added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 4. Alerts Table
CREATE TABLE alerts (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID REFERENCES vehicle_events(event_id),
    camera_id VARCHAR(64) REFERENCES cameras(camera_id),
    plate_number VARCHAR(32) NOT NULL,
    offense_category VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    acknowledged BOOLEAN DEFAULT FALSE
);
CREATE INDEX idx_alerts_cooldown ON alerts (plate_number, camera_id, created_at DESC);
```

---

## 2. Partition Strategy
For production scaling ($> 10,000$ cameras), `vehicle_events` uses monthly range partitioning (`PARTITION BY RANGE (timestamp)`).

---

## 3. Operational Layer (migration `0006`, 2026-09-08)

Additive tables that turn alerts into managed police work. **Nothing in §1
is altered.** Every operational row references the source rows by foreign
key — no alert / vehicle / camera state is denormalised, so the modules
stay synchronised through the shared entities.

```sql
-- incidents: an alert (or manual observation) promoted to tracked work
CREATE TABLE incidents (
    id VARCHAR PRIMARY KEY,
    incident_number VARCHAR UNIQUE NOT NULL,          -- INC-YYYY-NNNN
    title VARCHAR NOT NULL,
    description VARCHAR,
    category VARCHAR NOT NULL DEFAULT 'WATCHLIST_HIT',
    priority_level prioritylevel NOT NULL DEFAULT 'MEDIUM',
    status incidentstatus NOT NULL DEFAULT 'NEW',     -- NEW/ACKNOWLEDGED/INVESTIGATING/RESOLVED/CLOSED
    alert_id VARCHAR REFERENCES alerts(id),
    vehicle_event_id VARCHAR REFERENCES vehicle_events(id),
    camera_id VARCHAR REFERENCES cameras(id),
    plate_number_normalized VARCHAR,                  -- identifier, not mutable state
    created_by_user_id  VARCHAR REFERENCES users(id),
    assigned_to_user_id VARCHAR REFERENCES users(id),
    acknowledged_by_user_id VARCHAR REFERENCES users(id),
    acknowledged_at TIMESTAMP,
    resolved_by_user_id VARCHAR REFERENCES users(id),
    resolved_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE INDEX ix_incidents_status_created ON incidents (status, created_at);
-- + single-column indexes on status, priority_level, category, alert_id,
--   vehicle_event_id, camera_id, assigned_to_user_id, plate_number_normalized

CREATE TABLE incident_notes    (id PK, incident_id FK→incidents, author_user_id FK→users, body, ts…);
CREATE TABLE incident_evidence (id PK, incident_id FK→incidents, vehicle_event_id FK→vehicle_events,
                                added_by_user_id FK→users, note,
                                UNIQUE (incident_id, vehicle_event_id));

-- cases: a lightweight investigation folder
CREATE TABLE cases (
    id VARCHAR PRIMARY KEY,
    case_number VARCHAR UNIQUE NOT NULL,              -- CASE-YYYY-NNNN
    title VARCHAR NOT NULL, description VARCHAR,
    priority_level prioritylevel NOT NULL DEFAULT 'MEDIUM',
    status casestatus NOT NULL DEFAULT 'OPEN',        -- OPEN/INVESTIGATING/ON_HOLD/RESOLVED/CLOSED
    primary_plate_normalized VARCHAR,
    created_by_user_id VARCHAR REFERENCES users(id),
    assigned_to_user_id VARCHAR REFERENCES users(id),
    created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE INDEX ix_cases_status_created ON cases (status, created_at);

CREATE TABLE case_notes     (id PK, case_id FK→cases, author_user_id FK→users, body, ts…);
CREATE TABLE case_incidents (id PK, case_id FK→cases, incident_id FK→incidents,
                             added_by_user_id FK→users, UNIQUE (case_id, incident_id));
CREATE TABLE case_evidence  (id PK, case_id FK→cases, vehicle_event_id FK→vehicle_events,
                             added_by_user_id FK→users, note, UNIQUE (case_id, vehicle_event_id));

-- notifications: operational events for the control room (real events only)
CREATE TABLE notifications (
    id VARCHAR PRIMARY KEY,
    type VARCHAR NOT NULL,                            -- WATCHLIST_MATCH / INCIDENT_CREATED / INCIDENT_ASSIGNED / CASE_ASSIGNED …
    severity notificationseverity NOT NULL DEFAULT 'INFO',
    title VARCHAR NOT NULL, body VARCHAR,
    resource VARCHAR, resource_id VARCHAR,            -- deep-link target
    target_user_id VARCHAR REFERENCES users(id),      -- NULL = broadcast
    read BOOLEAN NOT NULL DEFAULT FALSE, read_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE INDEX ix_notifications_read_created ON notifications (read, created_at);
```

**Evidence is never duplicated.** `incident_evidence` / `case_evidence`
are pointer rows to an existing `vehicle_events` row; the snapshot file is
still served only through `GET /api/v1/vehicles/evidence/{event_id}`
(MinIO + short-lived media ticket, unchanged).

**Audit** uses the existing `audit_logs` table — the operational endpoints
write to it via `app/services/audit.record_audit`; `GET /api/v1/admin/audit`
is a read-only projection over it, not a second store.
