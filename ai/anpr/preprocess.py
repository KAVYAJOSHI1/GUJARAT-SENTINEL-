import cv2
import numpy as np
import logging
from typing import List

logger = logging.getLogger("ImagePreprocessor")


def _order_quad(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]
    rect[3] = pts[np.argmax(d)]
    return rect

class ImagePreprocessor:
    """
    Image Preprocessor module for license plate character enhancement.
    Applies CLAHE, grayscale conversion, Gaussian blurring, and optimal scaling for OCR.
    """

    def __init__(self, clip_limit: float = 2.5, tile_grid_size: tuple = (8, 8), target_height: int = 48):
        self.clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
        self.target_height = target_height
        # OCR reads best on ~2x the standard height; small crops get upscaled.
        self.ocr_height = target_height * 2

    # ------------------------------------------------------------------ #
    #  quality gate + multi-variant preprocessing (Phase 3)               #
    # ------------------------------------------------------------------ #
    def quality_ok(self, plate_crop: np.ndarray) -> bool:
        """Reject crops too small / too dark / too flat to hold readable text.

        Cheap checks only -- this runs per detected plate on the live path.
        """
        if plate_crop is None or getattr(plate_crop, "size", 0) == 0:
            return False
        if len(plate_crop.shape) < 2:
            return False
        h, w = plate_crop.shape[:2]
        if h < 10 or w < 24 or w / max(h, 1) < 1.3:
            return False
        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY) if plate_crop.ndim == 3 else plate_crop
        if float(gray.std()) < 12.0:          # almost no contrast -> nothing to read
            return False
        m = float(gray.mean())
        if m < 18.0 or m > 245.0:             # crushed black / blown white
            return False
        return True

    def _resize_for_ocr(self, img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        if h == self.ocr_height:
            return img
        scale = self.ocr_height / float(h)
        new_w = int(np.clip(w * scale, 80, 600))
        interp = cv2.INTER_CUBIC if scale >= 1.0 else cv2.INTER_AREA
        return cv2.resize(img, (new_w, self.ocr_height), interpolation=interp)

    # ------------------------------------------------------------------ #
    #  perspective correction (Phase 15B)                                 #
    # ------------------------------------------------------------------ #
    def perspective_correct(self, plate_crop: np.ndarray) -> np.ndarray:
        """Flatten a plate photographed at an angle via a 4-point warp.

        Finds the largest quadrilateral in the crop (the plate outline); if
        it is clearly non-rectangular, warps it to a front-parallel view.
        Returns the ORIGINAL crop unchanged when no good quad is found or the
        quad is already near-rectangular -- pure recall aid, never a
        regression on the (already axis-aligned) common case.
        """
        if plate_crop is None or plate_crop.size == 0 or plate_crop.ndim < 2:
            return plate_crop
        h, w = plate_crop.shape[:2]
        if h < 12 or w < 24:
            return plate_crop
        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY) if plate_crop.ndim == 3 else plate_crop
        try:
            edges = cv2.Canny(cv2.bilateralFilter(gray, 7, 40, 40), 40, 160)
            edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
            cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        except cv2.error:
            return plate_crop
        best_quad = None
        best_area = 0.30 * h * w
        for c in cnts:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.03 * peri, True)
            if len(approx) != 4 or not cv2.isContourConvex(approx):
                continue
            area = cv2.contourArea(approx)
            if area > best_area:
                best_area = area
                best_quad = approx.reshape(4, 2).astype("float32")
        if best_quad is None:
            return plate_crop

        rect = _order_quad(best_quad)
        (tl, tr, br, bl) = rect
        widths = [np.linalg.norm(br - bl), np.linalg.norm(tr - tl)]
        heights = [np.linalg.norm(tr - br), np.linalg.norm(tl - bl)]
        out_w, out_h = int(max(widths)), int(max(heights))
        if out_w < 24 or out_h < 12:
            return plate_crop
        # skip if already near-rectangular (corners agree within ~6%)
        if abs(widths[0] - widths[1]) < 0.06 * out_w and abs(heights[0] - heights[1]) < 0.10 * out_h:
            return plate_crop
        dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], "float32")
        try:
            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(plate_crop, M, (out_w, out_h), flags=cv2.INTER_CUBIC,
                                         borderMode=cv2.BORDER_REPLICATE)
        except cv2.error:
            return plate_crop
        return warped if warped is not None and warped.size else plate_crop

    def variants(self, plate_crop: np.ndarray, max_variants: int = 4) -> List[np.ndarray]:
        """Return a small set of preprocessing variants for the OCR engine to
        try. Empty list => the crop failed the quality gate (=> UNKNOWN).

        1. upscaled colour (kept close to the raw pixels)
        2. grayscale + CLAHE + light denoise  (the classic path)
        3. unsharp-masked (edge/character sharpening)
        4. adaptive threshold (binarised)
        """
        if not self.quality_ok(plate_crop):
            return []

        base = self._resize_for_ocr(plate_crop if plate_crop.ndim == 3
                                    else cv2.cvtColor(plate_crop, cv2.COLOR_GRAY2BGR))
        gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)

        out: List[np.ndarray] = [base]

        clahe = self.clahe.apply(gray)
        clahe = cv2.bilateralFilter(clahe, 5, 40, 40)
        out.append(cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR))

        blur = cv2.GaussianBlur(clahe, (0, 0), 2.0)
        sharp = cv2.addWeighted(clahe, 1.7, blur, -0.7, 0)
        out.append(cv2.cvtColor(sharp, cv2.COLOR_GRAY2BGR))

        thr = cv2.adaptiveThreshold(
            clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, 9
        )
        if thr.mean() < 127:                  # keep dark text on light background
            thr = cv2.bitwise_not(thr)
        out.append(cv2.cvtColor(thr, cv2.COLOR_GRAY2BGR))

        return out[:max_variants]

    def preprocess(self, plate_crop: np.ndarray) -> np.ndarray:
        """
        Enhance image quality of license plate crop for OCR while standardizing dimensions.

        :param plate_crop: BGR or Grayscale crop numpy array
        :return: Preprocessed BGR image array ready for OCR
        """
        if plate_crop is None or plate_crop.size == 0:
            return plate_crop

        h, w = plate_crop.shape[:2]
        if h < 8 or w < 16:
            return plate_crop

        # Standardize crop height for fast, high-accuracy OCR inferencing
        if h != self.target_height:
            scale = self.target_height / float(h)
            new_w = min(250, max(60, int(w * scale)))
            interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
            plate_crop = cv2.resize(plate_crop, (new_w, self.target_height), interpolation=interp)

        # Convert to grayscale
        if len(plate_crop.shape) == 3:
            gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
        else:
            gray = plate_crop.copy()

        # CLAHE (Contrast Limited Adaptive Histogram Equalization)
        equalized = self.clahe.apply(gray)

        # Subtle Gaussian blur to smooth high frequency noise
        blurred = cv2.GaussianBlur(equalized, (3, 3), 0)

        # Convert back to 3-channel BGR image for compatibility with OCR engines
        processed_bgr = cv2.cvtColor(blurred, cv2.COLOR_GRAY2BGR)

        return processed_bgr
