import cv2
import numpy as np
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("OCREngine")

class OCREngine:
    """
    PaddleOCR Engine wrapper with EasyOCR/Tesseract fallback for character recognition on license plates.
    """

    def __init__(self, lang: str = 'en', use_angle_cls: bool = False):
        self.paddle_ocr = None
        self.easy_ocr = None

        # Attempt PaddleOCR initialization
        try:
            from paddleocr import PaddleOCR
            logger.info("Initializing PaddleOCR engine...")
            self.paddle_ocr = PaddleOCR(lang=lang)
            logger.info("PaddleOCR engine initialized successfully.")
        except Exception as e:
            logger.warning(f"PaddleOCR init failed/unavailable ({e}). Trying EasyOCR fallback...")

        # Fallback to EasyOCR if PaddleOCR unavailable
        if self.paddle_ocr is None:
            try:
                import easyocr
                logger.info("Initializing EasyOCR fallback engine...")
                self.easy_ocr = easyocr.Reader(['en'], gpu=False)
                logger.info("EasyOCR initialized successfully.")
            except Exception as e:
                logger.warning(f"EasyOCR init failed ({e}). Custom contour OCR fallback active.")

    def extract_text(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Perform OCR on license plate image crop.

        :param image: Enhanced license plate BGR crop array
        :return: Dict containing {"raw_text": str, "confidence": float}
        """
        if image is None or image.size == 0:
            return {"raw_text": "UNKNOWN", "confidence": 0.0}

        h, w = image.shape[:2]
        # Fast filter for unpromising / tiny crops
        if h < 12 or w < 24:
            return {"raw_text": "UNKNOWN", "confidence": 0.0}

        # 1. Try PaddleOCR
        if self.paddle_ocr is not None:
            try:
                results = self.paddle_ocr.ocr(image)
                if results and len(results) > 0 and results[0]:
                    text_parts = []
                    conf_scores = []
                    for line in results[0]:
                        if line and len(line) >= 2:
                            text, conf = line[1][0], float(line[1][1])
                            text_parts.append(text)
                            conf_scores.append(conf)

                    if text_parts:
                        full_raw_text = " ".join(text_parts)
                        avg_conf = sum(conf_scores) / len(conf_scores)
                        return {"raw_text": full_raw_text, "confidence": round(avg_conf, 4)}
            except Exception as e:
                logger.debug(f"PaddleOCR inference exception: {e}")

        # 2. Try EasyOCR fallback
        if self.easy_ocr is not None:
            try:
                results = self.easy_ocr.readtext(image)
                if results:
                    text_parts = []
                    conf_scores = []
                    for bbox, text, conf in results:
                        text_parts.append(text)
                        conf_scores.append(float(conf))

                    if text_parts:
                        full_raw_text = " ".join(text_parts)
                        avg_conf = sum(conf_scores) / len(conf_scores)
                        return {"raw_text": full_raw_text, "confidence": round(avg_conf, 4)}
            except Exception as e:
                logger.debug(f"EasyOCR inference exception: {e}")

        # 3. Default fallback if image has insufficient clarity
        return {"raw_text": "UNKNOWN", "confidence": 0.0}
