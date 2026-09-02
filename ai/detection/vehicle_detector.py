import os
import logging
from typing import List, Dict, Any, Union, Optional
import numpy as np
from ultralytics import YOLO

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VehicleDetector")

# COCO dataset class index mapping for vehicles
DEFAULT_VEHICLE_CLASSES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck"
}

class VehicleDetector:
    """
    YOLOv8-based Vehicle Detector module for SENTINEL platform.
    Detects vehicles (car, motorcycle, bus, truck, auto-rickshaw) in video frames.
    """

    def __init__(
        self,
        model_path: str = "ai/weights/yolov8n.pt",
        conf_threshold: float = 0.50,
        device: str = "cpu"
    ):
        """
        Initialize VehicleDetector with pretrained YOLO model.

        :param model_path: Path to YOLO weights file (.pt)
        :param conf_threshold: Minimum confidence threshold (default 0.50)
        :param device: Hardware device ('cpu' or 'cuda')
        """
        self.conf_threshold = conf_threshold
        self.device = device
        
        # Fallback path if custom weights folder missing
        if not os.path.exists(model_path) and os.path.exists("yolov8n.pt"):
            model_path = "yolov8n.pt"

        logger.info(f"Loading YOLOv8 Vehicle Detector from '{model_path}' on device '{device}'...")
        try:
            self.model = YOLO(model_path)
            logger.info("YOLOv8 Vehicle Detector loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load model from {model_path}: {e}")
            raise e

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Run vehicle detection on a single frame (OpenCV BGR or RGB array).

        :param frame: Input image frame as numpy array (H, W, C)
        :return: List of detection dictionaries:
                 [
                   {
                     "class": "car",
                     "confidence": 0.92,
                     "bbox": [x1, y1, x2, y2]
                   }
                 ]
        """
        if frame is None or frame.size == 0:
            logger.warning("Empty frame passed to VehicleDetector.")
            return []

        results = self.model(frame, conf=self.conf_threshold, device=self.device, verbose=False)
        detections: List[Dict[str, Any]] = []

        if not results or len(results) == 0:
            return detections

        result = results[0]
        boxes = result.boxes

        if boxes is None or len(boxes) == 0:
            return detections

        for box in boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())

            # Check if detected object is a target vehicle class
            if cls_id in DEFAULT_VEHICLE_CLASSES:
                vehicle_class = DEFAULT_VEHICLE_CLASSES[cls_id]
                xyxy = box.xyxy[0].cpu().numpy().astype(int).tolist()
                
                # Format bounding box [x1, y1, x2, y2]
                x1, y1, x2, y2 = xyxy[0], xyxy[1], xyxy[2], xyxy[3]

                # Ensure non-negative bounds within image frame dimensions
                h, w = frame.shape[:2]
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)

                detections.append({
                    "class": vehicle_class,
                    "confidence": round(conf, 4),
                    "bbox": [x1, y1, x2, y2]
                })

        return detections

    def crop_vehicle(self, frame: np.ndarray, bbox: List[int]) -> np.ndarray:
        """
        Crop vehicle region from frame given bounding box [x1, y1, x2, y2].

        :param frame: Full image frame
        :param bbox: [x1, y1, x2, y2]
        :return: Cropped numpy array frame
        """
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        return frame[y1:y2, x1:x2].copy()
