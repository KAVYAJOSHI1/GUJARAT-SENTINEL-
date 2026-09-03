-- Executed once by the postgis container's docker-entrypoint-initdb.d hook.
-- Enables the PostGIS 3.3 extension before Alembic migrations run.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
