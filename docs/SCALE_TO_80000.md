# Scaling Sentinel: 50 → 80,000 Cameras

> **The full target design (Kafka, Kubernetes, Triton, statewide Postgres
> partitioning, distributed MinIO) is in the repo-root
> [`SCALABILITY.md`](../SCALABILITY.md)** — with a measured load ladder
> (5/10/20/30 cameras) and an honest gap analysis vs. what runs today.
> This file is the submission-level summary.

---

## 1. What runs today (PoC — ~50 cameras)

Single-node `docker-compose.yml`: one PostgreSQL 15 + PostGIS, one MinIO,
one FastAPI backend, CPU inference, in-process `queue.Queue` frame handoff.
Measured: ~9.5 processed FPS on the 3 demo clips; ~1.0–1.3 FPS aggregate
across a 5–30 camera synthetic ladder (single-consumer-thread bound).

**Correctly scoped to the ~50-feed PoC.** The multi-worker path exists but
showed no throughput benefit CPU-bound and defaults to 1 worker.

## 2. What already scales (data tier — built, not just designed)

| Concern | Implemented today | Statewide extension |
| :--- | :--- | :--- |
| Plate / journey lookup | composite B-tree `(plate_normalized, timestamp)` — `<50 ms` target at 100k+ rows | unchanged; add read replicas |
| Windowed analytics | covering indexes `(timestamp, plate)`, `(timestamp, camera_code)`, `(vehicle_type)` — index-only scans | unchanged |
| Partial-plate search | `pg_trgm` GIN index | unchanged |
| Spatial queries | GiST on PostGIS point columns | unchanged |
| Retention | periodic bounded `DELETE` sweep; alert-referenced rows never purged | move to native monthly range **partitioning** (`PARTITION BY RANGE (timestamp)`) — drop old partitions in O(1) |
| Every list/search endpoint | `WHERE` + `LIMIT`/`OFFSET`, no unbounded scans; bulk lookups (no N+1) | unchanged |
| AI queries | hard ceiling `AI_MAX_RESULTS` (100); one grouped aggregate for anomaly scan | unchanged |

The AI layer does **not** re-process video — it reads `vehicle_events`.
So AI cost scales with *events*, not *cameras × FPS*.

## 3. The compute path to 80,000 (target design — see `SCALABILITY.md`)

| Tier | Cameras | Strategy |
| :--- | :--- | :--- |
| PoC | ~50 | this repo |
| Regional node | ~2,500 | edge-gateway inference clusters; **Kafka/Redis Streams** between ingest, AI and backend (replaces the in-process queue); GPU (Triton / TensorRT) |
| Statewide grid | ~80,000 | Kubernetes autoscaling of stateless AI worker pools sharded by camera; distributed MinIO; Postgres partitioning + read replicas + Citus/CockroachDB for the write tier; per-district tenancy |

Key point: **the API contract and the schema do not change**. A regional
node runs the same FastAPI backend against the same tables; only the
frame→detection compute is horizontally scaled and a durable queue is
inserted between ingest and AI.

## 4. Scalability story for the demo

1. *Reads are ready now* — indexed, bounded, partition-friendly. The
   `vehicle_events` design is the statewide design.
2. *The AI layer is cheap* — it operates on stored events, capped result
   sets, one aggregate per anomaly scan.
3. *Compute is the only thing that scales horizontally* — edge inference +
   a queue + stateless workers, all standard, all documented, none
   requiring a rewrite of what exists.
4. *No premature infrastructure* — we did not ship Kafka/K8s for a
   50-camera PoC; we shipped the schema and indexes that make the jump
   possible.
