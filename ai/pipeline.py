import os
import cv2
import time
import uuid
import logging
import queue
import requests
import threading
import numpy as np
from collections import deque, OrderedDict
from typing import Dict, List, Any, Optional, Union

from ai.adapter.frame_interface import FrameInput
from ai.detection.vehicle_detector import VehicleDetector
from ai.anpr.plate_locator import PlateLocator
from ai.anpr.preprocess import ImagePreprocessor
from ai.anpr.consensus import MultiFrameConsensus
from ai.ocr.ocr_engine import OCREngine
from ai.ocr.normalizer import PlateNormalizer
from ai.tracking.tracker import ByteTrackTracker

logger = logging.getLogger("AIPipeline")


def _percentile(sorted_samples: List[float], pct: float) -> float:
    """Linear-interpolation percentile over an already-sorted list.
    Callers only ever pass a non-empty list."""
    if len(sorted_samples) == 1:
        return sorted_samples[0]
    k = (len(sorted_samples) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_samples) - 1)
    if f == c:
        return sorted_samples[f]
    return sorted_samples[f] + (sorted_samples[c] - sorted_samples[f]) * (k - f)

class AIPipeline:
    """
    End-to-End SENTINEL AI Computer Vision Analytics Pipeline.
    Processes video frames, detects vehicles, crops license plates, applies preprocessing,
    runs OCR, normalizes text, computes multi-frame consensus, saves evidence, and dispatches JSON events.
    Optimized for high-throughput live RTSP streams via smart OCR temporal throttling,
    bounded multi-camera track memory, and low-latency pre-filtering.
    """

    def __init__(
        self,
        backend_url: Optional[str] = None,
        evidence_dir: Optional[str] = None,
        confidence_threshold: Optional[float] = None,
        ocr_confidence_threshold: Optional[float] = None,
        consensus_stable_threshold: Optional[float] = None,
        ocr_throttle_frames: Optional[int] = None,
        device: str = "cpu"
    ):
        """
        Initialize AI Pipeline with configuration parameters or environment variable overrides.
        """
        self.backend_url = backend_url or os.getenv(
            "SENTINEL_BACKEND_URL", "http://localhost:8000/api/v1/events/ai-detection"
        )
        # Service credential sent as the X-Ingest-Key header so the pipeline can
        # POST events without a user login flow. Unset -> no header (dev / when
        # the backend also has no INGEST_API_KEY configured).
        self.ingest_api_key = os.getenv("SENTINEL_INGEST_API_KEY") or os.getenv("INGEST_API_KEY")
        self.evidence_dir = evidence_dir or os.getenv("SENTINEL_EVIDENCE_DIR", "evidence")

        # Configurable Confidence & Throttling Thresholds
        conf_env = os.getenv("CONFIDENCE_THRESHOLD") or os.getenv("SENTINEL_CONFIDENCE_THRESHOLD")
        self.confidence_threshold = confidence_threshold or (float(conf_env) if conf_env else 0.50)

        ocr_conf_env = os.getenv("OCR_CONFIDENCE_THRESHOLD")
        self.ocr_confidence_threshold = ocr_confidence_threshold or (float(ocr_conf_env) if ocr_conf_env else 0.50)

        stable_env = os.getenv("CONSENSUS_STABLE_THRESHOLD")
        self.consensus_stable_threshold = consensus_stable_threshold or (float(stable_env) if stable_env else 0.75)

        throttle_env = os.getenv("OCR_THROTTLE_FRAMES")
        self.ocr_throttle_frames = ocr_throttle_frames or (int(throttle_env) if throttle_env else 10)

        # Multi-variant preprocessing + best-of OCR (Phase 3). On by default;
        # SENTINEL_OCR_MULTIVARIANT=0 falls back to the single-pass path.
        self.multivariant_ocr = os.getenv("SENTINEL_OCR_MULTIVARIANT", "1").lower() not in (
            "0", "false", "no", "off",
        )
        self.ocr_max_variants = int(os.getenv("SENTINEL_OCR_MAX_VARIANTS", "3"))
        # Inline the frame snapshot (base64) in the event so the backend can put
        # it in object storage -- needed when pipeline and backend don't share a
        # filesystem (e.g. containers).
        self.send_snapshot_b64 = os.getenv("SENTINEL_SEND_SNAPSHOT", "0").lower() in (
            "1", "true", "yes", "on",
        )
        self._snapshot_sent: set = set()

        # Ensure evidence directory exists
        os.makedirs(self.evidence_dir, exist_ok=True)

        logger.info(
            f"Initializing SENTINEL AI Pipeline (conf_thresh: {self.confidence_threshold}, "
            f"ocr_thresh: {self.ocr_confidence_threshold}, stable_thresh: {self.consensus_stable_threshold}, "
            f"ocr_throttle: {self.ocr_throttle_frames})..."
        )
        self.vehicle_detector = VehicleDetector(conf_threshold=self.confidence_threshold, device=device)
        self.plate_locator = PlateLocator()
        self.preprocessor = ImagePreprocessor()
        self.ocr_engine = OCREngine()
        self.normalizer = PlateNormalizer()
        self.consensus_engine = MultiFrameConsensus(min_confidence_threshold=self.ocr_confidence_threshold)
        # Phase 15B: per-crop quality metrics + explicit ANPR failure reasons.
        from ai.anpr.quality import PlateQualityAssessor
        self.quality_assessor = PlateQualityAssessor()

        # Bounded in-memory buffer for retry on API *unreachability* (5xx /
        # connection errors). 4xx responses are NOT buffered -- retrying a
        # rejected payload forever never helps.
        self.event_buffer: "deque[Dict[str, Any]]" = deque(maxlen=2000)

        # One ByteTrack tracker per camera feed -> track IDs are camera-local and
        # persistent across frames. State cannot leak between cameras because each
        # camera_id gets its own ByteTrackTracker instance (see _get_tracker).
        self._trackers: Dict[str, ByteTrackTracker] = {}

        # Track OCR throttling counter and saved evidence state: key -> count / filename
        self.track_ocr_counter: Dict[str, int] = {}
        self.saved_evidence_tracks: Dict[str, str] = {}
        # camera:track -> last plate string we emitted an event for (dedup)
        self._emitted_tracks: Dict[str, str] = {}

        # Performance & Benchmark Statistics
        self.stats = {
            "total_frames": 0,
            "processed_frames": 0,
            "total_vehicles": 0,
            "total_detections": 0,
            "ocr_skipped_count": 0,
            "vehicle_detection_time_ms": 0.0,
            "ocr_time_ms": 0.0,
            "total_pipeline_time_ms": 0.0,
            # Async event-delivery outcome counters (Phase 2A Task 2) -- every
            # one of these is a REPORTED count, never a silent drop.
            "events_enqueued": 0,
            "events_sent_ok": 0,
            "events_dropped_queue_full": 0,
            "events_dropped_backend_rejected": 0,
            "events_dropped_buffer_full": 0,
        }

        # --- Async event delivery (Phase 2A Task 2) -------------------------
        # SENTINEL_System_Audit_Report.md flagged the synchronous
        # `requests.post` inside process_frame() as sitting in the AI hot
        # path -- a slow/down backend used to add up to 5s of stall per
        # event, serialized behind every camera sharing this pipeline
        # instance. process_frame() now only enqueues (non-blocking); a
        # single background thread drains the queue and performs the actual
        # (retrying) HTTP POST via the EXISTING _dispatch_event /
        # _post_one / _flush_buffer logic below, completely unchanged --
        # only the CALLER moved off the inference thread. The queue is
        # bounded so a stuck backend can never grow memory unboundedly; a
        # full queue drops the new event and counts it
        # (events_dropped_queue_full), it never blocks detection.
        self.event_queue_maxsize = int(os.getenv("SENTINEL_EVENT_QUEUE_SIZE", "500"))
        self._event_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=self.event_queue_maxsize)
        self._event_queue_max_depth = 0
        self._sender_stop = threading.Event()
        self._sender_thread: Optional[threading.Thread] = None

        # event_id -> monotonic frame-received timestamp, so the sender
        # thread can compute "compute latency" (frame ingested -> event
        # hand-off) and "end-to-end latency" (frame ingested -> delivered)
        # without putting any extra field into the wire payload itself.
        # Bounded (oldest evicted first) so a never-dequeued id can't leak.
        self._event_timing: "OrderedDict[str, float]" = OrderedDict()
        self._event_timing_lock = threading.Lock()
        self._EVENT_TIMING_MAX = 2000

        # Bounded raw-sample windows (milliseconds) for p50/p95 reporting --
        # Task 1 wants percentiles, not just the running averages self.stats
        # already tracks. monotonic-clock durations only; never PTS.
        self._yolo_latency_samples: "deque[float]" = deque(maxlen=2000)
        self._ocr_latency_samples: "deque[float]" = deque(maxlen=2000)
        self._send_latency_samples: "deque[float]" = deque(maxlen=2000)
        self._compute_latency_samples: "deque[float]" = deque(maxlen=2000)
        self._e2e_latency_samples: "deque[float]" = deque(maxlen=2000)

        # Per-camera processed-frame / generated-event counts (Task 1).
        # Only ever touched from process_frame(), which this codebase's own
        # architecture guarantees runs on a single consumer thread -- no
        # lock needed (see ai/adapter/ingestion_bridge.py's own docstring).
        self._frames_by_camera: Dict[str, int] = {}
        self._events_by_camera: Dict[str, int] = {}

        # Optional CPU%/RSS sampling (psutil). Never a hard dependency --
        # get_resource_usage() just returns Nones if it isn't importable.
        self._psutil_process = None
        try:
            import psutil  # noqa: F401 -- deliberately local/lazy
            self._psutil_process = psutil.Process()
            self._psutil_process.cpu_percent(interval=None)  # prime the counter
        except Exception:  # noqa: BLE001
            logger.debug("psutil unavailable -- CPU/RAM metrics will report null")

        self._start_sender_thread()

    # ------------------------------------------------------------------ #
    #  Async event delivery: bounded queue + background sender thread     #
    # ------------------------------------------------------------------ #
    def _start_sender_thread(self) -> None:
        if self._sender_thread is not None and self._sender_thread.is_alive():
            return
        self._sender_stop.clear()
        self._sender_thread = threading.Thread(
            target=self._sender_loop, name="ai-event-sender", daemon=True
        )
        self._sender_thread.start()

    def _sender_loop(self) -> None:
        """Runs on its own daemon thread for the pipeline's whole lifetime.
        Pulls one event at a time and dispatches it through the EXISTING
        _dispatch_event (buffer-on-5xx / drop-on-4xx / flush-on-success)
        logic -- nothing about that retry policy changed, only which thread
        calls it. A backend that's slow or down therefore only ever delays
        this thread, never the inference hot path calling process_frame()."""
        while not (self._sender_stop.is_set() and self._event_queue.empty()):
            try:
                payload = self._event_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            t_dequeue = time.monotonic()
            event_id = payload.get("event_id")
            recv_mono = None
            if event_id is not None:
                with self._event_timing_lock:
                    recv_mono = self._event_timing.pop(event_id, None)
            try:
                ok = self._dispatch_event(payload)
            except Exception:  # noqa: BLE001 -- the sender thread must never die
                logger.exception("event sender: unexpected error dispatching %s", event_id)
                ok = False
            send_ms = (time.monotonic() - t_dequeue) * 1000.0
            self._send_latency_samples.append(send_ms)
            if ok and recv_mono is not None:
                compute_ms = (t_dequeue - recv_mono) * 1000.0
                self._compute_latency_samples.append(compute_ms)
                self._e2e_latency_samples.append(compute_ms + send_ms)
            try:
                self._event_queue.task_done()
            except (ValueError, AttributeError):
                pass

    def _enqueue_event(self, payload: Dict[str, Any], recv_mono: Optional[float] = None) -> None:
        """Non-blocking hand-off from the inference hot path to the
        background sender. Never touches the network. A full queue means
        the sender/backend genuinely can't keep up -- the event is COUNTED
        as dropped (events_dropped_queue_full), never silently discarded."""
        event_id = payload.get("event_id")
        if recv_mono is not None and event_id is not None:
            with self._event_timing_lock:
                self._event_timing[event_id] = recv_mono
                while len(self._event_timing) > self._EVENT_TIMING_MAX:
                    self._event_timing.popitem(last=False)
        try:
            self._event_queue.put_nowait(payload)
            self.stats["events_enqueued"] += 1
            depth = self._event_queue.qsize()
            if depth > self._event_queue_max_depth:
                self._event_queue_max_depth = depth
        except queue.Full:
            self.stats["events_dropped_queue_full"] += 1
            if event_id is not None:
                with self._event_timing_lock:
                    self._event_timing.pop(event_id, None)
            logger.warning(
                "Event queue full (maxsize=%d) -- dropping event %s for camera %s "
                "(sender/backend can't keep up)",
                self.event_queue_maxsize, event_id, payload.get("camera_id"),
            )

    def _wait_for_queue_empty(self, timeout: float = 5.0) -> bool:
        """Poll (never a blind sleep) until every event handed to
        _enqueue_event so far has been picked up by the sender thread, or
        `timeout` elapses. Used by flush_events()/shutdown() so callers that
        need a deterministic "it's been sent (or moved to the retry
        buffer)" point still have one now that dispatch is asynchronous."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._event_queue.unfinished_tasks == 0:
                return True
            time.sleep(0.02)
        return self._event_queue.unfinished_tasks == 0

    def shutdown(self, drain_timeout: float = 5.0) -> int:
        """Graceful shutdown (Task 2): stop the sender thread, giving it up
        to `drain_timeout` to finish whatever's already queued through the
        normal retrying path. Anything still stuck in the queue afterward
        (e.g. the thread was mid-backoff-sleep on one stubborn event) is
        moved into the existing retry buffer rather than discarded, so a
        subsequent flush_events() still picks it up. Returns how many
        events remain buffered/unsent. Safe to call more than once."""
        self._wait_for_queue_empty(timeout=drain_timeout)
        self._sender_stop.set()
        if self._sender_thread is not None:
            self._sender_thread.join(timeout=drain_timeout)
        moved = 0
        while True:
            try:
                payload = self._event_queue.get_nowait()
            except queue.Empty:
                break
            self.event_buffer.append(payload)
            moved += 1
            try:
                self._event_queue.task_done()
            except (ValueError, AttributeError):
                pass
        if moved:
            logger.info("shutdown: moved %d unsent queued event(s) into the retry buffer", moved)
        return len(self.event_buffer)

    # ------------------------------------------------------------------ #
    #  Per-camera ByteTrack tracker registry                              #
    # ------------------------------------------------------------------ #
    def _get_tracker(self, camera_id: str) -> ByteTrackTracker:
        """Return the ByteTrack tracker owning ``camera_id`` (created on first use).

        One instance per camera => camera-local, persistent track IDs, and no
        cross-camera state leakage.
        """
        tracker = self._trackers.get(camera_id)
        if tracker is None:
            # track_thresh sits below the detector's own confidence gate so every
            # detection the detector already accepted is treated as high-score;
            # new_track_thresh == detector threshold so any accepted detection can
            # start a track.
            low = max(0.05, self.confidence_threshold - 0.25)
            tracker = ByteTrackTracker(
                track_thresh=low,
                new_track_thresh=self.confidence_threshold,
                match_thresh=0.85,
                track_buffer=30,
                frame_rate=30,
            )
            self._trackers[camera_id] = tracker
        return tracker

    def reset_camera(self, camera_id: str) -> None:
        """Drop tracker + per-track bookkeeping for a camera (e.g. on stream
        reconnect / discontinuity). Other cameras are untouched."""
        self._trackers.pop(camera_id, None)
        prefix = f"{camera_id}:"
        for d in (self.track_ocr_counter, self.saved_evidence_tracks, self._emitted_tracks):
            for k in [k for k in d if k.startswith(prefix)]:
                d.pop(k, None)

    def process_frame(
        self,
        frame_input: Union[FrameInput, np.ndarray],
        camera_id: str = "CAM-001",
        frame_timestamp: Optional[str] = None,
        pts: Optional[float] = None,
        track_ids: Optional[List[int]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Process a single video stream frame through the entire SENTINEL AI pipeline.

        :param frame_input: Either a FrameInput object or raw BGR numpy ndarray
        :param camera_id: Identifier of the camera stream (multi-camera state isolated)
        :param frame_timestamp: ISO timestamp string or UNIX epoch string
        :param pts: Stream presentation timestamp (PTS)
        :param track_ids: Optional explicit track-id override (one per detection,
                          in detection order). When omitted (the normal case) the
                          pipeline runs detections through a per-camera
                          ByteTrackTracker and uses its persistent IDs.
        :param metadata: Additional frame metadata
        :return: List of generated AI Detection Event dictionaries
        """
        # Internal duration timers use time.monotonic() throughout this method
        # (never wall time, never PTS) -- PTS is stream-relative and wall
        # time can jump; monotonic is the only clock safe for measuring
        # elapsed processing latency. The wire event's own `timestamp` field
        # (frame_timestamp, derived below) is unaffected and stays wall-clock.
        t_start = time.monotonic()
        self.stats["total_frames"] += 1

        # Unpack FrameInput object if provided
        if isinstance(frame_input, FrameInput):
            frame = frame_input.frame
            camera_id = frame_input.camera_id
            pts = frame_input.pts
            frame_timestamp = frame_input.get_event_timestamp()
            metadata = frame_input.metadata
        else:
            frame = frame_input
            if frame_timestamp is None:
                if pts is not None:
                    try:
                        pts_val = float(pts)
                        if pts_val > 1e11:
                            t_sec = pts_val / 1000.0
                        elif pts_val > 1e8:
                            t_sec = pts_val
                        else:
                            t_sec = time.time()
                        frame_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t_sec))
                    except Exception:
                        frame_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                else:
                    frame_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Gracefully handle empty or malformed frame arrays
        if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0 or len(frame.shape) < 2:
            logger.warning("Empty or malformed frame passed to AIPipeline. Skipping frame.")
            return []

        self.stats["processed_frames"] += 1
        self._frames_by_camera[camera_id] = self._frames_by_camera.get(camera_id, 0) + 1
        events: List[Dict[str, Any]] = []

        # Step 1: Vehicle Detection
        t_det0 = time.monotonic()
        try:
            detections = self.vehicle_detector.detect(frame)
        except Exception as e:
            logger.error(f"Error during vehicle detection: {e}")
            return []
        t_det = (time.monotonic() - t_det0) * 1000.0
        self.stats["vehicle_detection_time_ms"] += t_det
        self._yolo_latency_samples.append(t_det)

        if not detections:
            # Advance this camera's tracker on empty frames too, so lost tracks
            # age out and short occlusions are bridged by the Kalman predictor.
            if track_ids is None and camera_id in self._trackers:
                try:
                    self._trackers[camera_id].update([])
                except Exception as e:
                    logger.error(f"ByteTrack update failed on {camera_id}: {e}")
            t_total = (time.monotonic() - t_start) * 1000.0
            self.stats["total_pipeline_time_ms"] += t_total
            return []

        self.stats["total_vehicles"] += len(detections)

        # Step 1b: Persistent multi-object tracking (ByteTrack).
        # Default path: run detections through this camera's own tracker so
        # track_id is STABLE across consecutive frames. Legacy path: an explicit
        # `track_ids` list (e.g. an external tracker) overrides.
        if track_ids is not None:
            tracked_vehicles = [
                {
                    "class": det["class"],
                    "confidence": det["confidence"],
                    "bbox": det["bbox"],
                    "track_id": track_ids[idx] if idx < len(track_ids) else idx + 1,
                }
                for idx, det in enumerate(detections)
            ]
        else:
            try:
                online = self._get_tracker(camera_id).update(detections)
            except Exception as e:  # tracker must never take down the pipeline
                logger.error(f"ByteTrack update failed on {camera_id}: {e}")
                online = []
            tracked_vehicles = [
                {
                    "class": t.get("class") or "vehicle",
                    "confidence": float(t.get("score", 0.0)),
                    "bbox": [int(round(v)) for v in t["bbox"]],
                    "track_id": t["track_id"],
                }
                for t in online
            ]

        for vehicle in tracked_vehicles:
            vehicle_class = vehicle["class"]
            vehicle_conf = vehicle["confidence"]
            vehicle_bbox = vehicle["bbox"]
            track_id = vehicle["track_id"]
            track_key = f"{camera_id}:{track_id}"

            # Crop vehicle region
            try:
                vehicle_crop = self.vehicle_detector.crop_vehicle(frame, vehicle_bbox)
                if vehicle_crop is None or vehicle_crop.size == 0:
                    continue
            except Exception as e:
                logger.error(f"Error cropping vehicle region: {e}")
                continue

            # Step 2: License Plate Region Locator
            locator_res = self.plate_locator.locate_plate(vehicle_crop)
            plate_crop = locator_res["plate_crop"]
            rel_plate_bbox = locator_res["bbox"]

            # Convert relative plate bbox to full frame coordinates
            vx1, vy1, _, _ = vehicle_bbox
            px1, py1, px2, py2 = rel_plate_bbox
            abs_plate_bbox = [vx1 + px1, vy1 + py1, vx1 + px2, vy1 + py2]

            # Step 3: Check Smart OCR Throttling
            # If vehicle track already reached a stable consensus plate, throttle expensive OCR calls
            is_stable = self.consensus_engine.is_stable(
                track_id=track_id,
                camera_id=camera_id,
                min_votes=3,
                min_confidence=self.consensus_stable_threshold
            )

            skip_ocr = False
            if is_stable:
                curr_count = self.track_ocr_counter.get(track_key, 0) + 1
                self.track_ocr_counter[track_key] = curr_count
                if (curr_count % self.ocr_throttle_frames) != 0:
                    skip_ocr = True

            # Phase 15B defaults (overwritten in the OCR branch below).
            fmt_score = 1.0
            quality_obj = None
            located = bool(locator_res.get("confidence", 0.0) > 0.0)

            if skip_ocr:
                # Reuse cached stable consensus result
                self.stats["ocr_skipped_count"] += 1
                consensus_res = self.consensus_engine.get_consensus(track_id, camera_id=camera_id)
                final_plate = consensus_res["consensus_plate"]
                final_conf = consensus_res["confidence"]
                raw_text = final_plate
                enhanced_plate = plate_crop
            else:
                # Step 4: quality gate -> multi-variant preprocessing -> OCR
                t_ocr0 = time.monotonic()
                if self.multivariant_ocr:
                    variants = self.preprocessor.variants(plate_crop, max_variants=self.ocr_max_variants)
                    if variants:
                        ocr_res = self.ocr_engine.extract_best(variants, self.normalizer)
                        vi = ocr_res.get("variant", 0)
                        enhanced_plate = variants[vi] if 0 <= vi < len(variants) else variants[0]
                    else:
                        # crop failed the quality gate -> nothing readable
                        ocr_res = {"raw_text": "UNKNOWN", "confidence": 0.0}
                        enhanced_plate = self.preprocessor.preprocess(plate_crop)
                else:
                    enhanced_plate = self.preprocessor.preprocess(plate_crop)
                    ocr_res = self.ocr_engine.extract_text(enhanced_plate)
                t_ocr = (time.monotonic() - t_ocr0) * 1000.0
                self.stats["ocr_time_ms"] += t_ocr
                self._ocr_latency_samples.append(t_ocr)

                raw_text = ocr_res["raw_text"]
                ocr_conf = ocr_res["confidence"]

                # Step 5: Plate Normalization (position-aware, format-checked)
                normalized_plate = self.normalizer.normalize(raw_text)
                fmt_score = self.normalizer.format_score(normalized_plate)

                # Phase 15B: assess THIS crop's quality (cheap, single-pass).
                try:
                    quality_obj = self.quality_assessor.assess(plate_crop)
                except Exception:  # noqa: BLE001 -- quality is best-effort
                    quality_obj = None

                # Step 6: Multi-Frame Consensus Voting (OCR conf + detection conf
                # + format validity + plate-locator quality + temporal
                # stability; stable plates lock)
                consensus_res = self.consensus_engine.add_prediction(
                    track_id=track_id,
                    plate_number=normalized_plate,
                    confidence=ocr_conf,
                    camera_id=camera_id,
                    detection_confidence=float(vehicle_conf),
                    format_score=fmt_score,
                    plate_quality=float(locator_res.get("confidence", 1.0)),
                )
                final_plate = consensus_res["consensus_plate"]
                final_conf = consensus_res["confidence"]

            # Determine whether a valid license plate was successfully recognized
            plate_detected = bool(final_plate != "UNKNOWN" and final_conf > 0.0)

            # Phase 15B: explicit ANPR status + failure reason instead of a
            # bare UNKNOWN. A recognised plate -> status OK, reason NONE.
            from ai.anpr.quality import FailureReason, PlateQuality
            _q = quality_obj if quality_obj is not None else PlateQuality()
            _reads = consensus_res.get("raw_reads", []) if isinstance(consensus_res, dict) else []
            if plate_detected and final_conf >= self.ocr_confidence_threshold:
                anpr_status = "OK"
                anpr_failure_reason = FailureReason.NONE
            else:
                anpr_status = "UNKNOWN"
                try:
                    anpr_failure_reason = self.quality_assessor.classify_failure(
                        _q, located=located, ocr_text=raw_text,
                        normalized_plate=(final_plate if final_plate != "UNKNOWN" else None),
                        format_score=float(fmt_score), confidence=float(final_conf),
                        raw_reads=_reads, conf_threshold=self.ocr_confidence_threshold,
                    )
                except Exception:  # noqa: BLE001
                    anpr_failure_reason = FailureReason.LOW_CONFIDENCE

            # Step 7: Save Evidence Snapshots (Optimized to avoid redundant disk writes per frame)
            ts_str = str(int(time.time()))
            snapshot_filename = f"{camera_id}_{ts_str}_tr{track_id}_{final_plate}.jpg"
            crop_filename = f"{camera_id}_{ts_str}_tr{track_id}_{final_plate}_crop.jpg"

            # absolute so a separately-running backend on the same host can
            # resolve the file:// reference
            snapshot_path = os.path.abspath(os.path.join(self.evidence_dir, snapshot_filename))
            crop_path = os.path.abspath(os.path.join(self.evidence_dir, crop_filename))

            # Write evidence to disk if new track or readable plate detected
            evidence_key = f"{track_key}:{final_plate}"
            if evidence_key not in self.saved_evidence_tracks:
                try:
                    cv2.imwrite(snapshot_path, frame)
                    cv2.imwrite(crop_path, enhanced_plate)
                    self.saved_evidence_tracks[evidence_key] = snapshot_path
                except Exception as e:
                    logger.error(f"Failed to write evidence files: {e}")
            else:
                # Use previously saved evidence path for consistency
                snapshot_path = self.saved_evidence_tracks[evidence_key]
                crop_path = snapshot_path.replace(".jpg", "_crop.jpg")

            # Step 8: Build Structured AI Detection Event JSON Payload
            _md = metadata or {}
            event_payload = {
                "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                "timestamp": frame_timestamp,
                "pts": pts,
                "camera_id": camera_id,
                "camera_name": _md.get("camera_name"),
                "track_id": track_id,
                "latitude": _md.get("latitude"),
                "longitude": _md.get("longitude"),
                "seq_num": _md.get("seq_num"),
                "vehicle": {
                    "type": vehicle_class,
                    "class": vehicle_class,
                    "confidence": vehicle_conf,
                    "bbox": vehicle_bbox,
                    "track_id": track_id
                },
                "license_plate": {
                    "plate_detected": plate_detected,
                    "text": final_plate,
                    "plate_number": final_plate,
                    "confidence": final_conf if plate_detected else 0.0,
                    "bbox": abs_plate_bbox,
                    "raw_text": raw_text,
                    "consensus_applied": len(consensus_res.get("raw_reads", [])) > 1,
                    "raw_reads": consensus_res.get("raw_reads", [])
                },
                "evidence": {
                    "frame_path": snapshot_path,
                    "frame_snapshot_path": snapshot_path,
                    "plate_crop_path": crop_path
                },
                # Phase 15B: ANPR quality + explicit failure reason.
                "anpr": {
                    "status": anpr_status,
                    "failure_reason": anpr_failure_reason,
                    "plate_quality": round(float(locator_res.get("confidence", 0.0)), 4),
                    "quality": _q.to_dict() if hasattr(_q, "to_dict") else {},
                    "quality_score": _q.overall_score if hasattr(_q, "overall_score") else 0.0,
                    "ocr_confidence": round(float(final_conf), 4),
                },
            }

            # Optionally inline the snapshot so the backend can store it in
            # object storage (works across container / host boundaries, unlike
            # a bare file path). SENTINEL_SEND_SNAPSHOT=1 to enable.
            if self.send_snapshot_b64 and evidence_key not in getattr(self, "_snapshot_sent", set()):
                try:
                    okj, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if okj:
                        import base64
                        event_payload["snapshot_base64"] = base64.b64encode(buf.tobytes()).decode("ascii")
                        event_payload["snapshot_content_type"] = "image/jpeg"
                        self._snapshot_sent = getattr(self, "_snapshot_sent", set())
                        self._snapshot_sent.add(evidence_key)
                except Exception as e:  # noqa: BLE001
                    logger.debug("snapshot encode failed: %s", e)

            # Step 9: One consolidated event per (camera, track, plate).
            # Continuous video emits a detection every frame; without this a
            # single vehicle passing one camera would generate hundreds of
            # near-identical events (and journey rows). We emit the first time a
            # track is seen, and again whenever its plate changes -- notably on
            # the UNKNOWN -> readable transition once consensus settles.
            emit_key = f"{track_key}"
            last_plate = self._emitted_tracks.get(emit_key)
            if last_plate is None or last_plate != final_plate:
                self._emitted_tracks[emit_key] = final_plate
                events.append(event_payload)
                self.stats["total_detections"] += 1
                self._events_by_camera[camera_id] = self._events_by_camera.get(camera_id, 0) + 1
                # Hand off to the background sender (Task 2) -- NEVER a
                # blocking network call on this thread. `recv_mono` (this
                # frame's ingestion-side monotonic receipt time, if the
                # ingestion bridge supplied one) lets the sender compute a
                # real compute/end-to-end latency without adding any field
                # to the event payload itself -- the wire schema is
                # untouched.
                recv_mono = None
                _raw_recv = (metadata or {}).get("received_at_s")
                if isinstance(_raw_recv, (int, float)):
                    recv_mono = float(_raw_recv)
                self._enqueue_event(event_payload, recv_mono=recv_mono)

        t_total = (time.monotonic() - t_start) * 1000.0
        self.stats["total_pipeline_time_ms"] += t_total

        return events

    def get_benchmark_stats(self) -> Dict[str, Any]:
        """Calculates and returns pipeline latency & FPS performance metrics."""
        proc_frames = max(1, self.stats["processed_frames"])
        total_veh = max(1, self.stats["total_vehicles"])

        avg_yolo_ms = self.stats["vehicle_detection_time_ms"] / proc_frames
        avg_ocr_ms = self.stats["ocr_time_ms"] / total_veh
        avg_total_ms = self.stats["total_pipeline_time_ms"] / proc_frames
        fps = 1000.0 / avg_total_ms if avg_total_ms > 0 else 0.0

        return {
            "total_frames_received": self.stats["total_frames"],
            "processed_frames": self.stats["processed_frames"],
            "total_vehicles_detected": self.stats["total_vehicles"],
            "total_ai_events_generated": self.stats["total_detections"],
            "ocr_skipped_count": self.stats["ocr_skipped_count"],
            "avg_vehicle_detection_ms": round(avg_yolo_ms, 2),
            "avg_ocr_ms": round(avg_ocr_ms, 2),
            "avg_pipeline_latency_ms": round(avg_total_ms, 2),
            "estimated_fps": round(fps, 2)
        }

    @staticmethod
    def _samples_summary(samples: "deque[float]") -> Dict[str, Optional[float]]:
        """count/avg/p50/p95 over a bounded latency-sample window. Reports
        None (never a fabricated number) when there aren't enough/any
        samples yet -- e.g. OCR p95 before a single OCR call has run."""
        if not samples:
            return {"count": 0, "avg_ms": None, "p50_ms": None, "p95_ms": None}
        ordered = sorted(samples)
        return {
            "count": len(ordered),
            "avg_ms": round(sum(ordered) / len(ordered), 2),
            "p50_ms": round(_percentile(ordered, 50), 2),
            "p95_ms": round(_percentile(ordered, 95), 2),
        }

    def get_resource_usage(self) -> Dict[str, Optional[float]]:
        """This process's CPU%/RSS-MB, if psutil was importable at startup
        (Task 1 "CPU/RAM if practical"). Never raises; returns Nones
        otherwise so callers can tell "not measured" from "zero"."""
        if self._psutil_process is None:
            return {"cpu_percent": None, "rss_mb": None}
        try:
            cpu = self._psutil_process.cpu_percent(interval=None)
            rss_mb = self._psutil_process.memory_info().rss / (1024.0 * 1024.0)
            return {"cpu_percent": round(cpu, 1), "rss_mb": round(rss_mb, 1)}
        except Exception:  # noqa: BLE001
            return {"cpu_percent": None, "rss_mb": None}

    def get_metrics(self) -> Dict[str, Any]:
        """Full instrumentation snapshot (Phase 2A Task 1): everything
        get_benchmark_stats() already reports, PLUS event-queue depth /
        backpressure, per-outcome event-delivery counts, latency
        percentiles (not just running averages), per-camera frame/event
        counts, and CPU/RAM. Pure in-memory reads -- no I/O, cheap enough
        to poll from a stats loop or the benchmark script every few
        seconds."""
        metrics = self.get_benchmark_stats()
        metrics.update({
            "event_queue_depth": self._event_queue.qsize(),
            "event_queue_max_depth": self._event_queue_max_depth,
            "event_queue_maxsize": self.event_queue_maxsize,
            "events_enqueued": self.stats["events_enqueued"],
            "events_sent_ok": self.stats["events_sent_ok"],
            "events_dropped_queue_full": self.stats["events_dropped_queue_full"],
            "events_dropped_backend_rejected": self.stats["events_dropped_backend_rejected"],
            "events_dropped_buffer_full": self.stats["events_dropped_buffer_full"],
            "events_buffered_for_retry": len(self.event_buffer),
            "yolo_latency_ms": self._samples_summary(self._yolo_latency_samples),
            "ocr_latency_ms": self._samples_summary(self._ocr_latency_samples),
            "send_latency_ms": self._samples_summary(self._send_latency_samples),
            "compute_latency_ms": self._samples_summary(self._compute_latency_samples),
            "end_to_end_latency_ms": self._samples_summary(self._e2e_latency_samples),
            "frames_by_camera": dict(self._frames_by_camera),
            "events_by_camera": dict(self._events_by_camera),
            "resource_usage": self.get_resource_usage(),
        })
        return metrics

    def _post_headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.ingest_api_key:
            h["X-Ingest-Key"] = self.ingest_api_key
        return h

    def _post_one(self, payload: Dict[str, Any]) -> str:
        """POST one event. Returns 'ok' | 'retry' (buffer it) | 'drop' (don't)."""
        try:
            resp = requests.post(
                self.backend_url, json=payload, headers=self._post_headers(), timeout=5.0
            )
        except Exception as exc:  # connection refused / timeout / DNS
            logger.debug("backend unreachable (%s) -- buffering event", exc)
            return "retry"
        if resp.status_code in (200, 201):
            return "ok"
        if resp.status_code in (429,) or resp.status_code >= 500:
            logger.warning("backend %s -- buffering event for retry", resp.status_code)
            return "retry"
        # 4xx (auth / validation) -- retrying the same payload will never help
        body = resp.text[:200] if hasattr(resp, "text") else ""
        logger.error("backend rejected event %s: %s %s", payload.get("event_id"), resp.status_code, body)
        return "drop"

    def _dispatch_event(self, payload: Dict[str, Any]) -> bool:
        """POST an event. Buffers on 5xx/unreachable, drops on 4xx, flushes the
        backlog on success. Returns True iff the event was accepted."""
        outcome = self._post_one(payload)
        if outcome == "ok":
            plate = payload.get("license_plate", {}).get("text", payload.get("plate_number"))
            logger.info("Event %s published to backend (%s)", payload.get("event_id"), plate)
            self.stats["events_sent_ok"] += 1
            self._flush_buffer()
            return True
        if outcome == "retry":
            # Reported, never silent: the retry deque is bounded (maxlen=2000)
            # -- if it's already full, this append evicts the oldest queued
            # event, so count that eviction explicitly (Task 2 "no unbounded
            # memory growth" + "do not silently lose events").
            if len(self.event_buffer) >= (self.event_buffer.maxlen or 0):
                self.stats["events_dropped_buffer_full"] += 1
            self.event_buffer.append(payload)
        elif outcome == "drop":
            self.stats["events_dropped_backend_rejected"] += 1
        return False

    def _flush_buffer(self) -> None:
        """Retry buffered events (oldest first). Stops on the first still-failing
        one so ordering is preserved and we don't hammer a flaky backend."""
        if not self.event_buffer:
            return
        logger.info("Flushing %d buffered events to backend...", len(self.event_buffer))
        flushed = 0
        while self.event_buffer:
            payload = self.event_buffer[0]
            outcome = self._post_one(payload)
            if outcome == "ok":
                self.event_buffer.popleft()
                self.stats["events_sent_ok"] += 1
                flushed += 1
            elif outcome == "drop":
                self.event_buffer.popleft()
                self.stats["events_dropped_backend_rejected"] += 1
            else:  # retry -- backend still down, stop for now
                break
        if flushed:
            logger.info("Flushed %d buffered events (%d remaining)", flushed, len(self.event_buffer))

    def flush_events(self) -> int:
        """Public: wait for the background sender to drain whatever's
        already queued (Task 2 async hand-off means that's no longer
        instantaneous), then retry the backlog same as before. Returns the
        number of events still buffered/unsent afterward."""
        self._wait_for_queue_empty(timeout=5.0)
        self._flush_buffer()
        return len(self.event_buffer)
