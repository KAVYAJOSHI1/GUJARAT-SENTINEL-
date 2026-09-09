"""
ai/scheduled_consumer.py

Phase 17 -- fair-scheduled, priority-aware, adaptively-sampled alternative
to ai.adapter.ingestion_bridge.FrameConsumer.

Same thread-count / CPU-parallelism profile as the default single-consumer
path -- ONE thread calls ``pipeline.process_frame()``, plus one lightweight
router thread that only does queue hand-off (no model work at all). This
does NOT add multiprocessing and does NOT change how many CPU cores are
used; it only changes the ORDER frames are pulled in: fair, bounded,
priority-weighted (``ai.scheduler.FairCameraScheduler``) instead of a
plain FIFO ``queue.Queue`` drain.

This is the fix for the FIFO-starvation finding in SCALABILITY.md Sec 3
(only ~5 of 30 cameras ever got a processed frame in a 45s run) for the
DEFAULT, recommended configuration (``SENTINEL_AI_WORKERS=1``).
``ai/worker_pool.py`` already fixed the identical bug for its
multi-process pool path (Sec 4) -- but that path is currently NOT
recommended on constrained hardware (measured net throughput loss from
CPU oversubscription). This module gets the same fairness property
WITHOUT adding a second process and WITHOUT the CPU-oversubscription risk,
because it changes scheduling order only, not parallelism.

Pipeline:

    frame_queue (existing ingestion StreamManager output, unmodified)
          |  _route_loop(): drains frame_queue, applies AdaptiveFrameSampler
          |  gating (never blocks; a rejected frame is counted with an
          |  explicit DropReason), hands accepted frames to the scheduler
          v
    FairCameraScheduler (bounded, priority-weighted, fair)
          |  _work_loop(): pulls the next fairly-scheduled frame, calls
          |  pipeline.process_frame(..., mode=...) -- exactly one thread,
          |  same as ai.adapter.ingestion_bridge.FrameConsumer
          v
    AIPipeline.process_frame()

Opt-in: existing callers keep using FrameConsumer unchanged. Wired into
scripts/run_pipeline_service.py behind ``--fair-scheduler`` /
``SENTINEL_FAIR_SCHEDULER=1`` (single-consumer path only, i.e.
``--ai-workers`` still 1) so the two scheduling strategies can be
benchmarked head-to-head under identical load.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from ai.adapter.ingestion_bridge import envelope_to_frame_input
from ai.degradation import DegradationInputs, DegradationReport, SystemLoadMonitor
from ai.modes import ModeRegistry
from ai.sampling import AdaptiveFrameSampler
from ai.scheduler import DropReason, FairCameraScheduler

logger = logging.getLogger("sentinel.ai.scheduled_consumer")


class ScheduledFrameConsumer:
    def __init__(
        self,
        frame_queue: "queue.Queue",
        pipeline: Any,
        *,
        on_events: Optional[Callable[[str, List[Dict[str, Any]]], None]] = None,
        camera_names: Optional[Dict[str, str]] = None,
        stop_event: Optional[threading.Event] = None,
        poll_timeout_s: float = 1.0,
        scheduler: Optional[FairCameraScheduler] = None,
        sampler: Optional[AdaptiveFrameSampler] = None,
        mode_registry: Optional[ModeRegistry] = None,
        load_monitor: Optional[SystemLoadMonitor] = None,
        load_update_interval_s: float = 2.0,
    ) -> None:
        self._q = frame_queue
        self._pipeline = pipeline
        self._on_events = on_events
        self._camera_names = camera_names or {}
        self._stop_event = stop_event or threading.Event()
        self._poll_timeout_s = poll_timeout_s

        self.scheduler = scheduler if scheduler is not None else FairCameraScheduler()
        self.sampler = sampler if sampler is not None else AdaptiveFrameSampler()
        self.modes = mode_registry if mode_registry is not None else ModeRegistry()
        self.load_monitor = load_monitor if load_monitor is not None else SystemLoadMonitor()
        self._load_update_interval_s = load_update_interval_s

        self._last_seq: Dict[str, int] = {}
        self._priority_seeded: set = set()
        self.frames_processed = 0
        self.frames_skipped = 0
        self.events_emitted = 0
        self._current_load_state = "HEALTHY"
        self._last_degradation: Optional[DegradationReport] = None
        self._last_load_update_mono = 0.0

        self._router_thread = threading.Thread(target=self._route_loop, name="ai-scheduled-router", daemon=True)
        self._worker_thread = threading.Thread(target=self._work_loop, name="ai-scheduled-worker", daemon=True)

    # -- lifecycle -------------------------------------------------------- #
    def start(self) -> None:
        self._router_thread.start()
        self._worker_thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def join(self, timeout: Optional[float] = None) -> None:
        self._router_thread.join(timeout=timeout)
        self._worker_thread.join(timeout=timeout)

    # -- configuration helpers (registry-driven, all optional) ------------ #
    def configure_camera(
        self, camera_id: str, *, priority: Optional[str] = None,
        mode: Optional[str] = None, sampling=None,
    ) -> None:
        """One place a caller (scripts/run_pipeline_service.py, reading a
        camera registry's optional ``priority``/``processing_mode`` fields)
        can set up a camera before frames start arriving for it."""
        if mode is not None:
            self.modes.set_mode(camera_id, mode)
        if priority is not None:
            self.scheduler.set_priority(camera_id, priority)
            self._priority_seeded.add(camera_id)
        if sampling is not None:
            self.sampler.configure(camera_id, sampling)
        self.sampler.set_priority(camera_id, self.scheduler.get_priority(camera_id))

    # -- discontinuity handling (identical to FrameConsumer) -------------- #
    def _check_reconnect(self, camera_id: str, seq_num: Optional[int]) -> None:
        if seq_num is None:
            return
        last = self._last_seq.get(camera_id)
        if last is not None and seq_num <= last:
            logger.info(
                "Camera %s: seq_num %s <= %s -> stream discontinuity, resetting tracker",
                camera_id, seq_num, last,
            )
            reset = getattr(self._pipeline, "reset_camera", None)
            if callable(reset):
                try:
                    reset(camera_id)
                except Exception:  # noqa: BLE001
                    logger.exception("reset_camera(%s) failed", camera_id)
        self._last_seq[camera_id] = seq_num

    # -- router: frame_queue -> AdaptiveFrameSampler -> FairCameraScheduler #
    def _route_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                envelope = self._q.get(timeout=self._poll_timeout_s)
            except queue.Empty:
                continue
            try:
                camera_id = getattr(envelope, "camera_id", "CAM-UNKNOWN")
                if camera_id not in self._priority_seeded:
                    default_priority = self.modes.get_flags(camera_id).default_priority
                    self.scheduler.set_priority(camera_id, default_priority)
                    self.sampler.set_priority(camera_id, default_priority)
                    self._priority_seeded.add(camera_id)

                decision = self.sampler.should_process(camera_id, load_state=self._current_load_state)
                if not decision.accept:
                    self.frames_skipped += 1
                    self.scheduler.record_drop(camera_id, decision.reason or DropReason.RATE_LIMIT)
                    continue

                self.scheduler.put(camera_id, envelope)
            finally:
                try:
                    self._q.task_done()
                except (ValueError, AttributeError):
                    pass

    # -- worker: FairCameraScheduler -> AIPipeline.process_frame() -------- #
    def _work_loop(self) -> None:
        while not self._stop_event.is_set():
            got = self.scheduler.get(timeout=self._poll_timeout_s)
            self._maybe_update_load_state()
            if got is None:
                continue
            camera_id, envelope = got
            try:
                self._check_reconnect(camera_id, getattr(envelope, "seq_num", None))
                frame_input = envelope_to_frame_input(envelope, camera_name=self._camera_names.get(camera_id))
                mode = self.modes.get_mode(camera_id)
                events = self._pipeline.process_frame(frame_input, mode=mode) or []
                self.frames_processed += 1
                if events:
                    self.events_emitted += len(events)
                    if self._on_events is not None:
                        try:
                            self._on_events(camera_id, events)
                        except Exception:  # noqa: BLE001
                            logger.exception("on_events callback failed for %s", camera_id)
            except Exception:  # noqa: BLE001 -- one bad frame must not kill the worker
                logger.exception("Frame processing failed for %s", camera_id)
        logger.info(
            "ScheduledFrameConsumer stopped (frames=%d skipped=%d events=%d)",
            self.frames_processed, self.frames_skipped, self.events_emitted,
        )

    # -- degradation state (Phase 17 Step 7) ------------------------------ #
    def _maybe_update_load_state(self) -> None:
        now = time.monotonic()
        if now - self._last_load_update_mono < self._load_update_interval_s:
            return
        self._last_load_update_mono = now
        try:
            metrics = self._pipeline.get_metrics()
        except Exception:  # noqa: BLE001
            return
        snap = self.scheduler.snapshot()
        ocr = metrics.get("ocr_executor") or {}
        raw_cpu = (metrics.get("resource_usage") or {}).get("cpu_percent")
        # AIPipeline.get_resource_usage() reports psutil's raw, MULTI-CORE
        # cumulative percent (up to ncores*100 -- e.g. "652% avg" in
        # AI_ARCHITECTURE.md/SCALABILITY.md's own convention). That's the
        # right number for a human-readable dashboard metric, but
        # ai.degradation's thresholds (70%/90%) are written for a
        # NORMALIZED 0-100%-of-total-capacity scale -- comparing the raw
        # value directly would falsely trip OVERLOADED any time this
        # process alone used more than ~1 core, i.e. almost immediately
        # during any real inference (measured: this exact bug produced a
        # permanent, spurious OVERLOADED state and a near-total sampling
        # collapse in an early Phase 17 benchmark run -- see
        # docs/PHASE17_BENCHMARK.md's limitations section).
        cpu_cores = os.cpu_count() or 1
        normalized_cpu = (raw_cpu / cpu_cores) if raw_cpu is not None else None
        inputs = DegradationInputs(
            cpu_percent=normalized_cpu,
            event_queue_depth=metrics.get("event_queue_depth"),
            event_queue_maxsize=metrics.get("event_queue_maxsize"),
            ocr_queue_depth=ocr.get("queue_depth"),
            ocr_queue_maxsize=ocr.get("queue_maxsize"),
            starvation_events=snap["totals"]["starvation_events"],
            frames_processed=snap["totals"]["frames_processed"],
        )
        report = self.load_monitor.evaluate(inputs)
        if report.state != self._current_load_state:
            logger.info("system load state -> %s (%s)", report.state, "; ".join(report.reasons) or "recovered")
        self._current_load_state = report.state
        self._last_degradation = report

    # -- metrics (Step 2 + Step 7) ----------------------------------------- #
    def get_metrics(self) -> Dict[str, Any]:
        return {
            "frames_processed": self.frames_processed,
            "frames_skipped": self.frames_skipped,
            "events_emitted": self.events_emitted,
            "scheduler": self.scheduler.snapshot(),
            "modes": self.modes.snapshot(),
            "load_state": self._current_load_state,
            "degradation": self._last_degradation.to_dict() if self._last_degradation else None,
        }
