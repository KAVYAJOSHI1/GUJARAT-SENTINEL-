# Scaling Sentinel: 50 → 80,000 Cameras

> **The full target design (Kafka, Kubernetes, Triton, statewide Postgres
> partitioning, distributed MinIO) is in the repo-root
> [`SCALABILITY.md`](../SCALABILITY.md)** — with a measured load ladder
> (5/10/20/30 cameras) and an honest gap analysis vs. what runs today.
> This file is the submission-level summary.
>
> **Phase 17 (real-time multi-camera AI + capacity engineering)** added a
> fair per-camera scheduler, adaptive sampling, explicit processing modes,
> bounded async OCR, measurable HEALTHY/DEGRADED/OVERLOADED states, a
> transparent capacity model, and a tiered (SIMULATED/DECODED/AI-PROCESSED)
> benchmark harness — see [`PHASE17_BENCHMARK.md`](PHASE17_BENCHMARK.md)
> for the actual measured numbers this file's §5 below is built from.
> None of it changes the conclusion below that compute (not scheduling,
> not the schema) is the real bottleneck to 80,000 cameras — Phase 17
> makes that bottleneck precisely measurable and gives it a scaling
> formula instead of a guess.
>
> **Phase 18** measured *why* real footage returns `UNKNOWN` (see
> [`PHASE18_ANPR_DIAGNOSTICS.md`](PHASE18_ANPR_DIAGNOSTICS.md)) — the
> capacity model's `anpr_percentage` / `anpr_cost_multiplier` assumptions
> (§5/§6 below and `ai/capacity.py`) already account for ANPR being the
> expensive path per camera; Phase 18 confirms that expense is not wasted
> on this dataset's footage (OCR genuinely attempts and genuinely mostly
> fails on low-detail wide-area crops), not that the assumption itself
> needs to change.

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

## 5. Phase 17 — what's now REAL vs. what's still target design

Everything in this section is code in this repo today, not a roadmap
item — contrast with §3's Kafka/K8s/Triton row, which remains
deliberately unbuilt.

| Capability | Status | Where |
| :-- | :-- | :-- |
| Bounded, priority-weighted fair camera scheduler | **Built + benchmarked** | `ai/scheduler.py` |
| Adaptive per-camera frame sampling (target/min/max FPS, priority + load influence) | **Built + tested** | `ai/sampling.py` |
| Explicit DETECTION/TRACKING/ANPR/ALERT processing modes | **Built + tested** | `ai/modes.py` |
| Bounded, async OCR execution (opt-in) | **Built + tested** | `ai/ocr_executor.py` |
| Measurable HEALTHY/DEGRADED/OVERLOADED states | **Built + tested** | `ai/degradation.py` |
| Transparent 80k capacity calculation from a measured baseline | **Built + tested** | `ai/capacity.py`, `GET /api/v1/system/capacity` |
| Regional grouping (Ahmedabad/Surat/Rajkot/Vadodara/Other) | **SIMULATED** — deterministic grouping only, no real distributed deployment | `ai/regions.py` |
| Kafka/RabbitMQ/Redis Streams, Kubernetes, Triton, distributed MinIO | Still roadmap, unbuilt | `SCALABILITY.md` §1-2 |

**The headline measured result** (full detail: `PHASE17_BENCHMARK.md`):
the fair scheduler provably fixes the FIFO-starvation bug — a flooding
camera cannot starve others (automated regression test), and at N=10
cameras the plain FIFO consumer this Phase measured leaves 6 of 10
cameras fully starved, exactly reproducing `SCALABILITY.md` §3's earlier
finding. But on this project's CPU-only development hardware, using the
fair scheduler for *real* AI inference measured **slower**, not faster,
than the FIFO baseline (extra scheduling-thread overhead competing for
CPU/GIL time on an already CPU-saturated single inference thread) — so it
ships **off by default**, exactly like `ai/worker_pool.py`'s
multi-process pool before it. The pattern repeating twice is itself the
finding: **on this class of hardware, the single real inference thread is
the bottleneck, and infrastructure built around it (multi-process
sharding, or now fair scheduling) has a real, measurable cost that must
clear a bar before it's worth enabling** — this is exactly the argument
for the GPU/regional-worker path in §3, not a reason to add more
single-host scheduling machinery.

The transparent capacity formula (`ai/capacity.py::compute_capacity`)
turns that same measured ~1 FPS/worker ceiling into an honest 80k-camera
worker count instead of an arbitrary division: at a demanding 2 FPS/
camera ANPR-heavy target it says **~131,000 workers** (worse than 1:1,
correctly reflecting this hardware's real ceiling); at a more realistic
mixed workload (0.5 FPS, 10% ANPR) it says **~23,000 workers** — see
`PHASE17_BENCHMARK.md` §6 for the full assumption-by-assumption
breakdown. **Neither number is a claim that Sentinel serves 80,000
cameras today** — both are what the formula outputs from a real
measurement plus named, adjustable assumptions, and both point the same
direction §3 already did: the path to 80,000 is more workers (regional,
eventually GPU-backed), not more scheduling cleverness on one CPU.
