import cv2
import numpy as np
import logging
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger("PlateLocator")

class PlateLocator:
    """
    License Plate Region Locator module for SENTINEL platform.
    Locates license plate region inside a vehicle bounding box crop.
    """

    def __init__(
        self,
        min_aspect_ratio: float = 2.0,
        max_aspect_ratio: float = 6.0,
        min_area: int = 400
    ):
        self.min_aspect_ratio = min_aspect_ratio
        self.max_aspect_ratio = max_aspect_ratio
        self.min_area = min_area

    def locate_plate(self, vehicle_crop: np.ndarray) -> Dict[str, Any]:
        """
        Locate license plate inside vehicle image crop.

        :param vehicle_crop: Numpy array image (BGR or Grayscale) of detected vehicle
        :return: Dict containing:
                 {
                   "plate_crop": np.ndarray,
                   "bbox": [px1, py1, px2, py2], # relative to vehicle_crop
                   "confidence": float
                 }
        """
        if vehicle_crop is None or vehicle_crop.size == 0:
            return self._empty_result(vehicle_crop)

        vh, vw = vehicle_crop.shape[:2]
        if vh < 20 or vw < 20:
            return self._empty_result(vehicle_crop)

        # Convert to grayscale if BGR
        if len(vehicle_crop.shape) == 3:
            gray = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY)
        else:
            gray = vehicle_crop.copy()

        # Bilateral filter to reduce noise while preserving edges
        blurred = cv2.bilateralFilter(gray, 11, 17, 17)
        # Edge detection
        edged = cv2.Canny(blurred, 30, 200)

        # Find contours
        contours, _ = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_area:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            aspect_ratio = float(w) / h

            if self.min_aspect_ratio <= aspect_ratio <= self.max_aspect_ratio:
                # License plates are predominantly located in the lower 70% of vehicles
                vertical_position_ratio = (y + h / 2.0) / vh
                score = area * (1.5 if vertical_position_ratio > 0.3 else 0.8)
                candidates.append((cnt, [x, y, x + w, y + h], aspect_ratio, score))

        if candidates:
            # Pick candidate with highest heuristic score
            candidates.sort(key=lambda item: item[3], reverse=True)
            best_cnt, bbox, aspect_ratio, score = candidates[0]
            px1, py1, px2, py2 = bbox
            plate_crop = vehicle_crop[py1:py2, px1:px2].copy()
            confidence = min(0.95, 0.60 + (score / (vw * vh + 1e-5)) * 0.35)

            return {
                "plate_crop": plate_crop,
                "bbox": [px1, py1, px2, py2],
                "confidence": round(float(confidence), 4)
            }

        # Fallback: Extract bottom center region of vehicle (where plate standard is)
        fallback_y1 = int(vh * 0.50)
        fallback_y2 = int(vh * 0.95)
        fallback_x1 = int(vw * 0.20)
        fallback_x2 = int(vw * 0.80)

        fallback_crop = vehicle_crop[fallback_y1:fallback_y2, fallback_x1:fallback_x2].copy()
        
        return {
            "plate_crop": fallback_crop,
            "bbox": [fallback_x1, fallback_y1, fallback_x2, fallback_y2],
            "confidence": 0.50
        }

    def _empty_result(self, vehicle_crop: Optional[np.ndarray]) -> Dict[str, Any]:
        blank = np.zeros((30, 100, 3), dtype=np.uint8) if vehicle_crop is None else vehicle_crop
        return {
            "plate_crop": blank,
            "bbox": [0, 0, blank.shape[1], blank.shape[0]],
            "confidence": 0.0
        }
