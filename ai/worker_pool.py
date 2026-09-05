"""
ai/worker_pool.py

Phase 2C -- camera-sharded, multi-process AI worker pool + fair per-camera
scheduling.

Only active when SENTINEL_AI_WORKERS > 1 (scripts/run_pipeline_service.py
takes the exact pre-Phase-2C single-consumer-thread path otherwise --
default behavior is unchanged). This module changes how frames get from
the EXISTING ingestion frame_queue (ingestion/stream_manager.py,
completely untouched) to the AI pipeline(s); it does not touch ingestion,
RTSP handling, PTS timing, or reconnect logic at all.

Why (see SENTINEL_System_Audit_Report.md Part II and the Phase 2B
benchmark): a plain FIFO queue.Queue drained by one AI consumer thread
starves most cameras once the camera count exceeds what one CPU-bound
consumer can service -- measured: only ~5 of 30 cameras ever got a single
processed frame in a 45s run, regardless of camera count. This module
fixes that with two independent, separable changes:

  1. FAIR SCHEDULING (PerCameraLatestQueue): each worker keeps at most ONE
     pending (not-yet-consumed) frame per camera it owns. A newer frame
     for a camera that already has one pending overwrites it -- the stale
     one is counted (never silently dropped) instead of queueing behind
     it. Cameras are served round-robin, so every camera with a pending
     frame gets a turn before any camera gets a second one. Memory is
     bounded by construction: at most one FrameEnvelope resident per
     camera assigned to that worker, never an unbounded backlog.

  2. PARALLEL WORKERS (AIWorkerPool): cameras are deterministically
     sharded across SENTINEL_AI_WORKERS separate OS processes
     (multiprocessing, not threading -- YOLO/OCR inference is CPU-bound
     Python/native work and each worker needs its own model loaded in
     memory; that memory cost is real and reported honestly in the
     benchmark, never hidden). A camera is assigned to exactly ONE worker
     for the pool's entire lifetime (camera_worker_index()) -- its
     ByteTrack tracker, OCR consensus state, and cooldown-relevant history
     therefore only ever exist inside that one worker's own AIPipeline
     instance. Two workers can never process the same camera's frames
     concurrently BY CONSTRUCTION (disjoint camera sets), not by locking
     shared state.

Each worker process reuses ai.pipeline.AIPipeline and
ai.adapter.ingestion_bridge.envelope_to_frame_input completely unchanged,
including Phase 2A's async bounded-queue event sender -- only the
INGESTION-SIDE hand-off (which frame reaches which pipeline instance, and
in what order) is new.
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import threading
import time
import zlib
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("sentinel.ai.worker_pool")


def camera_worker_index(camera_id: str, num_workers: int) -> int:
    """Deterministic, STABLE camera -> worker assignment (never Python's
    randomized hash() -- that would assign the same camera to different
    workers across runs/processes, since PYTHONHASHSEED differs by
    default). The same camera_id always maps to the same worker index for
    a given num_workers."""
    if num_workers <= 1:
        return 0
    return zlib.crc32(camera_id.encode("utf-8")) % num_workers


class PerCameraLatestQueue:
    """Bounded, fair, per-camera "latest frame wins" hand-off structure.

    At most one item resident per camera_id that has ever called put() --
    memory is bounded by the number of DISTINCT cameras assigned to this
    queue, never by frame arrival rate (this is the Task 2 "no unbounded
    queue" requirement). get() serves cameras round-robin: a camera only
    gets a second turn after every OTHER camera with a currently-pending
    frame has had one -- this is the actual fairness fix.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._latest: Dict[str, Any] = {}
        self._order: "deque[str]" = deque()
        self._stale_evicted: Dict[str, int] = {}

    def put(self, camera_id: str, item: Any) -> None:
        with self._not_empty:
            if camera_id in self._latest:
                # A not-yet-consumed frame for this camera is being
                # overwritten -- reported explicitly, never silent.
                self._stale_evicted[camera_id] = self._stale_evicted.get(camera_id, 0) + 1
            else:
                self._order.append(camera_id)
            self._latest[camera_id] = item
            self._not_empty.notify()

    def get(self, timeout: float = 0.5) -> Optional[Tuple[str, Any]]:
        with self._not_empty:
            if not self._order:
                self._not_empty.wait(timeout=timeout)
            if not self._order:
                return None
            camera_id = self._order.popleft()
            item = self._latest.pop(camera_id, None)
            return camera_id, item

    def depth(self) -> int:
        """Number of DISTINCT cameras with a currently-pending frame."""
        with self._lock:
            return len(self._order)

    def stale_evicted_snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._stale_evicted)


def _default_pipeline_factory(*, backend_url: str, evidence_dir: str, device: str):
    """The REAL AIPipeline construction, used in production. Overridable
    (AIWorkerPool(..., pipeline_factory=...)) purely for fast tests that
    want to exercise the routing/sharding/fairness logic in a real,
    separate process without paying YOLO/EasyOCR's load cost -- the
    factory must be a module-level (picklable) callable, since it crosses
    the `spawn` process boundary by reference."""
    from ai.pipeline import AIPipeline

    return AIPipeline(backend_url=backend_url, evidence_dir=evidence_dir, device=device)


def _report_metrics(metrics_queue, worker_id: int, camera_ids: List[str], pipeline, frames_processed: int) -> None:
    try:
        metrics_queue.put_nowait({
            "worker_id": worker_id,
            "camera_ids": list(camera_ids),
            "frames_processed": frames_processed,
            "metrics": pipeline.get_metrics(),
            "ts": time.time(),
        })
    except Exception:  # noqa: BLE001 -- metrics reporting must never crash a worker
        pass


def _ai_worker_main(
    worker_id: int,
    camera_ids: List[str],
    in_queue,
    metrics_queue,
    stop_event,
    *,
    backend_url: str,
    ingest_api_key: Optional[str],
    evidence_dir: str,
    device: str,
    no_backend: bool,
    stats_interval: float,
    pipeline_factory: Callable[..., Any] = _default_pipeline_factory,
    num_workers: int = 1,
) -> None:
    """Entry point run inside its OWN process (multiprocessing 'spawn').

    Owns exactly one AIPipeline instance (own model, own per-camera
    tracker/consensus/OCR-throttle state, own Phase-2A async event
    sender), scoped to exactly `camera_ids`. No other worker process ever
    sees frames from these cameras -- there is no cross-process state to
    synchronize, and no locking is needed for correctness.
    """
    # CRITICAL, must happen before ANY torch/cv2/numpy import (including
    # the one inside pipeline_factory() below): by default, each of these
    # processes independently claims ALL visible CPU cores for its own
    # BLAS/OpenMP thread pool (torch's own heuristic, PLUS OpenCV's, PLUS
    # EasyOCR's own torch backend). Running N such processes concurrently
    # therefore oversubscribes the host's real core count by roughly Nx,
    # and the resulting thread-contention/context-switch thrashing is
    # severe, not mild: measured, YOLO inference went from a ~40ms
    # single-worker baseline to 6000ms+ per call at num_workers=2 with no
    # thread-count limit in place. Dividing the host's cores evenly across
    # workers keeps total thread subscription roughly the same as the
    # single-worker case.
    threads = max(1, (os.cpu_count() or 4) // max(1, num_workers))
    for _env_var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[_env_var] = str(threads)
    # OpenMP's default idle-thread policy is to SPIN-WAIT (busy-poll) rather
    # than sleep, expecting to be the only OpenMP consumer on the host.
    # With N worker processes each running their own OpenMP thread pool,
    # idle threads from one worker spin-waiting steal real CPU time from
    # another worker's ACTIVE threads -- this is a well-documented cause of
    # catastrophic (not just proportional) multi-process slowdown, on top
    # of the raw thread-count oversubscription the NUM_THREADS vars above
    # address. PASSIVE makes idle threads yield instead.
    os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
    os.environ.setdefault("KMP_BLOCKTIME", "0")

    logging.basicConfig(
        level=os.getenv("SENTINEL_LOG_LEVEL", "INFO"),
        format=f"%(asctime)s %(levelname)-5s worker{worker_id} %(name)s: %(message)s",
    )
    log = logging.getLogger(f"sentinel.ai.worker.{worker_id}")
    log.info("starting, cameras=%s, threads_per_worker=%d", camera_ids, threads)

    try:
        import torch
        torch.set_num_threads(threads)
    except Exception:  # noqa: BLE001 -- best-effort; env vars above are the primary control
        pass
    try:
        import cv2
        cv2.setNumThreads(threads)
    except Exception:  # noqa: BLE001
        pass

    os.makedirs(evidence_dir, exist_ok=True)
    pipeline = pipeline_factory(backend_url=backend_url, evidence_dir=evidence_dir, device=device)
    if ingest_api_key:
        pipeline.ingest_api_key = ingest_api_key
    if no_backend:
        # dry run: swallow dispatch so we still exercise detection/OCR/tracking
        pipeline._dispatch_event = lambda payload: True

    # Local import so this only needs to succeed inside a real worker
    # process (and so a stub pipeline_factory in tests never needs it).
    from ai.adapter.ingestion_bridge import envelope_to_frame_input

    frames_processed = 0
    last_report = time.monotonic()

    while not stop_event.is_set():
        try:
            item = in_queue.get(timeout=0.5)
        except Exception:
            item = None
        if item is not None:
            camera_id, envelope = item
            try:
                frame_input = envelope_to_frame_input(envelope, camera_name=camera_id)
                pipeline.process_frame(frame_input)
                frames_processed += 1
            except Exception:  # noqa: BLE001 -- one bad frame must never kill the worker
                log.exception("frame processing failed for %s", camera_id)
        if time.monotonic() - last_report > stats_interval:
            _report_metrics(metrics_queue, worker_id, camera_ids, pipeline, frames_processed)
            last_report = time.monotonic()

    log.info("stop requested, draining...")
    try:
        pipeline.shutdown(drain_timeout=5.0)
    except Exception:  # noqa: BLE001
        log.exception("pipeline shutdown failed")
    _report_metrics(metrics_queue, worker_id, camera_ids, pipeline, frames_processed)
    log.info("stopped. frames_processed=%d", frames_processed)


@dataclass
class WorkerHandle:
    worker_id: int
    camera_ids: List[str]
    process: Any
    in_queue: Any
    stop_event: Any
    metrics_queue: Any
    latest_queue: PerCameraLatestQueue = field(default_factory=PerCameraLatestQueue)
    handoff_drops: int = 0


class AIWorkerPool:
    """Owns N worker processes, a router thread that drains the EXISTING
    ingestion frame_queue and fans frames out by (deterministic) camera
    shard, and N feeder threads that hand each worker its next, fairly-
    scheduled frame. Mirrors AIPipeline's own public surface just enough
    for scripts/run_pipeline_service.py and scripts/benchmark_pipeline.py
    to use either one with minimal branching (get_metrics(), shutdown()).
    """

    def __init__(
        self,
        frame_queue: "multiprocessing.queues.Queue | Any",
        camera_ids: List[str],
        num_workers: int,
        *,
        backend_url: str,
        ingest_api_key: Optional[str],
        evidence_dir: str,
        device: str,
        no_backend: bool,
        stats_interval: float = 5.0,
        pipeline_factory: Callable[..., Any] = _default_pipeline_factory,
    ) -> None:
        self.frame_queue = frame_queue
        self.num_workers = max(1, num_workers)
        self._stop = threading.Event()
        self._router_thread: Optional[threading.Thread] = None
        self._feeder_threads: List[threading.Thread] = []
        self.frames_routed = 0
        self.frames_handoff_dropped = 0
        self._latest_metrics: Dict[int, dict] = {}

        self._assignment: Dict[str, int] = {
            cid: camera_worker_index(cid, self.num_workers) for cid in camera_ids
        }
        by_worker: Dict[int, List[str]] = {}
        for cid, idx in self._assignment.items():
            by_worker.setdefault(idx, []).append(cid)

        ctx = multiprocessing.get_context("spawn")
        self.workers: List[WorkerHandle] = []
        for i in range(self.num_workers):
            cams = by_worker.get(i, [])
            in_q = ctx.Queue(maxsize=2)
            metrics_q = ctx.Queue(maxsize=8)
            stop_evt = ctx.Event()
            proc = ctx.Process(
                target=_ai_worker_main,
                args=(i, cams, in_q, metrics_q, stop_evt),
                kwargs=dict(
                    backend_url=backend_url,
                    ingest_api_key=ingest_api_key,
                    evidence_dir=os.path.join(evidence_dir, f"worker{i}"),
                    device=device,
                    no_backend=no_backend,
                    stats_interval=stats_interval,
                    pipeline_factory=pipeline_factory,
                    num_workers=self.num_workers,
                ),
                name=f"ai-worker-{i}",
                daemon=True,
            )
            self.workers.append(WorkerHandle(
                worker_id=i, camera_ids=cams, process=proc,
                in_queue=in_q, stop_event=stop_evt, metrics_queue=metrics_q,
            ))
            logger.info("worker %d assigned %d camera(s): %s", i, len(cams), cams)

    # -- lifecycle ---------------------------------------------------- #
    def start(self) -> None:
        for w in self.workers:
            w.process.start()
        self._router_thread = threading.Thread(target=self._route_loop, name="ai-router", daemon=True)
        self._router_thread.start()
        for w in self.workers:
            t = threading.Thread(target=self._feed_loop, args=(w,), name=f"ai-feeder-{w.worker_id}", daemon=True)
            t.start()
            self._feeder_threads.append(t)

    def shutdown(self, timeout: float = 15.0) -> None:
        self._stop.set()
        for w in self.workers:
            w.stop_event.set()
        if self._router_thread is not None:
            self._router_thread.join(timeout=2.0)
        for t in self._feeder_threads:
            t.join(timeout=2.0)
        for w in self.workers:
            w.process.join(timeout=timeout)
            if w.process.is_alive():
                logger.warning("worker %d did not exit within %.0fs, terminating", w.worker_id, timeout)
                w.process.terminate()
                w.process.join(timeout=5.0)
            # multiprocessing.Queue runs a background feeder thread in
            # THIS (parent) process; its atexit finalizer joins that
            # thread, which can hang the whole interpreter on exit if any
            # buffered item was never fully flushed (e.g. the child exited
            # first). We've already given up on delivering anything still
            # queued at this point, so tell it not to try.
            for q in (w.in_queue, w.metrics_queue):
                try:
                    q.close()
                    q.cancel_join_thread()
                except Exception:  # noqa: BLE001
                    pass

    # -- routing -------------------------------------------------------- #
    def _route_loop(self) -> None:
        while not self._stop.is_set():
            try:
                envelope = self.frame_queue.get(timeout=0.5)
            except Exception:
                continue
            try:
                camera_id = getattr(envelope, "camera_id", None)
                idx = self._assignment.get(camera_id)
                if idx is None:
                    # A camera not known at pool-construction time (e.g.
                    # onboarded afterward) still gets a deterministic,
                    # stable shard rather than having its frames dropped.
                    idx = camera_worker_index(camera_id, self.num_workers)
                    self._assignment[camera_id] = idx
                self.workers[idx].latest_queue.put(camera_id, envelope)
                self.frames_routed += 1
            finally:
                try:
                    self.frame_queue.task_done()
                except (ValueError, AttributeError):
                    pass

    def _feed_loop(self, w: WorkerHandle) -> None:
        while not self._stop.is_set():
            item = w.latest_queue.get(timeout=0.5)
            if item is None:
                continue
            try:
                # A BLOCKING (bounded) put, not put_nowait: this ties the
                # feeder's rate of draining latest_queue to the worker's
                # actual consumption rate. put_nowait here was a real bug
                # -- on any Full it looped straight back to another get(),
                # busy-draining latest_queue far faster than the worker
                # could ever consume, which defeated the round-robin
                # fairness entirely (one camera's frames would dominate
                # _order purely by timing luck, not by design). The bound
                # (not an unbounded blocking put) still guarantees this
                # thread can't wedge forever on a truly dead worker.
                w.in_queue.put(item, timeout=2.0)
            except Exception:  # queue.Full after the timeout -- worker stuck/dead
                w.handoff_drops += 1
                self.frames_handoff_dropped += 1

    # -- metrics -------------------------------------------------------- #
    def poll_metrics(self) -> Dict[int, dict]:
        """Drain whatever metrics snapshots workers have pushed since the
        last call (non-blocking); keeps the latest snapshot per worker."""
        for w in self.workers:
            while True:
                try:
                    m = w.metrics_queue.get_nowait()
                except Exception:
                    break
                self._latest_metrics[w.worker_id] = m
        return dict(self._latest_metrics)

    def get_metrics(self) -> dict:
        """Aggregated, pool-wide view -- shaped closely enough to
        AIPipeline.get_metrics() that callers can share most logic."""
        per_worker = self.poll_metrics()
        frames_by_camera: Dict[str, int] = {}
        events_by_camera: Dict[str, int] = {}
        totals = {
            "processed_frames": 0,
            "total_ai_events_generated": 0,
            "events_sent_ok": 0,
            "events_dropped_queue_full": 0,
            "events_dropped_backend_rejected": 0,
            "events_dropped_buffer_full": 0,
            "events_buffered_for_retry": 0,
            "event_queue_max_depth": 0,
        }
        resource = []
        latency_stages = ("yolo_latency_ms", "ocr_latency_ms", "send_latency_ms",
                          "compute_latency_ms", "end_to_end_latency_ms")
        per_worker_latency: Dict[int, dict] = {}
        for w in self.workers:
            snap = per_worker.get(w.worker_id) or {}
            metrics = snap.get("metrics") or {}
            for k in ("total_ai_events_generated", "events_sent_ok", "events_dropped_queue_full",
                      "events_dropped_backend_rejected", "events_dropped_buffer_full",
                      "events_buffered_for_retry"):
                totals[k] += metrics.get(k, 0) or 0
            totals["processed_frames"] += snap.get("frames_processed", 0) or 0
            totals["event_queue_max_depth"] = max(totals["event_queue_max_depth"], metrics.get("event_queue_max_depth", 0) or 0)
            frames_by_camera.update(metrics.get("frames_by_camera", {}) or {})
            events_by_camera.update(metrics.get("events_by_camera", {}) or {})
            if metrics.get("resource_usage"):
                resource.append({"worker_id": w.worker_id, **metrics["resource_usage"]})
            per_worker_latency[w.worker_id] = {stage: metrics.get(stage) for stage in latency_stages}

        # A combined view across workers: each worker only reports its own
        # summary stats (count/avg/p50/p95), not raw samples, so an EXACT
        # pooled percentile isn't computable here without shipping every
        # sample across the process boundary (not done -- that's real
        # per-frame overhead this pass deliberately avoids). avg_ms is
        # combined as a count-weighted mean (mathematically valid); p50/p95
        # instead report the largest-sample worker's own values, labeled
        # "representative" rather than passed off as an exact pooled figure.
        combined_latency: Dict[str, dict] = {}
        for stage in latency_stages:
            entries = [v[stage] for v in per_worker_latency.values() if v.get(stage) and v[stage].get("count")]
            if not entries:
                combined_latency[stage] = {"count": 0, "avg_ms": None, "p50_ms": None, "p95_ms": None,
                                            "note": "no samples"}
                continue
            total_count = sum(e["count"] for e in entries)
            weighted_avg = sum(e["count"] * e["avg_ms"] for e in entries) / total_count
            biggest = max(entries, key=lambda e: e["count"])
            combined_latency[stage] = {
                "count": total_count,
                "avg_ms": round(weighted_avg, 2),
                "p50_ms": biggest["p50_ms"],
                "p95_ms": biggest["p95_ms"],
                "note": "p50/p95 are the largest-sample worker's own values, not an exact pooled percentile",
            }

        stale_by_worker = {w.worker_id: w.latest_queue.stale_evicted_snapshot() for w in self.workers}
        depth_by_worker = {w.worker_id: w.latest_queue.depth() for w in self.workers}
        handoff_drops_by_worker = {w.worker_id: w.handoff_drops for w in self.workers}

        return {
            "num_workers": self.num_workers,
            "frames_routed": self.frames_routed,
            "frames_handoff_dropped": self.frames_handoff_dropped,
            "worker_assignment": {w.worker_id: w.camera_ids for w in self.workers},
            "per_worker_raw": per_worker,
            "per_worker_queue_depth": depth_by_worker,
            "per_worker_stale_evicted": stale_by_worker,
            "per_worker_handoff_drops": handoff_drops_by_worker,
            "per_worker_resource_usage": resource,
            "per_worker_latency": per_worker_latency,
            "combined_latency": combined_latency,
            "frames_by_camera": frames_by_camera,
            "events_by_camera": events_by_camera,
            **totals,
        }
