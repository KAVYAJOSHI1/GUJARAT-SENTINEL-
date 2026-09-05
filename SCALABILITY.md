# SENTINEL — Statewide Scalability Roadmap (50 to 80,000 Cameras)

> **ROADMAP — not implemented.** Everything below (Kafka/RabbitMQ,
> Kubernetes, NVIDIA Triton, PostgreSQL partitioning at the statewide tier)
> is a target architecture, evaluated against no infrastructure that exists
> in this repository today. The current implementation is a single-node
> `docker-compose.yml` stack — one Postgres+PostGIS instance, one MinIO
> node, one FastAPI backend, CPU-only inference (`device="cpu"` hardcoded),
> and an in-process `queue.Queue` for frame handoff, correctly scoped to its
> stated **~50-camera PoC** target. See `SENTINEL_System_Audit_Report.md`
> §7 for the full code-verified gap analysis between this document and the
> actual codebase. Nothing here is deleted — it remains a legitimate
> **production target**, just not a description of the system as it runs
> today.

---

## 1. Multi-Tier Scaling Strategy

| Scale Tier | Camera Count | Ingestion Throughput | Primary Infrastructure Strategy |
| :--- | :--- | :--- | :--- |
| **PoC Phase** | ~50 Feeds | ~1,250 FPS Total | Single node Docker Compose stack |
| **Regional Node** | ~2,500 Feeds | ~62,500 FPS Total | Edge gateway clusters + Distributed Kafka |
| **Statewide Grid** | ~80,000 Feeds | ~2,000,000 FPS Total | Kubernetes (K8s) auto-scaling + MinIO distributed Object Storage |

---

## 2. Horizontal Ingestion & AI Worker Pools

To support 80,000 streams:
1. Stream ingestion workers decouple from AI inference using Kafka/RabbitMQ frame queues.
2. AI inference nodes auto-scale based on queue backlog metrics using NVIDIA Triton Inference Server.
3. PostgreSQL partition management separates historical logs from active hot queries.

---

## 3. What's actually measured today (Phase 2A — IMPLEMENTED, single-node)

Before this pass, none of the numbers above were backed by an actual
measurement of the current single-node system — see
`SENTINEL_System_Audit_Report.md` Part II. This is now partially closed:

- `ai/pipeline.py` reports real, monotonic-clock instrumentation
  (`get_metrics()`): event-queue depth/backpressure, YOLO/OCR/event-send/
  end-to-end latency (p50/p95, not just an average), per-camera frame/event
  counts, and CPU%/RSS. `ingestion.stream_health.HealthRegistry` gained
  reconnect *duration* (count already existed).
- The AI→backend event POST is no longer synchronous in the inference hot
  path — a bounded queue + background sender thread handles it, with every
  drop (queue-full, backend-rejected, retry-buffer-full) counted, never
  silent. See README.md §3 for the measured result of one real run.
- `scripts/benchmark_pipeline.py` is a reusable harness for the 1/5/10/20/30
  camera load ladder the audit's Part II described — it has been run at 2
  cameras (see README.md §3); the full ladder has not been run yet.

**Still ROADMAP, unaffected by this pass**: everything in §1/§2 above
(Kafka/RabbitMQ, Kubernetes, Triton, PostgreSQL partitioning, GPU inference,
Redis-backed WebSocket fan-out) — none of it exists in code, and this pass
deliberately did not add it (see the task brief this was implemented under:
"measure first," not "add distributed infrastructure"). Closing the
single-CPU-consumer-thread bottleneck the benchmark run reconfirmed still
requires the GPU/worker-pool work described in §8 of the audit report, not
attempted here.
