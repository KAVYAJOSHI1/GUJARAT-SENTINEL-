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
  camera load ladder the audit's Part II described — it has now been run at
  all five tiers (1/5/10/20/30 MOCK cameras, one 8-core host, 45s each,
  `--no-backend`). Full table + analysis: README.md §3b.

**Load-ladder headline result (MEASURED, README.md §3b has the full
table)**: total pipeline throughput is **flat at ~1.0–1.3 processed
frames/sec regardless of camera count (1 through 30)** — the single
`FrameConsumer` thread is already the hard ceiling at N=1 on this host/
dataset, not something that only appears at higher camera counts. CPU is
already near its ~800%-of-8-cores ceiling (667% avg) at N=1 and stays flat
through N=30. This directly confirms, with real numbers rather than
architectural inference, this document's own §7-of-the-audit conclusion
that the current single-process design does not scale past a handful of
cameras without the GPU/worker-pool changes in §2 above — it is not a
50-camera-vs-30,000-camera question, it is already the binding constraint
at 1 camera on CPU.

A related but distinct finding: at N≥10, only 5 of N cameras ever get a
processed frame in a 45s run (the rest are fully starved) — this is a FIFO
frame-queue fairness artifact (worker start order determines who fills the
queue first), not the same thing as the CPU ceiling, and was intentionally
NOT fixed this pass (the safe fix needs a different queue/eviction
structure, more than the "smallest safe change" this pass allowed for).

**Still ROADMAP, unaffected by this pass**: everything in §1/§2 above
(Kafka/RabbitMQ, Kubernetes, Triton, PostgreSQL partitioning, GPU inference,
Redis-backed WebSocket fan-out) — none of it exists in code, and this pass
deliberately did not add it (see the task brief this was implemented under:
"measure first," not "add distributed infrastructure"). Closing the
single-CPU-consumer-thread bottleneck the benchmark run reconfirmed still
requires the GPU/worker-pool work described in §8 of the audit report, not
attempted here. The 1,250 FPS / 62,500 FPS / 2,000,000 FPS figures in §1
above remain entirely aspirational — the measured total across this
codebase's actual single-consumer-thread design tops out at ~1.3 FPS
regardless of camera count, a ~1,000x gap from even the stated PoC-tier
target that no config change closes; only GPU inference and true worker
parallelism (§2 above, not implemented) can.
