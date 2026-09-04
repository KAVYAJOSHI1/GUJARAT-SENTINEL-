"""
ai/adapter/ingestion_bridge.py

The real bridge between Rishit's stream ingestion (``ingestion/``) and Kavya's
AI pipeline (``ai/pipeline.py``).

``ingestion.stream_manager.StreamManager`` runs one ``StreamWorker`` thread per
camera and pushes a :class:`ingestion.models.FrameEnvelope` onto a shared
``queue.Queue`` for every successfully decoded frame. Nothing consumed that
queue -- this module does.

  FrameEnvelope(camera_id, frame, pts_ms, seq_num, received_at_s)
        │  envelope_to_frame_input()
        ▼
  FrameInput(frame, camera_id, pts, timestamp, metadata={seq_num, pts_ms, ...})
        │  AIPipeline.process_frame()
        ▼
  [ AI detection events ]  ── on_events callback ──▶  correlation / backend

This is NOT a second ingestion architecture: there is no video capture here,
no reconnect logic, no catalogue. It only *consumes* what ``StreamManager``
already produces. ``ai/adapter/rtsp_adapter.py`` stays as the standalone
single-source helper for local file / webcam testing; for the real
multi-camera path use ``StreamManager`` + this consumer.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from ai.adapter.frame_interface import FrameInput

logger = logging.getLogger("sentinel.ai.ingestion_bridge")


def envelope_to_frame_input(
    envelope: Any,
    *,
    now_wall: Optional[float] = None,
    now_mono: Optional[float] = None,
    camera_name: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> FrameInput:
    """Convert one ``FrameEnvelope`` to the AI pipeline's ``FrameInput``.

    Field mapping (nothing is invented, nothing is dropped):

      ==================  ==================================================
      FrameEnvelope       FrameInput
      ==================  ==================================================
      camera_id           camera_id
      frame               frame
      pts_ms              pts  (also metadata["pts_ms"] -- authoritative timing)
      seq_num             metadata["seq_num"]  (per-connection gap detection)
      received_at_s        metadata["received_at_s"]  (monotonic bookkeeping)
      (derived)           timestamp  -- wall-clock ISO-8601 of frame capture
      ==================  ==================================================

    The event timestamp is reconstructed from ``received_at_s`` (a
    ``time.monotonic()`` reading) relative to the current wall clock, which is
    the most accurate wall time available for when the frame was actually read
    off the capture. If ``received_at_s`` looks unusable we fall back to "now".
    """
    now_wall = time.time() if now_wall is None else now_wall
    now_mono = time.monotonic() if now_mono is None else now_mono

    received_at_s = getattr(envelope, "received_at_s", None)
    if isinstance(received_at_s, (int, float)) and received_at_s > 0:
        age_s = max(0.0, now_mono - float(received_at_s))
        wall_of_frame = now_wall - age_s
    else:
        wall_of_frame = now_wall
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(wall_of_frame))

    frame = getattr(envelope, "frame", None)
    resolution = None
    try:
        if frame is not None and hasattr(frame, "shape") and len(frame.shape) >= 2:
            h, w = frame.shape[:2]
            resolution = f"{w}x{h}"
    except Exception:  # noqa: BLE001
        resolution = None

    metadata: Dict[str, Any] = {
        "seq_num": getattr(envelope, "seq_num", None),
        "pts_ms": getattr(envelope, "pts_ms", None),
        "received_at_s": received_at_s,
        "resolution": resolution,
        "source": "ingestion.stream_manager",
    }
    if camera_name:
        metadata["camera_name"] = camera_name
    if extra_metadata:
        metadata.update(extra_metadata)

    return FrameInput(
        frame=frame,
        camera_id=getattr(envelope, "camera_id", "CAM-UNKNOWN"),
        pts=getattr(envelope, "pts_ms", None),
        timestamp=timestamp,
        metadata=metadata,
    )


class FrameConsumer(threading.Thread):
    """Drains a ``StreamManager`` frame queue and runs each frame through the AI pipeline.

    One consumer thread is enough for the PoC (the AI pipeline is the
    bottleneck, not the queue). Scale out by running several instances against
    the same queue.

    :param frame_queue:  the ``StreamManager.frame_queue``
    :param pipeline:     an ``ai.pipeline.AIPipeline`` (or anything with a
                         compatible ``process_frame`` / ``reset_camera``)
    :param on_events:    optional callback ``(camera_id, [event, ...]) -> None``
                         invoked for every non-empty AI result (backend POST,
                         cross-camera correlation, ...)
    :param camera_names: optional ``{camera_id: human name}`` map, forwarded
                         into ``FrameInput.metadata["camera_name"]``
    :param stop_event:   shared shutdown flag
    """

    def __init__(
        self,
        frame_queue: "queue.Queue",
        pipeline: Any,
        *,
        on_events: Optional[Callable[[str, List[Dict[str, Any]]], None]] = None,
        camera_names: Optional[Dict[str, str]] = None,
        stop_event: Optional[threading.Event] = None,
        poll_timeout_s: float = 1.0,
    ) -> None:
        super().__init__(name="ai-frame-consumer", daemon=True)
        self._q = frame_queue
        self._pipeline = pipeline
        self._on_events = on_events
        self._camera_names = camera_names or {}
        self._stop_event = stop_event or threading.Event()
        self._poll_timeout_s = poll_timeout_s
        self._last_seq: Dict[str, int] = {}
        self.frames_processed = 0
        self.events_emitted = 0

    def stop(self) -> None:
        self._stop_event.set()

    # -- discontinuity handling ----------------------------------------- #
    def _check_reconnect(self, camera_id: str, seq_num: Optional[int]) -> None:
        """StreamWorker resets seq_num to 0/1 on every reconnect. A seq_num that
        did not advance monotonically => new connection => reset that camera's
        tracker so a post-gap vehicle is not glued onto a pre-gap track."""
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

    # -- main loop ---------------------------------------------------- #
    def run(self) -> None:
        logger.info("AI FrameConsumer started")
        while not self._stop_event.is_set():
            try:
                envelope = self._q.get(timeout=self._poll_timeout_s)
            except queue.Empty:
                continue
            try:
                camera_id = getattr(envelope, "camera_id", "CAM-UNKNOWN")
                self._check_reconnect(camera_id, getattr(envelope, "seq_num", None))
                frame_input = envelope_to_frame_input(
                    envelope, camera_name=self._camera_names.get(camera_id)
                )
                events = self._pipeline.process_frame(frame_input) or []
                self.frames_processed += 1
                if events:
                    self.events_emitted += len(events)
                    if self._on_events is not None:
                        try:
                            self._on_events(camera_id, events)
                        except Exception:  # noqa: BLE001
                            logger.exception("on_events callback failed for %s", camera_id)
            except Exception:  # noqa: BLE001 -- one bad frame must not kill the consumer
                logger.exception("Frame processing failed")
            finally:
                try:
                    self._q.task_done()
                except (ValueError, AttributeError):
                    pass
        logger.info(
            "AI FrameConsumer stopped (frames=%d events=%d)",
            self.frames_processed, self.events_emitted,
        )


def process_queue_once(
    frame_queue: "queue.Queue",
    pipeline: Any,
    *,
    max_frames: Optional[int] = None,
    timeout_s: float = 0.5,
    on_events: Optional[Callable[[str, List[Dict[str, Any]]], None]] = None,
    camera_names: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Synchronously drain up to ``max_frames`` envelopes from ``frame_queue``
    through ``pipeline`` and return a small summary. Handy for tests and
    one-shot batch runs (no thread)."""
    names = camera_names or {}
    last_seq: Dict[str, int] = {}
    frames = 0
    all_events: List[Dict[str, Any]] = []
    while max_frames is None or frames < max_frames:
        try:
            envelope = frame_queue.get(timeout=timeout_s)
        except queue.Empty:
            break
        try:
            camera_id = getattr(envelope, "camera_id", "CAM-UNKNOWN")
            seq = getattr(envelope, "seq_num", None)
            if seq is not None and last_seq.get(camera_id, -1) >= seq:
                reset = getattr(pipeline, "reset_camera", None)
                if callable(reset):
                    reset(camera_id)
            if seq is not None:
                last_seq[camera_id] = seq
            fi = envelope_to_frame_input(envelope, camera_name=names.get(camera_id))
            events = pipeline.process_frame(fi) or []
            frames += 1
            if events:
                all_events.extend(events)
                if on_events is not None:
                    on_events(camera_id, events)
        finally:
            try:
                frame_queue.task_done()
            except (ValueError, AttributeError):
                pass
    return {"frames_processed": frames, "events": all_events}
