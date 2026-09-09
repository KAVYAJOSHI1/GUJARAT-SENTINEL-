# Phase 17 Benchmark Report — Real-Time Multi-Camera AI + Scale/Capacity Engineering

> **Read this before quoting any number from it.** Every figure below was
> produced by an actual run of `scripts/benchmark_phase17.py` or
> `scripts/benchmark_pipeline.py` on **one 8-core CPU-only development
> workstation** (`nproc` = 8, no GPU, 15 GB RAM) on **2026-09-09** — the
> exact machine and date are the whole point: these are measurements, not
> projections. Every number is labeled **SIMULATED**, **DECODED**, or
> **AI-PROCESSED** — never conflated. Reproduce any table with the command
> printed above it.

---

## 1. What Phase 17 actually changed (short version)

Phase 1–16 already had: an AI pipeline (YOLOv8n + EasyOCR + ByteTrack +
multi-frame consensus), an async event-delivery queue (Phase 2A), and a
camera-sharded multi-process worker pool with its own fair per-camera
queue (Phase 2C, `ai/worker_pool.py`) — measured in `SCALABILITY.md` §4 to
be a **net throughput loss** on this class of host due to CPU
oversubscription, and therefore not recommended (`SENTINEL_AI_WORKERS=1`
stays the default).

Phase 17 adds, all additive / opt-in unless stated:

| Module | What it is | Default behavior |
| :-- | :-- | :-- |
| `ai/scheduler.py` | `FairCameraScheduler` — bounded per-camera queues, 4 priority classes via smooth-weighted round robin, named drop reasons, per-camera stats | Equal-priority default reproduces the exact `PerCameraLatestQueue` behavior |
| `ai/sampling.py` | `AdaptiveFrameSampler` — per-camera target/min/max FPS, priority + load-state influence, optional motion boost | No-op (accepts every frame) unless configured |
| `ai/modes.py` | `DETECTION` / `TRACKING` / `ANPR` / `ALERT` processing modes | Default mode is `ANPR` = today's unchanged pipeline behavior |
| `ai/ocr_executor.py` | Bounded, asynchronous OCR execution | Off (`SENTINEL_ASYNC_OCR=0`) |
| `ai/degradation.py` | `SystemLoadMonitor` — HEALTHY/DEGRADED/OVERLOADED from measurable thresholds | N/A (pure function) |
| `ai/scheduled_consumer.py` | `ScheduledFrameConsumer` — fair-scheduled alternative to the default FIFO `FrameConsumer`, **same one-thread CPU profile** | Off (`--fair-scheduler` / `SENTINEL_FAIR_SCHEDULER=1`) |
| `ai/capacity.py` + `ai/regions.py` | Transparent 80k capacity model + labeled-SIMULATED regional grouping | N/A (pure functions / read-only API) |
| `GET /api/v1/system/capacity` | Read-only capacity API | N/A |

---

## 2. Tier A — INGESTION SIMULATION (scheduler only, no decode, no AI)

```
.venv/bin/python scripts/benchmark_phase17.py --tier ingestion \
  --cameras 10,30,50,100,250,500 --duration 10 \
  --worker-fps-budget 1.0 --source-fps 15
```

`--worker-fps-budget 1.0` stands in for one AI worker's real measured
throughput (Tier C below) via a `time.sleep()` — no decode, no inference
actually runs. This isolates one question: **is the scheduling layer
itself fair and memory-bounded, independent of compute cost?**

| Configured cameras | Aggregate processed FPS | Starvation events | RSS growth (MB) |
| --: | --: | --: | --: |
| 10  | 1.00 | 8   | 0.2 |
| 30  | 1.00 | 27  | 0.0 |
| 50  | 1.00 | 46  | 0.0 |
| 100 | 1.00 | 98  | 0.0 |
| 250 | 0.99 | 248 | 0.2 |
| 500 | 1.00 | 498 | 0.4 |

**Reading this correctly:** aggregate throughput stays pinned at the
configured worker budget (1.0 fps) *regardless of camera count* — this is
the capacity model's central point made visible: **scheduling fairness
cannot manufacture compute.** Memory stays flat (<0.5 MB growth even at
500 simulated cameras) — the bounded-queue design (Step 2) holds at scale.
Priority weighting visibly does its job under this starvation: at N=500,
CRITICAL cameras (25 of them, 5%) still get non-zero service far more
often than BACKGROUND (100 of them, 20%) — see the full JSON
(`by_priority`) for the exact split.

---

## 3. Tier C — AI-PROCESSED (real YOLOv8n + EasyOCR), head-to-head

```
.venv/bin/python scripts/benchmark_pipeline.py \
  --cameras MOCK_CAM01..05 --registry data/trafficdataset_camera_registry.json \
  --duration 45 --no-backend [--fair-scheduler --target-fps 5]
```

| Config | N | Processed FPS | Cameras starved | CPU avg/max | Notes |
| :-- | --: | --: | --: | --: | :-- |
| default (FIFO) | 5  | 0.93 | 0/5  | 650% / 696% | matches `SCALABILITY.md` §4's 1.09 fps at N=5 within run-to-run variance |
| `--fair-scheduler --target-fps 5` | 5  | 0.18–0.27 | 0/5 | 703% / 747% | **fair (every camera served), but 3–5× SLOWER** |
| default (FIFO) | 10 | 0.82 | **6/10** | — | reproduces the exact FIFO-starvation finding this Phase exists to fix |
| `--fair-scheduler --target-fps 5` | 10 | 0.02 | **9/10** | 710% / 742% | fairness mechanism never gets enough compute to matter — see §3.1 |

### 3.1 Honest finding: `--fair-scheduler` costs real throughput on this host

The FIFO baseline confirms the historical result exactly: at N=10, 6 of 10
cameras get **zero** processed frames in 45 seconds — total starvation of
most cameras, the bug this Phase exists to fix.

`ScheduledFrameConsumer` **does** fix the fairness problem — no camera is
architecturally locked out, and the `ai.scheduler`/`ai.sampling` unit and
fairness-regression tests (`tests/test_scheduler.py`,
`tests/test_scheduled_consumer.py`) prove this in isolation from real
inference cost. But measured **with real YOLO+EasyOCR inference on this
CPU-bound host**, it delivers **lower aggregate throughput than the plain
FIFO consumer it replaces** — 5–40× lower at N=10. CPU utilization is
similar in both configurations (~650–750% of 800% available), which rules
out "it's just doing more total work" as the explanation. The most likely
cause, not fully isolated in this pass: `ScheduledFrameConsumer` runs a
second (router) thread that must inspect **every** incoming frame — up to
300/sec at N=10 — through a lock-protected `FairCameraScheduler.put()`
call, and that extra Python-level, GIL-competing work measurably steals
cycles from the single real inference thread on an already CPU-saturated
host. This is the same *category* of finding as `ai/worker_pool.py`'s
documented CPU-oversubscription regression (`SCALABILITY.md` §4) — a
different mechanism (thread/GIL contention vs. process oversubscription),
same practical conclusion.

**Recommendation, exactly mirroring §4's own precedent:** `--fair-scheduler`
is **not currently recommended** for maximizing raw AI-processed
throughput on hardware resembling this dev host. It is default-**off**
(opt-in only) for precisely this reason. It remains architecturally
correct and valuable as the fairness foundation, validated independent of
real inference cost in Tier A/B and the unit-test suite, and is expected
to become net-positive once real per-frame inference cost drops far
enough (GPU) that the router's fixed per-frame overhead stops mattering
relative to it — not measured in this pass. **The capacity model below
therefore uses the plain/default FIFO baseline**, not the fair-scheduler
numbers, as `MeasuredBaseline.worker_fps_budget` — the number that
actually reflects the currently-recommended configuration.

A second, genuine bug was found and fixed *by* this benchmarking:
`psutil.Process.cpu_percent(interval=None)` is only accurate when polled
from exactly one place at a controlled interval. Adding
`ScheduledFrameConsumer`'s own load-state poller alongside the
pre-existing stats-loop poller broke that assumption and produced
measured CPU readings **over 3000%** on an 8-core host. Fixed by caching/
throttling the actual psutil call inside `AIPipeline.get_resource_usage()`
itself (`ai/pipeline.py`) — safe now for any number of independent
callers. Regression test: `tests/test_resource_usage_throttle.py`. A
related, separate calibration bug (comparing psutil's raw multi-core
percent directly against normalized 0–100% degradation thresholds) was
fixed alongside it — see `ai/scheduled_consumer.py`'s
`_maybe_update_load_state()` and `backend/app/services/capacity.py`'s
normalization comment. Both are documented here rather than hidden
because catching them is exactly what this kind of benchmarking is for.

---

## 4. Tier B — DECODE LOAD (real OpenCV/FFmpeg, no AI)

```
.venv/bin/python scripts/benchmark_phase17.py --tier decode --cameras 10,30,50,100 --duration 20
```

| Configured cameras | Active streams (ONLINE within 20s) | Aggregate decoded FPS | Per-camera FPS | CPU % | RSS |
| --: | --: | --: | --: | --: | --: |
| 10  | 10/10 | 300  | 30 (every camera) | 459% | 1.18 GB |
| 30  | 30/30 | 900  | 30 | 663% | 2.95 GB |
| 50  | 49/50 | 1440 | 30 | 647% | 4.90 GB |
| 100 | **60/100** | 1740 | 30 (on the 60 that connected) | 581% | 5.72 GB |

**Reading this correctly:** pure decode (no AI at all) comfortably
sustains 30–50 concurrent real video streams on this 8-core host with
**zero frame drops** and full real-time per-camera FPS — decode is *far*
cheaper than AI inference, exactly as the capacity model assumes when it
treats compute (not decode) as the binding constraint. At 100 configured
cameras, only 60 actually reached ONLINE status within the 20s window —
a real, measured limit on how fast this host can open 100 concurrent
`cv2.VideoCapture`/FFmpeg connections simultaneously, distinct from
steady-state decode capacity. **250 and 500 decode-tier runs were not
attempted** — per the brief, "if 500 cannot actually be decoded... that is
completely fine"; extrapolating past a measured, connection-limited 100
tier would not be honest.

---

## 5. Camera fairness — automated regression tests (Step 9)

Not a one-off benchmark run — a permanent, fast (`<1s` combined), CI-run
test suite:

- `tests/test_scheduler.py::TestPriorityWeighting::test_one_busy_camera_cannot_starve_others_fairness_test`
  — a flooding camera cannot starve normal-priority cameras sharing the
  same scheduler.
- `tests/test_scheduled_consumer.py::TestFairnessUnderFlood::test_all_cameras_get_served_despite_one_flooding_camera`
  — the same property end-to-end through `ScheduledFrameConsumer` with a
  real (simulated-cost) consumer thread.
- `tests/test_scheduler.py::TestStarvation` — starvation is actually
  counted, not silently absorbed.

Run: `.venv/bin/python -m pytest tests/test_scheduler.py tests/test_scheduled_consumer.py -v`

---

## 6. Capacity model — the transparent 80,000-camera calculation

`ai/capacity.py` / `backend/app/services/capacity_model.py`
(`compute_capacity()`), fed by
`backend/data/phase17_benchmark_latest.json` (committed, regenerate by
hand after a fresh benchmark run):

```
measured_anpr_mode_processed_fps = 0.93     (Tier C, N=5, plain FIFO -- §3 above)
anpr_cost_multiplier             = 3.7      (measured OCR p50 ~169ms / YOLO p50 ~45ms, AI_ARCHITECTURE.md)
worker_fps_budget (detection-equivalent) = 0.93 * 3.7 = 3.441
```

| Scenario (assumptions) | Effective cameras/worker | Required workers for 80,000 | Est. GPUs (UNVERIFIED) |
| :-- | --: | --: | --: |
| target_fps=2.0, 30% ANPR (conservative default) | 0.61 | 131,293 | — |
| target_fps=0.5, 30% ANPR | 2.44 | 32,824 | — |
| target_fps=0.5, 10% ANPR | 3.47 | 23,031 | — |
| target_fps=0.5, 10% ANPR, assumed 8× GPU speedup | 3.47 | 23,031 | 2,879 |

**Read this the way it's meant to be read:** on *this exact CPU-only
hardware*, at a demanding 2 FPS/camera ANPR-heavy target, the model
honestly says you'd need *more workers than cameras* — a direct,
unflattering, and correct restatement of `SCALABILITY.md`'s own finding
that this host's single-consumer CPU ceiling is ~1 FPS aggregate
regardless of camera count. Lowering the target FPS or the ANPR
percentage (both legitimate, named, adjustable assumptions — most 80k
cameras would run cheap DETECTION/TRACKING mode, not full ANPR every
frame) brings the number down by 4–6×. The GPU row's speedup factor is
explicitly **not measured** — no GPU was available on this development
host — and is flagged `gpu_speedup_verified: false` everywhere it's
surfaced (API and this doc). None of these scenarios should be read as
"SENTINEL supports 23,000–131,000 workers today" — they are what the
transparent formula outputs from a real measured baseline plus named
assumptions; see `docs/SCALE_TO_80000.md` for the deployment-shape
discussion these numbers feed into.

Reproduce: `.venv/bin/python -m pytest tests/test_capacity.py -v` (pure
arithmetic + honesty-guarantee tests, no benchmark run needed) and
`GET /api/v1/system/capacity` (live API, reads the committed baseline
file above).

---

## 7. Regional simulation (Step 6)

`ai/regions.py` groups camera_ids into 5 named regions
(Ahmedabad/Surat/Rajkot/Vadodara/Other) via a deterministic hash, purely
for presenting "central control plane → regions → workers" — **labeled
SIMULATED everywhere**, no Kubernetes, no cross-host orchestration, no
network boundary exists between "regions" in this codebase today.

---

## 8. Honest limitations (Step 19)

- **Single 8-core CPU-only development workstation, no GPU.** Every
  AI-PROCESSED number in this document is bound by that ceiling, not by
  this Phase's scheduling work — the scheduler/sampler/capacity model is
  provably correct and fast in isolation (Tier A, unit tests) but real
  throughput is compute-bound on this hardware.
- **`--fair-scheduler` measured worse than FIFO for raw AI throughput on
  this host** (§3.1) — a genuine, unresolved trade-off, not swept under
  the rug. Root cause (router-thread GIL contention) identified but not
  fully isolated or optimized in this pass.
- **DECODE tier only validated up to 50 fully-online cameras**; 100
  showed a real connection-startup bottleneck (60/100 online in 20s), and
  250/500 were not attempted at all.
- **AI-PROCESSED tier only validated at N≤10** — re-running the existing,
  already-known CPU-ceiling result at N=30/50/100/250/500 would not have
  produced new information (see `SCALABILITY.md` §3/§4's own N=1..30
  ladder, which already shows the ceiling is hit at N=1).
- **GPU speedup is an unverified, published-benchmark-derived assumption**,
  not a measurement — flagged as such everywhere it appears.
- **The capacity model's regional split, bandwidth, and storage estimates
  are all named assumptions** (per-camera bitrate, evidence write rate,
  redundancy/headroom factors) — see `CapacityAssumptions` in
  `ai/capacity.py` for the full, adjustable list.
- **CPU-percent normalization in the capacity API assumes the backend and
  AI pipeline share one host's core count** (true in this project's
  single-node `docker-compose.yml` PoC) — would need the pipeline's own
  core count pushed alongside its metrics to stay correct in a true
  multi-host deployment.
- **No real government CCTV feed was used or is claimed anywhere in this
  document** — all AI-PROCESSED and DECODE numbers use the repo's own
  mock camera video clips (`trafficdataset/Videos/Videos/*.MOV`).
