import cv2
import numpy as np
import logging

logger = logging.getLogger("ImagePreprocessor")

class ImagePreprocessor:
    """
    Image Preprocessor module for license plate character enhancement.
    Applies CLAHE, grayscale conversion, Gaussian blurring, and contrast stretching.
    """

    def __init__(self, clip_limit: float = 3.0, tile_grid_size: tuple = (8, 8)):
        self.clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)

    def preprocess(self, plate_crop: np.ndarray) -> np.ndarray:
        """
        Enhance image quality of license plate crop for OCR.

        :param plate_crop: BGR or Grayscale crop numpy array
        :return: Preprocessed BGR or Grayscale image array ready for OCR
        """
        if plate_crop is None or plate_crop.size == 0:
            return plate_crop

        h, w = plate_crop.shape[:2]

        # Upscale small crops to ensure minimum height for OCR recognition
        min_height = 80
        if h < min_height:
            scale = min_height / float(h)
            new_w = int(w * scale)
            new_h = min_height
            plate_crop = cv2.resize(plate_crop, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

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
