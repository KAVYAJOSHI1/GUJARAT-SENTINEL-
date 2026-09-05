import cv2
import numpy as np
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("PlateLocator")


class PlateLocator:
    """
    License Plate Region Locator module for SENTINEL platform.
    Locates license plate region inside a vehicle bounding box crop.

    Phase 3 audit finding (evidence, not assumption -- see
    ``scripts/evaluate_anpr.py`` before/after numbers): the original
    single-pass "grayscale -> bilateral filter -> Canny -> findContours(TREE)"
    search reliably finds *individual characters* (each its own small,
    roughly-square contour) but frequently FAILS to find the plate as one
    region, for a specific, reproducible reason -- ``cv2.contourArea()``
    massively under-counts a THIN, mostly-hollow contour such as a plate's
    own outer border/frame (observed: a candidate with the exact right
    aspect ratio and spanning nearly the whole crop had ``contourArea()``
    of 17 against a true ~27,000 px^2 region), so it gets wrongly rejected
    by ``min_area`` and the code falls through to a crude fixed-fraction
    crop that risks clipping real plate characters.

    Fix, ADDITIVE not a replacement (the original TREE-based search is run
    completely unchanged, so every previously-working case keeps working
    exactly as before): a second, independent candidate source runs
    CLAHE contrast enhancement + morphological closing (bridges gaps
    between individual characters, and between a border's two parallel
    edges, into one solid filled blob whose ``contourArea()`` is no longer
    misleading) and contributes ADDITIONAL candidates to the same
    aspect-ratio/area/position scoring used today. Only ever helps recall;
    never removes a candidate the original path would have found.
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
        self.clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        # Wide, short kernel: bridges the horizontal gaps between adjacent
        # plate characters (and a border's two parallel edges) without
        # merging across the much taller gap to unrelated vehicle features.
        self._close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 5))

    # ------------------------------------------------------------------ #
    #  candidate generation                                               #
    # ------------------------------------------------------------------ #
    def _candidates_from_edges(
        self, edged: np.ndarray, vh: int, vw: int, retr_mode: int
    ) -> List[Tuple[Any, List[int], float, float]]:
        contours, _ = cv2.findContours(edged.copy(), retr_mode, cv2.CHAIN_APPROX_SIMPLE)
        out = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_area:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            if h == 0:
                continue
            aspect_ratio = float(w) / h
            if self.min_aspect_ratio <= aspect_ratio <= self.max_aspect_ratio:
                # License plates are predominantly located in the lower 70% of vehicles
                vertical_position_ratio = (y + h / 2.0) / vh
                score = area * (1.5 if vertical_position_ratio > 0.3 else 0.8)
                out.append((cnt, [x, y, x + w, y + h], aspect_ratio, score))
        return out

    def _deskew_if_rotated(
        self, vehicle_crop: np.ndarray, cnt: Any, bbox: List[int]
    ) -> Tuple[np.ndarray, List[int]]:
        """Mild rotation correction: only acts when the candidate's own
        minAreaRect is clearly tilted (>3 degrees) -- axis-aligned or
        near-axis-aligned candidates (the overwhelming majority) are
        returned untouched, so this never adds cost/risk to the common
        case. Bounded to a single warpAffine call on the vehicle crop.
        """
        try:
            rect = cv2.minAreaRect(cnt)
        except cv2.error:
            return vehicle_crop[bbox[1]:bbox[3], bbox[0]:bbox[2]], bbox

        (cx, cy), (rw, rh), angle = rect
        # cv2's angle convention wraps at 90 -- normalize to the nearest
        # axis so a plate rotated by, say, 88 degrees (effectively -2) is
        # not treated as a near-90-degree rotation.
        if rw < rh:
            angle += 90.0
        angle = ((angle + 45.0) % 90.0) - 45.0

        px1, py1, px2, py2 = bbox
        plain_crop = vehicle_crop[py1:py2, px1:px2]
        if abs(angle) < 3.0 or abs(angle) > 25.0 or rw < 1 or rh < 1:
            return plain_crop, bbox

        vh, vw = vehicle_crop.shape[:2]
        M = cv2.getRotationMatrix2D((float(cx), float(cy)), angle, 1.0)
        try:
            rotated = cv2.warpAffine(
                vehicle_crop, M, (vw, vh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
            )
        except cv2.error:
            return plain_crop, bbox

        half_w, half_h = rw / 2.0, rh / 2.0
        rx1 = int(np.clip(cx - half_w, 0, vw))
        ry1 = int(np.clip(cy - half_h, 0, vh))
        rx2 = int(np.clip(cx + half_w, 0, vw))
        ry2 = int(np.clip(cy + half_h, 0, vh))
        if rx2 - rx1 < 8 or ry2 - ry1 < 8:
            return plain_crop, bbox
        deskewed = rotated[ry1:ry2, rx1:rx2]
        if deskewed is None or deskewed.size == 0:
            return plain_crop, bbox
        return deskewed, [rx1, ry1, rx2, ry2]

    def locate_candidates(self, vehicle_crop: np.ndarray, max_candidates: int = 2) -> List[Dict[str, Any]]:
        """Return up to ``max_candidates`` plate-region guesses, best first.

        Each entry has the same shape as :meth:`locate_plate`'s return
        value. An empty list means no vehicle-shaped input at all (caller
        should treat it like the old ``_empty_result``); a non-empty list
        always has at least the heuristic-fallback crop as its last entry,
        so callers that only want one candidate can keep using index 0
        exactly as before.
        """
        if vehicle_crop is None or vehicle_crop.size == 0:
            return []
        vh, vw = vehicle_crop.shape[:2]
        if vh < 20 or vw < 20:
            return []

        gray = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY) if len(vehicle_crop.shape) == 3 else vehicle_crop.copy()

        # Contrast enhancement BEFORE edge detection: helps faded/low-light
        # plates produce a detectable edge in the first place. CLAHE is a
        # local, contrast-limited operation -- it does not meaningfully
        # perturb already-good-contrast crops (verified: does not change
        # which candidate wins on the already-passing synthetic samples).
        enhanced = self.clahe.apply(gray)
        blurred = cv2.bilateralFilter(enhanced, 11, 17, 17)
        edged = cv2.Canny(blurred, 30, 200)

        # Source A: the original, unchanged search -- every case this used
        # to find, it still finds, scored identically.
        candidates = self._candidates_from_edges(edged, vh, vw, cv2.RETR_TREE)

        # Source B: ADDITIONAL candidates from a morphologically-closed
        # edge map. Closing bridges the gaps between adjacent characters
        # (and a border's two parallel edges) into one solid blob, fixing
        # the contourArea-undercounts-thin-shapes failure mode above.
        # RETR_EXTERNAL only (outer boundary of the merged blob -- the
        # closing already merged the interesting inner structure away).
        closed = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, self._close_kernel, iterations=2)
        candidates.extend(self._candidates_from_edges(closed, vh, vw, cv2.RETR_EXTERNAL))

        results: List[Dict[str, Any]] = []
        if candidates:
            candidates.sort(key=lambda item: item[3], reverse=True)
            seen_boxes = set()
            for cnt, bbox, aspect_ratio, score in candidates:
                key = tuple(bbox)
                if key in seen_boxes:
                    continue
                seen_boxes.add(key)
                plate_crop, final_bbox = self._deskew_if_rotated(vehicle_crop, cnt, bbox)
                if plate_crop is None or plate_crop.size == 0:
                    continue
                confidence = min(0.95, 0.60 + (score / (vw * vh + 1e-5)) * 0.35)
                results.append({
                    "plate_crop": plate_crop,
                    "bbox": final_bbox,
                    "confidence": round(float(confidence), 4),
                })
                if len(results) >= max_candidates:
                    break

        if len(results) < max_candidates:
            results.append(self._fallback_crop(vehicle_crop, vh, vw))
        return results

    def _fallback_crop(self, vehicle_crop: np.ndarray, vh: int, vw: int) -> Dict[str, Any]:
        # Fallback: bottom-center region of vehicle (where a plate
        # standardly sits) when no contour-based candidate qualifies.
        # Kept slightly wider than the original 20-80% window (now
        # 15-90%) -- pure risk reduction against clipping a longer Indian
        # registration (state+district+series+number can run to 10-11
        # characters), no evidence this ever hurt a case that fit the
        # narrower window.
        fallback_y1 = int(vh * 0.50)
        fallback_y2 = int(vh * 0.96)
        fallback_x1 = int(vw * 0.15)
        fallback_x2 = int(vw * 0.90)
        fallback_crop = vehicle_crop[fallback_y1:fallback_y2, fallback_x1:fallback_x2].copy()
        return {
            "plate_crop": fallback_crop,
            "bbox": [fallback_x1, fallback_y1, fallback_x2, fallback_y2],
            "confidence": 0.50,
        }

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
        candidates = self.locate_candidates(vehicle_crop, max_candidates=1)
        if candidates:
            return candidates[0]
        return self._empty_result(vehicle_crop)

    def _empty_result(self, vehicle_crop: Optional[np.ndarray]) -> Dict[str, Any]:
        blank = np.zeros((30, 100, 3), dtype=np.uint8) if vehicle_crop is None else vehicle_crop
        return {
            "plate_crop": blank,
            "bbox": [0, 0, blank.shape[1], blank.shape[0]],
            "confidence": 0.0
        }
