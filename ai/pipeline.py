import os
import cv2
import time
import uuid
import logging
import requests
import numpy as np
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

        # In-memory buffer for retry on API unreachability
        self.event_buffer: List[Dict[str, Any]] = []

        # One ByteTrack tracker per camera feed -> track IDs are camera-local and
        # persistent across frames. State cannot leak between cameras because each
        # camera_id gets its own ByteTrackTracker instance (see _get_tracker).
        self._trackers: Dict[str, ByteTrackTracker] = {}

        # Track OCR throttling counter and saved evidence state: key -> count / filename
        self.track_ocr_counter: Dict[str, int] = {}
        self.saved_evidence_tracks: Dict[str, str] = {}

        # Performance & Benchmark Statistics
        self.stats = {
            "total_frames": 0,
            "processed_frames": 0,
            "total_vehicles": 0,
            "total_detections": 0,
            "ocr_skipped_count": 0,
            "vehicle_detection_time_ms": 0.0,
            "ocr_time_ms": 0.0,
            "total_pipeline_time_ms": 0.0
        }

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
        for d in (self.track_ocr_counter, self.saved_evidence_tracks):
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
        t_start = time.time()
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
        events: List[Dict[str, Any]] = []

        # Step 1: Vehicle Detection
        t_det0 = time.time()
        try:
            detections = self.vehicle_detector.detect(frame)
        except Exception as e:
            logger.error(f"Error during vehicle detection: {e}")
            return []
        t_det = (time.time() - t_det0) * 1000.0
        self.stats["vehicle_detection_time_ms"] += t_det

        if not detections:
            # Advance this camera's tracker on empty frames too, so lost tracks
            # age out and short occlusions are bridged by the Kalman predictor.
            if track_ids is None and camera_id in self._trackers:
                try:
                    self._trackers[camera_id].update([])
                except Exception as e:
                    logger.error(f"ByteTrack update failed on {camera_id}: {e}")
            t_total = (time.time() - t_start) * 1000.0
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

            if skip_ocr:
                # Reuse cached stable consensus result
                self.stats["ocr_skipped_count"] += 1
                consensus_res = self.consensus_engine.get_consensus(track_id, camera_id=camera_id)
                final_plate = consensus_res["consensus_plate"]
                final_conf = consensus_res["confidence"]
                raw_text = final_plate
                enhanced_plate = plate_crop
            else:
                # Step 4: Image Preprocessing & OCR Engine
                enhanced_plate = self.preprocessor.preprocess(plate_crop)

                t_ocr0 = time.time()
                ocr_res = self.ocr_engine.extract_text(enhanced_plate)
                t_ocr = (time.time() - t_ocr0) * 1000.0
                self.stats["ocr_time_ms"] += t_ocr

                raw_text = ocr_res["raw_text"]
                ocr_conf = ocr_res["confidence"]

                # Step 5: Plate Normalization
                normalized_plate = self.normalizer.normalize(raw_text)

                # Step 6: Multi-Frame Consensus Voting
                consensus_res = self.consensus_engine.add_prediction(
                    track_id=track_id,
                    plate_number=normalized_plate,
                    confidence=ocr_conf,
                    camera_id=camera_id
                )
                final_plate = consensus_res["consensus_plate"]
                final_conf = consensus_res["confidence"]

            # Determine whether a valid license plate was successfully recognized
            plate_detected = bool(final_plate != "UNKNOWN" and final_conf > 0.0)

            # Step 7: Save Evidence Snapshots (Optimized to avoid redundant disk writes per frame)
            ts_str = str(int(time.time()))
            snapshot_filename = f"{camera_id}_{ts_str}_tr{track_id}_{final_plate}.jpg"
            crop_filename = f"{camera_id}_{ts_str}_tr{track_id}_{final_plate}_crop.jpg"

            snapshot_path = os.path.join(self.evidence_dir, snapshot_filename)
            crop_path = os.path.join(self.evidence_dir, crop_filename)

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
            event_payload = {
                "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                "timestamp": frame_timestamp,
                "pts": pts,
                "camera_id": camera_id,
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
                }
            }

            events.append(event_payload)
            self.stats["total_detections"] += 1

            # Step 9: Dispatch HTTP POST Payload to backend API
            self._dispatch_event(event_payload)

        t_total = (time.time() - t_start) * 1000.0
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

    def _dispatch_event(self, payload: Dict[str, Any]) -> bool:
        """
        Send event payload via HTTP POST to backend API. Buffers locally if backend unreachable.

        :param payload: Event payload dictionary
        :return: True if posted successfully, False if buffered
        """
        try:
            resp = requests.post(
                self.backend_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=2.0
            )
            if resp.status_code in (200, 201):
                logger.info(f"Event {payload['event_id']} published to backend ({payload['license_plate']['text']}).")
                self._flush_buffer()
                return True
            else:
                logger.warning(f"Backend returned status {resp.status_code}. Buffering event.")
                self.event_buffer.append(payload)
                return False
        except Exception:
            # Backend API unavailable / connection refused - buffer locally
            self.event_buffer.append(payload)
            return False

    def _flush_buffer(self) -> None:
        """Attempt to flush buffered events when connection is restored."""
        if not self.event_buffer:
            return

        logger.info(f"Flushing {len(self.event_buffer)} buffered events to backend...")
        remaining = []
        for payload in self.event_buffer:
            try:
                resp = requests.post(
                    self.backend_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=2.0
                )
                if resp.status_code not in (200, 201):
                    remaining.append(payload)
            except Exception:
                remaining.append(payload)

        self.event_buffer = remaining
