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

---

## 4. Parallel AI worker pool + fair camera scheduling (Phase 2C — IMPLEMENTED, currently a net loss on this test host)

**What was built** (`ai/worker_pool.py`, opt-in via `SENTINEL_AI_WORKERS`,
default `1` = the exact pre-Phase-2C single-consumer-thread path,
byte-for-byte unchanged):

- **Fair per-camera scheduling** (`PerCameraLatestQueue`): each worker keeps
  at most ONE not-yet-consumed frame per camera it owns — a newer frame
  overwrites a pending one (the stale one is *counted*, `per_worker_stale_evicted`,
  never silently dropped), and cameras are served strict round-robin. This
  directly fixes the §3 FIFO-starvation finding (only 5 of 30 cameras ever
  got a frame) *for whichever cameras a worker owns* — memory is bounded by
  camera count, never by arrival rate, by construction.
- **Camera-sharded multi-process workers** (`AIWorkerPool`): cameras are
  assigned to exactly one of `SENTINEL_AI_WORKERS` OS processes via a
  deterministic hash (`zlib.crc32`, *not* Python's randomized `hash()` —
  verified stable across a freshly spawned process in
  `tests/test_worker_pool.py::test_deterministic_across_processes`). A
  camera's ByteTrack tracker, OCR consensus state, plate lock, and cooldown
  history therefore only ever exist inside the one worker process that owns
  it — two workers provably never touch the same camera's state
  concurrently, by disjoint-set construction, not by locking. Each worker
  loads its own `AIPipeline` (own YOLO/EasyOCR model, own Phase 2A async
  event-delivery queue+sender, otherwise completely unmodified).
- **Thread-pool oversubscription control**: each worker caps
  `OMP/MKL/OPENBLAS/NUMEXPR_NUM_THREADS` and `torch`/`cv2` thread counts to
  `cpu_count() // num_workers` before any heavy import, plus
  `OMP_WAIT_POLICY=PASSIVE`/`KMP_BLOCKTIME=0` so idle OpenMP threads yield
  instead of spin-waiting (a documented amplifier of multi-process
  contention) — necessary but, as measured below, **not sufficient** on
  this host.
- Extended metrics: worker ID, cameras-per-worker, per-worker/per-camera
  processed and stale-evicted counts, per-worker queue depth, per-worker
  CPU%/RSS, per-worker YOLO/OCR/send/end-to-end latency, plus a pool-wide
  `combined_latency` (count-weighted average; p50/p95 explicitly labeled
  "representative" from the largest-sample worker, not an exact pooled
  percentile — computing an exact one would require shipping every raw
  sample across the process boundary, a real per-frame cost this pass
  deliberately avoided).
- Correctness (camera isolation, deterministic sharding, round-robin
  fairness, stale-eviction counting, bounded memory, clean shutdown with no
  process/queue hang) is verified in `tests/test_worker_pool.py` with a
  stubbed pipeline factory — fast, and independent of real model timing.

**MEASURED — `SENTINEL_AI_WORKERS=1` (unchanged path), same 8-core host as
§3, `scripts/benchmark_pipeline.py`, `--no-backend`:**

| N cameras | processed FPS | dropped | starved cameras | CPU avg/max % | RSS max | YOLO p50 ms | OCR p50 ms |
| :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| 5  | 1.09 | 161 | 1/5   | 652/714 | 4505 MB | 45 | 169 |
| 10 | 0.97 | 241 | 7/10  | 638/714 | 4900 MB | 53 | 174 |
| 20 | 0.90 | 493 | 17/20 | 633/714 | 5762 MB | 44 | 165 |
| 30 | 0.70 | 710 | 28/30 | 599/721 | 6594 MB | 55 | 184 |

Consistent with §3: unchanged default behavior, same FIFO-starvation
pattern, same order-of-magnitude throughput.

**MEASURED — `SENTINEL_AI_WORKERS=2` and `=4`, same host, same 5/10/20/30-camera
tiers, 30-45s runs**: **zero frames processed at every single tier tested**
(`per_worker_resource_usage: []`, no post-startup log line from any
worker — confirmed from raw logs that both/all worker processes logged
`starting, cameras=[...]` and then produced nothing further within the run
window). A longer, dedicated 100-second run at `workers=2, N=5` (well past
any plausible model-load time) still only completed **6 frames total**
(0.06 FPS combined) with YOLO calls averaging **3552ms** and OCR calls
averaging **4752ms** — both roughly **80-100x** their `workers=1` baseline
(45ms / 169ms). CPU usage for the one worker that did report
(`cpu_percent_avg=515%`) was still below the single-worker baseline's 652%,
meaning the second worker was actively starving the first of CPU time, not
merely idling.

**Root cause (isolated and confirmed, not assumed)**: this is **host CPU
oversubscription**, not a defect in the fair-scheduling or camera-sharding
design. The test host is an 8-core shared desktop workstation (measured
`load average` up to 12.4 during these runs from an active browser/GUI
session, unrelated to Sentinel) with no CPU headroom to spare. Each of the
following was tested **in isolation** and found to scale correctly:
pure multi-process YOLO inference (thread-capped, 2 processes: 86ms/call,
unchanged from 1-process baseline), pure multi-process EasyOCR inference
(2 processes: 101ms/call vs 110ms 1-process — ~2.2x combined throughput),
and the fair-queue routing/sharding architecture itself (stub pipeline,
zero real model cost: 802 frames/30s, perfectly even round-robin splits,
zero handoff drops). The regression appears **only** when real ingestion
(OpenCV/FFmpeg decoding several real camera streams in the main process)
runs *concurrently* with 2+ real (unstubbed) YOLO+EasyOCR worker processes
on this specific host — the combined CPU demand (ingestion decode + N
independent multivariant-OCR-and-YOLO processes, each wanting several
BLAS/OpenMP threads even after capping) exceeds the 8 physical cores badly
enough to cause severe OS-scheduler thrashing, not a mild slowdown.
`workers=1` alone already runs at 599-652% CPU (out of ~800% max) — there
is no real headroom left for a second full worker on this host before
inference latency itself inflates.

**Honest conclusion**: the Phase 2C architecture (fair per-camera
scheduling, deterministic camera-to-worker sharding, provable per-camera
state isolation) is implemented correctly and is verified correct in
isolation — but it delivers **no throughput benefit, and currently a
severe regression, on this specific 8-core test host**, because that host
does not have enough spare CPU to run a second real inference worker
alongside the first. **`SENTINEL_AI_WORKERS>1` is not recommended on
hardware resembling this reference host** — enabling it makes real
end-to-end throughput dramatically worse (0.06 FPS vs. 0.7-1.1 FPS), not
better. It would be expected to help only where either (a) the host has
enough additional physical cores that each worker's own thread budget
(`cpu_count()//num_workers`) stays reasonably close to what a single
worker already needs (~6-7 cores' worth of BLAS/OpenMP parallelism on this
dataset), or (b) inference moves off the CPU entirely (GPU) so each
worker's CPU footprint shrinks far below one physical core — neither of
which this pass attempted (explicitly out of scope). This is reported as a
genuine, measured finding, not a hidden failure: **do not enable
`SENTINEL_AI_WORKERS>1` in production until it has been re-benchmarked on
the actual target deployment hardware** and shown a net improvement there.

**Real Sentinel camera validation, unaffected by this pass**: all
previously-confirmed-working real cameras (cam04 H.264, cam06/cam22
H.265, cam15 H.264, plus MOCK_CAM01/02) were re-smoke-tested after this
change and connect/decode exactly as before (`status=OK`, correct codec
detected, PTS-monotonic, credentials never logged). cam30's prior
no-frames finding from the full 30-camera validation pass is a
source/network issue on that one feed, unrelated to and unaffected by this
change.

**NOT attempted this pass** (explicitly out of scope, per the task brief):
GPU inference, Kafka/RabbitMQ/Redis, Kubernetes, re-identification, and any
attempt to "fix" the oversubscription by reducing per-worker thread counts
further than `cpu_count()//num_workers` (would only shrink each worker's own
throughput proportionally — it does not address that ingestion + N workers
together exceed the host's total core budget). The **next real step**, not
done here, is re-running this exact same matrix on hardware with
meaningfully more spare cores (or a GPU) before recommending
`SENTINEL_AI_WORKERS>1` for any real deployment.

---

## 5. Fair scheduling for the DEFAULT (single-consumer) path + capacity model (Phase 17)

Section 4 fixed FIFO-starvation for the multi-process pool, then found
that pool currently costs more than it saves on this host — leaving the
DEFAULT (`SENTINEL_AI_WORKERS=1`) path's own FIFO starvation (§3) still
unfixed. Phase 17 (`docs/SCALE_TO_80000.md` §5, full data in
`docs/PHASE17_BENCHMARK.md`) added a second, independent fix for the
*same* bug that changes SERVICE ORDER, not parallelism —
`ai/scheduled_consumer.py`'s `ScheduledFrameConsumer`, opt-in via
`--fair-scheduler`. It reproduces the exact FIFO-starvation finding above
(6 of 10 mock cameras get zero processed frames with the plain consumer),
and does serve every camera when enabled — but **measured LOWER real
AI-processed throughput than the FIFO baseline on this same 8-core host**
(an extra scheduling thread competing for CPU/GIL time against the one
real inference thread), so it too ships default-**off**, for the same
class of reason as `SENTINEL_AI_WORKERS>1` above. Two independent
attempts at scheduling infrastructure around one CPU-bound inference
thread, two measured net costs on this hardware — that pattern is itself
now the strongest evidence for what §2's Kafka/K8s/GPU roadmap was always
arguing: the fix is more real compute (regional workers, eventually GPU),
not more scheduling cleverness on one host. Phase 17 also added a
transparent capacity formula (`ai/capacity.py`) that turns this section's
own ~1 FPS/worker measured ceiling into an honest required-worker count
for 80,000 cameras instead of an arbitrary division — see
`docs/PHASE17_BENCHMARK.md` §6 for the full, assumption-labeled
calculation.
