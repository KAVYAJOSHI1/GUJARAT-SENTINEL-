import os
import cv2
import time
import json
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

logger = logging.getLogger("AIPipeline")

class AIPipeline:
    """
    End-to-End SENTINEL AI Computer Vision Analytics Pipeline.
    Processes video frames, detects vehicles, crops license plates, applies preprocessing,
    runs OCR, normalizes text, computes multi-frame consensus, saves evidence, and dispatches JSON events.
    """

    def __init__(
        self,
        backend_url: Optional[str] = None,
        evidence_dir: Optional[str] = None,
        confidence_threshold: Optional[float] = None,
        device: str = "cpu"
    ):
        """
        Initialize AI Pipeline with configuration parameters or environment variable overrides.
        """
        self.backend_url = backend_url or os.getenv(
            "SENTINEL_BACKEND_URL", "http://localhost:8000/api/v1/events/ai-detection"
        )
        self.evidence_dir = evidence_dir or os.getenv("SENTINEL_EVIDENCE_DIR", "evidence")

        conf_env = os.getenv("CONFIDENCE_THRESHOLD") or os.getenv("SENTINEL_CONFIDENCE_THRESHOLD")
        if confidence_threshold is not None:
            self.confidence_threshold = confidence_threshold
        elif conf_env:
            try:
                self.confidence_threshold = float(conf_env)
            except ValueError:
                self.confidence_threshold = 0.50
        else:
            self.confidence_threshold = 0.50

        # Ensure evidence directory exists
        os.makedirs(self.evidence_dir, exist_ok=True)

        logger.info(f"Initializing SENTINEL AI Pipeline components (conf threshold: {self.confidence_threshold})...")
        self.vehicle_detector = VehicleDetector(conf_threshold=self.confidence_threshold, device=device)
        self.plate_locator = PlateLocator()
        self.preprocessor = ImagePreprocessor()
        self.ocr_engine = OCREngine()
        self.normalizer = PlateNormalizer()
        self.consensus_engine = MultiFrameConsensus()

        # In-memory buffer for retry on API unreachability
        self.event_buffer: List[Dict[str, Any]] = []

        # Performance & Benchmark Statistics
        self.stats = {
            "total_frames": 0,
            "processed_frames": 0,
            "total_vehicles": 0,
            "total_detections": 0,
            "vehicle_detection_time_ms": 0.0,
            "ocr_time_ms": 0.0,
            "total_pipeline_time_ms": 0.0
        }

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
        :param camera_id: Identifier of the camera stream
        :param frame_timestamp: ISO timestamp string or UNIX epoch string
        :param pts: Stream presentation timestamp (PTS)
        :param track_ids: Optional list of ByteTrack IDs matching detected vehicles
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
            t_total = (time.time() - t_start) * 1000.0
            self.stats["total_pipeline_time_ms"] += t_total
            return []

        self.stats["total_vehicles"] += len(detections)

        for idx, det in enumerate(detections):
            vehicle_class = det["class"]
            vehicle_conf = det["confidence"]
            vehicle_bbox = det["bbox"]
            track_id = track_ids[idx] if (track_ids and idx < len(track_ids)) else idx + 1

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

            # Step 3: Image Preprocessing
            enhanced_plate = self.preprocessor.preprocess(plate_crop)

            # Step 4: OCR Engine
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
                confidence=ocr_conf
            )
            final_plate = consensus_res["consensus_plate"]
            final_conf = consensus_res["confidence"]

            # Step 7: Save Evidence Snapshots
            ts_str = str(int(time.time()))
            snapshot_filename = f"{camera_id}_{ts_str}_tr{track_id}_{final_plate}.jpg"
            crop_filename = f"{camera_id}_{ts_str}_tr{track_id}_{final_plate}_crop.jpg"

            snapshot_path = os.path.join(self.evidence_dir, snapshot_filename)
            crop_path = os.path.join(self.evidence_dir, crop_filename)

            try:
                cv2.imwrite(snapshot_path, frame)
                cv2.imwrite(crop_path, enhanced_plate)
            except Exception as e:
                logger.error(f"Failed to write evidence files: {e}")

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
                    "text": final_plate,
                    "plate_number": final_plate,
                    "confidence": final_conf,
                    "bbox": abs_plate_bbox,
                    "raw_text": raw_text,
                    "consensus_applied": len(consensus_res["raw_reads"]) > 1,
                    "raw_reads": consensus_res["raw_reads"]
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
