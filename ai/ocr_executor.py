"""
ai/ocr_executor.py

Phase 17 Step 4 -- bounded, asynchronous OCR execution.

Principle: "ANPR/OCR must not block the entire camera processing
pipeline." Today, OCR runs synchronously inline inside
``AIPipeline.process_frame`` -- measured at ~169ms avg / much higher p95
(see AI_ARCHITECTURE.md / SCALABILITY.md), against a ~45ms YOLO call. When
a single consumer thread (or a single ai.worker_pool worker) owns several
cameras, that ~170ms is spent NOT looking at any other camera's frame.

``OCRExecutor`` moves the actual OCR call (a pure function: crop in, text+
confidence out -- no pipeline state touched) onto its own bounded-queue
background thread(s), so the calling thread can keep detecting/tracking on
the NEXT frame (possibly a different camera) while OCR for a previous crop
finishes. Consensus/track-state mutation from the OCR *result* still
happens on the pipeline's own single owning thread (via
``AIPipeline._drain_ocr_results``, called at the top of every
``process_frame``) -- exactly the same "single writer, no locks needed"
invariant the rest of this pipeline already relies on.

Bounded, honest backpressure: a full job queue means OCR genuinely can't
keep up with the submission rate. The job is DROPPED and counted
(``DropReason.QUEUE_FULL``) -- never queued unboundedly, never silently
lost. This is opt-in (``AIPipeline(..., async_ocr=True)`` /
``SENTINEL_ASYNC_OCR=1``); the default (off) leaves OCR exactly where it
always was, byte-for-byte.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from ai.scheduler import DropReason

logger = logging.getLogger("sentinel.ai.ocr_executor")


@dataclass
class OCRJob:
    """Everything the OCR call itself needs -- no pipeline state, so the
    worker thread never touches consensus/tracker/evidence bookkeeping."""

    camera_id: str
    track_id: Any
    track_key: str
    plate_crop: Any
    submitted_mono: float = field(default_factory=time.monotonic)
    context: Dict[str, Any] = field(default_factory=dict)  # opaque, carried through to the result


@dataclass
class OCRResult:
    job: OCRJob
    raw_text: str
    confidence: float
    enhanced_plate: Any
    variant_index: int = 0
    error: Optional[str] = None
    completed_mono: float = field(default_factory=time.monotonic)

    @property
    def latency_ms(self) -> float:
        return (self.completed_mono - self.job.submitted_mono) * 1000.0


class OCRExecutor:
    """Bounded background OCR execution. ``ocr_fn`` is a pure callable
    ``(plate_crop) -> {"raw_text": str, "confidence": float}`` (matches
    ``OCREngine.extract_text``'s existing return shape) -- this class does
    not know or care about EasyOCR/PaddleOCR specifics.
    """

    def __init__(
        self,
        ocr_fn: Callable[[Any], Dict[str, Any]],
        *,
        max_queue: int = 16,
        num_threads: int = 1,
    ) -> None:
        self._ocr_fn = ocr_fn
        self._jobs: "queue.Queue[OCRJob]" = queue.Queue(maxsize=max(1, max_queue))
        self._results: "queue.Queue[OCRResult]" = queue.Queue()
        self._stop = threading.Event()
        self._threads = [
            threading.Thread(target=self._worker_loop, name=f"ocr-executor-{i}", daemon=True)
            for i in range(max(1, num_threads))
        ]
        self.submitted = 0
        self.completed = 0
        self.dropped_queue_full = 0
        self.errors = 0
        self._lock = threading.Lock()
        for t in self._threads:
            t.start()

    def submit(self, job: OCRJob) -> bool:
        """Non-blocking. Returns False (and counts the drop) if the bounded
        job queue is already full -- the caller must treat this exactly
        like a skipped-OCR frame (continue detection/tracking, never
        block)."""
        try:
            self._jobs.put_nowait(job)
            with self._lock:
                self.submitted += 1
            return True
        except queue.Full:
            with self._lock:
                self.dropped_queue_full += 1
            return False

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                res = self._ocr_fn(job.plate_crop)
                result = OCRResult(
                    job=job,
                    raw_text=res.get("raw_text", "UNKNOWN"),
                    confidence=float(res.get("confidence", 0.0)),
                    enhanced_plate=res.get("enhanced_plate", job.plate_crop),
                    variant_index=int(res.get("variant", 0)),
                )
                with self._lock:
                    self.completed += 1
            except Exception as exc:  # noqa: BLE001 -- one bad crop must never kill the thread
                logger.exception("OCR job failed for %s", job.track_key)
                with self._lock:
                    self.errors += 1
                result = OCRResult(
                    job=job, raw_text="UNKNOWN", confidence=0.0,
                    enhanced_plate=job.plate_crop, error=str(exc),
                )
            finally:
                try:
                    self._jobs.task_done()
                except (ValueError, AttributeError):
                    pass
            self._results.put(result)

    def poll_results(self) -> list:
        """Non-blocking drain of every OCR result completed since the last
        call. Called from the pipeline's OWN thread -- results are applied
        (consensus mutation, event emission) there, never on this executor's
        worker thread(s)."""
        out = []
        while True:
            try:
                out.append(self._results.get_nowait())
            except queue.Empty:
                break
        return out

    def queue_depth(self) -> int:
        return self._jobs.qsize()

    def metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "queue_depth": self.queue_depth(),
                "queue_maxsize": self._jobs.maxsize,
                "submitted": self.submitted,
                "completed": self.completed,
                "dropped_queue_full": self.dropped_queue_full,
                "dropped_reason": DropReason.QUEUE_FULL if self.dropped_queue_full else None,
                "errors": self.errors,
                "num_threads": len(self._threads),
            }

    def shutdown(self, timeout: float = 5.0) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=timeout)
