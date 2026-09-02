import os
import cv2
import time
import json
import uuid
import logging
import requests
import numpy as np
from typing import Dict, List, Any, Optional

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
        backend_url: str = "http://localhost:8000/api/v1/events/ai-detection",
        evidence_dir: str = "evidence",
        device: str = "cpu"
    ):
        self.backend_url = backend_url
        self.evidence_dir = evidence_dir

        # Ensure evidence directory exists
        os.makedirs(self.evidence_dir, exist_ok=True)

        logger.info("Initializing SENTINEL AI Pipeline components...")
        self.vehicle_detector = VehicleDetector(device=device)
        self.plate_locator = PlateLocator()
        self.preprocessor = ImagePreprocessor()
        self.ocr_engine = OCREngine()
        self.normalizer = PlateNormalizer()
        self.consensus_engine = MultiFrameConsensus()

        # In-memory buffer for retry on API unreachability
        self.event_buffer: List[Dict[str, Any]] = []

    def process_frame(
        self,
        frame: np.ndarray,
        camera_id: str = "CAM-001",
        frame_timestamp: Optional[str] = None,
        track_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Process a single video stream frame through the entire SENTINEL AI pipeline.

        :param frame: Image frame array (BGR numpy ndarray)
        :param camera_id: Identifier of the camera stream
        :param frame_timestamp: ISO timestamp string or UNIX epoch string
        :param track_ids: Optional list of ByteTrack IDs matching detected vehicles
        :return: List of generated AI Detection Event dictionaries
        """
        if frame is None or frame.size == 0:
            return []

        if frame_timestamp is None:
            frame_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        events: List[Dict[str, Any]] = []

        # Step 1: Vehicle Detection
        detections = self.vehicle_detector.detect(frame)
        if not detections:
            return []

        for idx, det in enumerate(detections):
            vehicle_class = det["class"]
            vehicle_conf = det["confidence"]
            vehicle_bbox = det["bbox"]
            track_id = track_ids[idx] if (track_ids and idx < len(track_ids)) else idx + 1

            # Crop vehicle region
            vehicle_crop = self.vehicle_detector.crop_vehicle(frame, vehicle_bbox)

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
            ocr_res = self.ocr_engine.extract_text(enhanced_plate)
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
                "camera_id": camera_id,
                "vehicle": {
                    "class": vehicle_class,
                    "confidence": vehicle_conf,
                    "bbox": vehicle_bbox,
                    "track_id": track_id
                },
                "license_plate": {
                    "plate_number": final_plate,
                    "confidence": final_conf,
                    "bbox": abs_plate_bbox,
                    "raw_text": raw_text,
                    "consensus_applied": len(consensus_res["raw_reads"]) > 1,
                    "raw_reads": consensus_res["raw_reads"]
                },
                "evidence": {
                    "frame_snapshot_path": snapshot_path,
                    "plate_crop_path": crop_path
                }
            }

            events.append(event_payload)

            # Step 9: Dispatch HTTP POST Payload to backend API
            self._dispatch_event(event_payload)

        return events

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
                logger.info(f"Event {payload['event_id']} published to backend ({payload['license_plate']['plate_number']}).")
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
