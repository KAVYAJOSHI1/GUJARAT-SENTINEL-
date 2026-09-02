import cv2
import numpy as np
import logging

logger = logging.getLogger("ImagePreprocessor")

class ImagePreprocessor:
    """
    Image Preprocessor module for license plate character enhancement.
    Applies CLAHE, grayscale conversion, Gaussian blurring, and optimal scaling for OCR.
    """

    def __init__(self, clip_limit: float = 2.5, tile_grid_size: tuple = (8, 8), target_height: int = 48):
        self.clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
        self.target_height = target_height

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
