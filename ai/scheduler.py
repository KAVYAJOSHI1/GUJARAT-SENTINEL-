"""
ai/scheduler.py

Phase 17 -- bounded, fair, priority-aware camera frame scheduler.

Context (see AI_ARCHITECTURE.md / SCALABILITY.md Sec 3-4 for the full,
previously-measured history): a plain FIFO ``queue.Queue`` drained by one
consumer starves most cameras once camera count exceeds what one CPU-bound
consumer can service -- measured at only ~5 of 30 cameras ever getting a
processed frame in a 45s run. ``ai/worker_pool.py`` already fixed this for
its (opt-in, currently NOT recommended -- see SCALABILITY.md Sec 4)
multi-process pool via ``PerCameraLatestQueue``: bounded one-pending-frame-
per-camera memory + strict round-robin service.

This module is a superset of that same idea, used by the DEFAULT
single-consumer path (``ai/scheduled_consumer.py``) as well as anywhere
else that wants it:

  1. Bounded per-camera queues (depth configurable, default 1 = the same
     "latest frame wins" behavior as ``PerCameraLatestQueue`` -- a newer
     frame overwrites a not-yet-consumed one, counted as a stale eviction,
     never silently dropped).
  2. FOUR priority classes (CRITICAL/HIGH/NORMAL/BACKGROUND) served via a
     smooth weighted round-robin (the same well-known algorithm nginx uses
     for weighted upstream selection): with every camera at the default
     priority (NORMAL), weights are equal and this degenerates to EXACTLY
     plain round-robin service in arrival order -- i.e. this is backward
     compatible with the existing fairness guarantee, not a behavior change,
     when nothing sets a non-default priority.
  3. Every drop is COUNTED with an explicit, named reason (``DropReason``)
     -- never a silent frame loss.
  4. Per-camera stats: frames received/processed/dropped(by reason),
     current processing FPS (rolling window), target FPS, priority,
     starvation count, last-processed timestamp -- everything Step 2 of the
     Phase 17 brief asks the scheduler to expose.

Nothing here touches ``ai/worker_pool.py`` or ``PerCameraLatestQueue`` --
that module and its existing, passing test suite
(``tests/test_worker_pool.py``) are completely unaffected; this is an
additive module.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Condition, Lock
from typing import Any, Deque, Dict, List, Optional, Tuple


class CameraPriority:
    """Plain string constants (not enum.Enum) so values serialize directly
    into JSON API/metrics payloads without a `.value` unwrap -- matches this
    codebase's existing convention (see ai/anpr/quality.py::FailureReason)."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    BACKGROUND = "BACKGROUND"

    ALL = (CRITICAL, HIGH, NORMAL, BACKGROUND)


class DropReason:
    QUEUE_FULL = "QUEUE_FULL"
    RATE_LIMIT = "RATE_LIMIT"
    OVERLOAD = "OVERLOAD"
    DUPLICATE = "DUPLICATE"
    CAMERA_PAUSED = "CAMERA_PAUSED"

    ALL = (QUEUE_FULL, RATE_LIMIT, OVERLOAD, DUPLICATE, CAMERA_PAUSED)


# Higher weight => proportionally more turns in the smooth weighted
# round-robin. These are a starting, documented default -- callers can pass
# their own via FairCameraScheduler(priority_weights=...).
DEFAULT_PRIORITY_WEIGHTS: Dict[str, int] = {
    CameraPriority.CRITICAL: 8,
    CameraPriority.HIGH: 4,
    CameraPriority.NORMAL: 2,
    CameraPriority.BACKGROUND: 1,
}

# A camera with a pending frame that hasn't been served in this long counts
# as one "starvation" event (then the clock resets, so a genuinely wedged
# camera racks up multiple events over a long run rather than one that
# never increments again).
DEFAULT_STARVATION_THRESHOLD_S = 5.0


@dataclass
class CameraSchedulerStats:
    camera_id: str
    priority: str = CameraPriority.NORMAL
    frames_received: int = 0
    frames_processed: int = 0
    frames_dropped: Dict[str, int] = field(default_factory=dict)
    target_fps: Optional[float] = None
    starvation_count: int = 0
    last_processed_mono: Optional[float] = None
    last_received_mono: Optional[float] = None
    pending_since_mono: Optional[float] = None
    _recent_processed: Deque[float] = field(default_factory=lambda: deque(maxlen=64), repr=False)

    def record_received(self) -> None:
        self.frames_received += 1
        self.last_received_mono = time.monotonic()

    def record_processed(self) -> None:
        now = time.monotonic()
        self.frames_processed += 1
        self.last_processed_mono = now
        self.pending_since_mono = None
        self._recent_processed.append(now)

    def record_dropped(self, reason: str) -> None:
        self.frames_dropped[reason] = self.frames_dropped.get(reason, 0) + 1

    def total_dropped(self) -> int:
        return sum(self.frames_dropped.values())

    def current_fps(self, window_s: float = 10.0) -> Optional[float]:
        """Rolling processed-FPS over the last ``window_s`` seconds of
        actual processed timestamps -- None (never 0) when there are not
        yet enough samples to say anything meaningful."""
        if len(self._recent_processed) < 2:
            return None
        now = time.monotonic()
        recent = [t for t in self._recent_processed if now - t <= window_s]
        if len(recent) < 2:
            return None
        span = recent[-1] - recent[0]
        return round((len(recent) - 1) / span, 2) if span > 0 else None

    def snapshot(self, *, queue_depth: int = 0) -> Dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "priority": self.priority,
            "frames_received": self.frames_received,
            "frames_processed": self.frames_processed,
            "frames_dropped": dict(self.frames_dropped),
            "frames_dropped_total": self.total_dropped(),
            "current_fps": self.current_fps(),
            "target_fps": self.target_fps,
            "queue_depth": queue_depth,
            "starvation_count": self.starvation_count,
            "last_processed_ts": self.last_processed_mono,
            "last_received_ts": self.last_received_mono,
        }


class FairCameraScheduler:
    """Bounded, priority-weighted, fair-scheduled camera->frame hand-off.

    API-compatible in spirit with ``ai.worker_pool.PerCameraLatestQueue``
    (``put`` / ``get`` / ``depth``) -- with every camera left at the default
    NORMAL priority and ``max_queue_depth=1`` (both defaults), behavior is
    exactly that module's "latest frame wins, strict round robin" semantics.
    """

    def __init__(
        self,
        max_queue_depth: int = 1,
        priority_weights: Optional[Dict[str, int]] = None,
        starvation_threshold_s: float = DEFAULT_STARVATION_THRESHOLD_S,
    ) -> None:
        self._lock = Lock()
        self._not_empty = Condition(self._lock)
        self._max_queue_depth = max(1, int(max_queue_depth))
        self._weights = dict(priority_weights or DEFAULT_PRIORITY_WEIGHTS)
        self._starvation_threshold_s = starvation_threshold_s

        self._buckets: Dict[str, Deque[str]] = {p: deque() for p in CameraPriority.ALL}
        self._pending_items: Dict[str, Deque[Any]] = {}
        self._camera_priority: Dict[str, str] = {}
        self._stale_evicted: Dict[str, int] = {}
        self._current_weight: Dict[str, float] = {p: 0.0 for p in CameraPriority.ALL}
        self._stats: Dict[str, CameraSchedulerStats] = {}

    # -- per-camera config --------------------------------------------- #
    def _get_stats(self, camera_id: str) -> CameraSchedulerStats:
        st = self._stats.get(camera_id)
        if st is None:
            st = CameraSchedulerStats(camera_id=camera_id)
            self._stats[camera_id] = st
        return st

    def set_priority(self, camera_id: str, priority: str) -> None:
        if priority not in CameraPriority.ALL:
            raise ValueError(f"unknown priority {priority!r}")
        with self._lock:
            self._camera_priority[camera_id] = priority
            self._get_stats(camera_id).priority = priority

    def get_priority(self, camera_id: str) -> str:
        with self._lock:
            return self._camera_priority.get(camera_id, CameraPriority.NORMAL)

    def set_target_fps(self, camera_id: str, fps: Optional[float]) -> None:
        with self._lock:
            self._get_stats(camera_id).target_fps = fps

    # -- put / get ------------------------------------------------------ #
    def put(self, camera_id: str, item: Any, priority: Optional[str] = None) -> None:
        """Hand off one frame for ``camera_id``. Never blocks, never raises
        on a full per-camera slot -- at ``max_queue_depth=1`` (default) the
        pending frame is overwritten (stale-evicted, counted); at a higher
        configured depth the OLDEST pending frame is dropped instead
        (counted as ``DropReason.QUEUE_FULL``) once the bound is reached."""
        with self._not_empty:
            st = self._get_stats(camera_id)
            st.record_received()
            if priority is not None:
                if priority not in CameraPriority.ALL:
                    raise ValueError(f"unknown priority {priority!r}")
                self._camera_priority[camera_id] = priority
                st.priority = priority
            prio = self._camera_priority.get(camera_id, CameraPriority.NORMAL)

            dq = self._pending_items.get(camera_id)
            if dq is None:
                dq = deque()
                self._pending_items[camera_id] = dq
            was_empty = len(dq) == 0

            if self._max_queue_depth <= 1:
                if dq:
                    self._stale_evicted[camera_id] = self._stale_evicted.get(camera_id, 0) + 1
                    dq.clear()
                dq.append(item)
            else:
                if len(dq) >= self._max_queue_depth:
                    dq.popleft()
                    st.record_dropped(DropReason.QUEUE_FULL)
                dq.append(item)

            if was_empty:
                st.pending_since_mono = time.monotonic()
                self._buckets[prio].append(camera_id)
            self._not_empty.notify()

    def _select_bucket(self) -> Optional[str]:
        """Smooth weighted round-robin over non-empty priority buckets
        (the same algorithm nginx uses for weighted upstream selection).
        With all buckets but one empty (the common case: every camera at
        the same priority), this always returns that one bucket -- plain
        FIFO-per-bucket, i.e. unchanged round-robin behavior."""
        nonempty = [p for p in CameraPriority.ALL if self._buckets[p]]
        if not nonempty:
            return None
        total = sum(self._weights.get(p, 1) for p in nonempty)
        best, best_w = None, None
        for p in nonempty:
            self._current_weight[p] = self._current_weight.get(p, 0.0) + self._weights.get(p, 1)
            if best is None or self._current_weight[p] > best_w:
                best, best_w = p, self._current_weight[p]
        self._current_weight[best] -= total
        return best

    def _mark_starved_if_needed(self, now: float) -> None:
        for cam_id, dq in self._pending_items.items():
            if not dq:
                continue
            st = self._stats.get(cam_id)
            if st is None or st.pending_since_mono is None:
                continue
            if now - st.pending_since_mono >= self._starvation_threshold_s:
                st.starvation_count += 1
                st.pending_since_mono = now  # restart the window

    def get(self, timeout: float = 0.5) -> Optional[Tuple[str, Any]]:
        """Blocks up to ``timeout`` seconds for the next fairly-scheduled
        (camera_id, item) pair; returns None on timeout (mirrors
        ``PerCameraLatestQueue.get``)."""
        deadline = time.monotonic() + max(0.0, timeout)
        with self._not_empty:
            while True:
                bucket = self._select_bucket()
                if bucket is not None:
                    camera_id = self._buckets[bucket].popleft()
                    dq = self._pending_items.get(camera_id)
                    item = dq.popleft() if dq else None
                    if dq:
                        # depth > 1 and more items already queued -- keep this
                        # camera in rotation instead of waiting for a new put().
                        self._buckets[bucket].append(camera_id)
                        self._get_stats(camera_id).pending_since_mono = time.monotonic()
                    st = self._get_stats(camera_id)
                    st.record_processed()
                    self._mark_starved_if_needed(time.monotonic())
                    return camera_id, item
                self._mark_starved_if_needed(time.monotonic())
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._not_empty.wait(timeout=min(remaining, 0.5))

    # -- introspection ---------------------------------------------------- #
    def depth(self) -> int:
        """Number of distinct cameras with a currently-pending frame."""
        with self._lock:
            return sum(1 for dq in self._pending_items.values() if dq)

    def stale_evicted_snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._stale_evicted)

    def record_drop(self, camera_id: str, reason: str) -> None:
        """For callers gating BEFORE put() (e.g. adaptive sampling rejecting
        a frame outright) -- still counted against this camera's stats."""
        with self._lock:
            self._get_stats(camera_id).record_dropped(reason)

    def snapshot(self) -> Dict[str, Any]:
        """Full scheduler-wide stats snapshot -- Step 2 of the Phase 17
        brief: active cameras, queued cameras, per-camera queue depth,
        frames received/processed/dropped, current/target FPS, priority,
        starvation count, last-processed timestamp."""
        with self._lock:
            per_camera = {}
            for cam_id, st in self._stats.items():
                snap = st.snapshot(queue_depth=len(self._pending_items.get(cam_id, ())))
                snap["stale_evicted"] = self._stale_evicted.get(cam_id, 0)
                per_camera[cam_id] = snap
            queued = [c for c, dq in self._pending_items.items() if dq]
            by_priority = {p: len(self._buckets[p]) for p in CameraPriority.ALL}
            return {
                "active_cameras": len(self._stats),
                "queued_cameras": len(queued),
                "queued_camera_ids": queued,
                "queued_by_priority": by_priority,
                "priority_weights": dict(self._weights),
                "max_queue_depth": self._max_queue_depth,
                "starvation_threshold_s": self._starvation_threshold_s,
                "cameras": per_camera,
                "totals": {
                    "frames_received": sum(s.frames_received for s in self._stats.values()),
                    "frames_processed": sum(s.frames_processed for s in self._stats.values()),
                    "stale_evicted": sum(self._stale_evicted.values()),
                    "frames_dropped": sum(s.total_dropped() for s in self._stats.values()),
                    "starvation_events": sum(s.starvation_count for s in self._stats.values()),
                },
            }
