"""
Plate quality assessment + ANPR failure classification (Phase 15B).

The Phase 3 pipeline already gates crops (``ImagePreprocessor.quality_ok``)
and votes across frames. What it did NOT do was say *why* a plate came back
UNKNOWN. This module produces explicit, per-crop quality metrics and maps a
failed read onto ONE reason instead of a bare ``UNKNOWN``:

    ANPR
    UNKNOWN
    Reason: LOW_RESOLUTION
    Confidence: 0.31

All metrics are cheap (single-pass OpenCV ops) so this stays affordable on
the live per-vehicle path.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

import cv2
import numpy as np


# --------------------------------------------------------------------------- #
#  failure reasons
# --------------------------------------------------------------------------- #
class FailureReason:
    NONE = "NONE"                       # a plate WAS recognised
    NO_PLATE = "NO_PLATE"               # no plate-shaped region at all
    LOW_RESOLUTION = "LOW_RESOLUTION"   # crop too small for reliable OCR
    BLUR = "BLUR"                       # motion / focus blur
    OCCLUDED = "OCCLUDED"               # dirt / object / glare covering the plate
    OCR_DISAGREEMENT = "OCR_DISAGREEMENT"   # engines / variants / frames disagree
    INVALID_FORMAT = "INVALID_FORMAT"      # text read but not a valid Indian plate
    LOW_CONFIDENCE = "LOW_CONFIDENCE"      # a candidate exists but below threshold

    ALL = (
        NONE, NO_PLATE, LOW_RESOLUTION, BLUR, OCCLUDED,
        OCR_DISAGREEMENT, INVALID_FORMAT, LOW_CONFIDENCE,
    )


@dataclass
class PlateQuality:
    width: int = 0
    height: int = 0
    resolution_score: float = 0.0      # 0-1, is the crop big enough
    blur_score: float = 0.0            # 0-1, higher = sharper
    contrast_score: float = 0.0        # 0-1
    angle_deg: float = 0.0             # abs deviation from horizontal
    angle_score: float = 0.0           # 0-1, higher = more axis-aligned
    edge_density: float = 0.0          # Canny edge fraction
    occlusion_score: float = 0.0       # 0-1, higher = LESS occluded
    char_estimate: int = 0             # rough count of character-shaped blobs
    overall_score: float = 0.0         # 0-1 weighted

    def to_dict(self) -> Dict[str, Any]:
        return {k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in asdict(self).items()}


# Minimum pixels/character for EasyOCR to be reliable on plates (empirical).
_PX_PER_CHAR = 11
_TYPICAL_CHARS = 10
_MIN_H = 14


class PlateQualityAssessor:
    def __init__(
        self,
        min_plate_height: int = _MIN_H,
        blur_var_floor: float = 45.0,     # Laplacian variance below this -> blurry
        blur_var_good: float = 220.0,
        contrast_floor: float = 16.0,
        contrast_good: float = 55.0,
    ):
        self.min_h = min_plate_height
        self.blur_floor = blur_var_floor
        self.blur_good = blur_var_good
        self.contrast_floor = contrast_floor
        self.contrast_good = contrast_good

    # ------------------------------------------------------------------ #
    def assess(self, plate_crop: Optional[np.ndarray]) -> PlateQuality:
        q = PlateQuality()
        if plate_crop is None or getattr(plate_crop, "size", 0) == 0 or plate_crop.ndim < 2:
            return q
        h, w = plate_crop.shape[:2]
        q.width, q.height = int(w), int(h)
        gray = (cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
                if plate_crop.ndim == 3 else plate_crop.astype(np.uint8))

        # --- resolution ---
        need_w = _PX_PER_CHAR * _TYPICAL_CHARS
        q.resolution_score = float(np.clip(
            0.5 * min(1.0, h / max(self.min_h * 1.6, 1))
            + 0.5 * min(1.0, w / max(need_w, 1)), 0.0, 1.0))

        # --- blur (variance of Laplacian) ---
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        q.blur_score = float(np.clip(
            (lap_var - self.blur_floor) / max(self.blur_good - self.blur_floor, 1e-6), 0.0, 1.0))

        # --- contrast ---
        std = float(gray.std())
        q.contrast_score = float(np.clip(
            (std - self.contrast_floor) / max(self.contrast_good - self.contrast_floor, 1e-6),
            0.0, 1.0))

        # --- angle (dominant text-row orientation) ---
        q.angle_deg = _estimate_skew_deg(gray)
        q.angle_score = float(np.clip(1.0 - abs(q.angle_deg) / 25.0, 0.0, 1.0))

        # --- edges / occlusion / char estimate ---
        edges = cv2.Canny(gray, 60, 180)
        q.edge_density = float(edges.mean() / 255.0)
        q.char_estimate = _estimate_char_blobs(gray)
        # A readable plate has a moderate edge density and several char blobs.
        # Too few edges/blobs -> covered/blank; way too many -> noise/dirt.
        dens_ok = 1.0 - min(1.0, abs(q.edge_density - 0.12) / 0.12)
        blob_ok = min(1.0, q.char_estimate / 6.0)
        q.occlusion_score = float(np.clip(0.5 * dens_ok + 0.5 * blob_ok, 0.0, 1.0))

        q.overall_score = round(float(
            0.28 * q.resolution_score
            + 0.26 * q.blur_score
            + 0.18 * q.contrast_score
            + 0.12 * q.angle_score
            + 0.16 * q.occlusion_score
        ), 4)
        return q

    # ------------------------------------------------------------------ #
    def classify_failure(
        self,
        quality: PlateQuality,
        *,
        located: bool,
        ocr_text: Optional[str],
        normalized_plate: Optional[str],
        format_score: float,
        confidence: float,
        raw_reads: Optional[list] = None,
        conf_threshold: float = 0.5,
        format_threshold: float = 0.45,
    ) -> str:
        """Return ONE FailureReason. ``NONE`` means the read succeeded."""
        plate = (normalized_plate or "").strip().upper()
        if plate and plate != "UNKNOWN" and confidence >= conf_threshold and format_score >= format_threshold:
            return FailureReason.NONE

        if not located:
            return FailureReason.NO_PLATE

        # quality-driven reasons take precedence -- the honest root cause
        if quality.resolution_score < 0.35 or quality.width < _PX_PER_CHAR * 5:
            return FailureReason.LOW_RESOLUTION
        # a near-featureless crop is covered/blank, not merely out of focus
        if (quality.contrast_score < 0.15 and quality.occlusion_score < 0.3) \
                or quality.char_estimate == 0:
            return FailureReason.OCCLUDED
        if quality.blur_score < 0.28:
            return FailureReason.BLUR
        if quality.occlusion_score < 0.32 or quality.char_estimate < 4:
            return FailureReason.OCCLUDED

        # something WAS read -- why is it not a plate?
        if raw_reads and len(set(r for r in raw_reads if r and r != "UNKNOWN")) >= 3 \
                and (not plate or plate == "UNKNOWN"):
            return FailureReason.OCR_DISAGREEMENT
        if ocr_text and ocr_text != "UNKNOWN" and (not plate or plate == "UNKNOWN"
                                                   or format_score < format_threshold):
            return FailureReason.INVALID_FORMAT
        if plate and plate != "UNKNOWN" and confidence < conf_threshold:
            return FailureReason.LOW_CONFIDENCE

        # nothing readable produced from a plausibly-located region
        if not ocr_text or ocr_text == "UNKNOWN":
            return FailureReason.LOW_CONFIDENCE
        return FailureReason.INVALID_FORMAT


# --------------------------------------------------------------------------- #
#  helpers
# --------------------------------------------------------------------------- #
def _estimate_skew_deg(gray: np.ndarray) -> float:
    """Dominant near-horizontal line angle via a coarse Hough transform.
    Returns abs deviation from horizontal in degrees (0 = perfectly level)."""
    try:
        edges = cv2.Canny(gray, 60, 180)
        lines = cv2.HoughLines(edges, 1, np.pi / 180.0, threshold=max(20, gray.shape[1] // 6))
    except cv2.error:
        return 0.0
    if lines is None:
        return 0.0
    angles = []
    for rho_theta in lines[:20]:
        theta = float(rho_theta[0][1])
        deg = math.degrees(theta) - 90.0          # 0 == horizontal edge
        if abs(deg) <= 35.0:
            angles.append(deg)
    if not angles:
        return 0.0
    return round(abs(float(np.median(angles))), 2)


def _estimate_char_blobs(gray: np.ndarray) -> int:
    """Rough count of character strokes via the vertical projection profile
    of the plate's central band: a plate with legible text produces a
    regular run of dark 'ink' columns separated by light gaps."""
    h, w = gray.shape[:2]
    if h < 8 or w < 16:
        return 0
    band = gray[int(h * 0.15):int(h * 0.9), :]
    try:
        _, binv = cv2.threshold(band, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    except cv2.error:
        return 0
    col_ink = binv.mean(axis=0) / 255.0          # fraction of dark pixels per column
    ink = col_ink > 0.18
    # count rising edges (start of an ink run) that are wide enough to be a stroke
    runs = 0
    run_len = 0
    for v in ink:
        if v:
            run_len += 1
        else:
            if 1 <= run_len <= max(3, int(0.55 * h)):
                runs += 1
            run_len = 0
    if 1 <= run_len <= max(3, int(0.55 * h)):
        runs += 1
    return runs
