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
