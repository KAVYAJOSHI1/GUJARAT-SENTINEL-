"""
Phase 15B -- plate quality assessment + ANPR failure classification.

Covers: quality metrics on good / tiny / blurry / blank crops, the failure
reason mapping (NO_PLATE / LOW_RESOLUTION / BLUR / OCCLUDED /
OCR_DISAGREEMENT / INVALID_FORMAT / LOW_CONFIDENCE / NONE), and the
perspective-correction recall aid.
"""
import unittest

import cv2
import numpy as np

from ai.anpr.quality import FailureReason, PlateQualityAssessor
from ai.anpr.preprocess import ImagePreprocessor


def _plate(text="GJ18TC0450", w=430, h=110, blur=0):
    img = np.full((h, w, 3), 235, np.uint8)
    cv2.rectangle(img, (4, 4), (w - 5, h - 5), (10, 10, 10), 3)
    cv2.putText(img, text, (14, int(h * 0.72)), cv2.FONT_HERSHEY_SIMPLEX,
                h / 55.0, (0, 0, 0), max(2, h // 30), cv2.LINE_AA)
    if blur:
        img = cv2.GaussianBlur(img, (0, 0), blur)
    return img


class TestQualityMetrics(unittest.TestCase):
    def setUp(self):
        self.qa = PlateQualityAssessor()

    def test_good_plate_scores_high(self):
        q = self.qa.assess(_plate())
        self.assertGreater(q.resolution_score, 0.7)
        self.assertGreater(q.blur_score, 0.4)
        self.assertGreater(q.contrast_score, 0.5)
        self.assertGreaterEqual(q.char_estimate, 5)
        self.assertGreater(q.overall_score, 0.55)

    def test_empty_or_tiny_is_zero(self):
        self.assertEqual(self.qa.assess(None).overall_score, 0.0)
        self.assertEqual(self.qa.assess(np.zeros((0, 0, 3), np.uint8)).overall_score, 0.0)
        tiny = self.qa.assess(_plate(w=40, h=10))
        self.assertLess(tiny.resolution_score, 0.5)

    def test_blur_lowers_blur_score(self):
        sharp = self.qa.assess(_plate())
        blurry = self.qa.assess(_plate(blur=3.5))
        self.assertLess(blurry.blur_score, sharp.blur_score)
        self.assertLess(blurry.blur_score, 0.35)

    def test_blank_crop_reads_as_occluded_quality(self):
        blank = np.full((90, 300, 3), 128, np.uint8)
        q = self.qa.assess(blank)
        self.assertLess(q.occlusion_score, 0.5)
        self.assertLess(q.contrast_score, 0.2)


class TestFailureClassification(unittest.TestCase):
    def setUp(self):
        self.qa = PlateQualityAssessor()

    def _q(self, crop):
        return self.qa.assess(crop)

    def test_success_is_none(self):
        r = self.qa.classify_failure(
            self._q(_plate()), located=True, ocr_text="GJ 18 TC 0450",
            normalized_plate="GJ18TC0450", format_score=0.95, confidence=0.9)
        self.assertEqual(r, FailureReason.NONE)

    def test_no_plate_when_not_located(self):
        r = self.qa.classify_failure(
            self._q(_plate()), located=False, ocr_text=None,
            normalized_plate=None, format_score=0.0, confidence=0.0)
        self.assertEqual(r, FailureReason.NO_PLATE)

    def test_low_resolution(self):
        r = self.qa.classify_failure(
            self._q(_plate(w=44, h=12)), located=True, ocr_text=None,
            normalized_plate=None, format_score=0.0, confidence=0.0)
        self.assertEqual(r, FailureReason.LOW_RESOLUTION)

    def test_blur(self):
        r = self.qa.classify_failure(
            self._q(_plate(blur=4.5)), located=True, ocr_text=None,
            normalized_plate=None, format_score=0.0, confidence=0.1)
        self.assertEqual(r, FailureReason.BLUR)

    def test_occluded_on_blank(self):
        blank = np.full((90, 300, 3), 120, np.uint8)
        r = self.qa.classify_failure(
            self._q(blank), located=True, ocr_text=None,
            normalized_plate=None, format_score=0.0, confidence=0.0)
        self.assertEqual(r, FailureReason.OCCLUDED)

    def test_ocr_disagreement(self):
        r = self.qa.classify_failure(
            self._q(_plate()), located=True, ocr_text="GJ18TC0450",
            normalized_plate=None, format_score=0.2, confidence=0.4,
            raw_reads=["GJ18TC0450", "GJ18TC04S0", "GJ1BTC0450", "GJI8TC0450"])
        self.assertEqual(r, FailureReason.OCR_DISAGREEMENT)

    def test_invalid_format(self):
        r = self.qa.classify_failure(
            self._q(_plate()), located=True, ocr_text="HELLO WORLD",
            normalized_plate=None, format_score=0.1, confidence=0.6,
            raw_reads=["HELLO WORLD"])
        self.assertEqual(r, FailureReason.INVALID_FORMAT)

    def test_low_confidence(self):
        r = self.qa.classify_failure(
            self._q(_plate()), located=True, ocr_text="GJ18TC0450",
            normalized_plate="GJ18TC0450", format_score=0.9, confidence=0.33)
        self.assertEqual(r, FailureReason.LOW_CONFIDENCE)


class TestPerspectiveCorrection(unittest.TestCase):
    def test_perspective_correct_is_safe_on_axis_aligned(self):
        pp = ImagePreprocessor()
        crop = _plate()
        out = pp.perspective_correct(crop)
        self.assertIsNotNone(out)
        self.assertGreater(out.size, 0)

    def test_perspective_correct_handles_tiny_input(self):
        pp = ImagePreprocessor()
        out = pp.perspective_correct(np.zeros((6, 6, 3), np.uint8))
        self.assertEqual(out.shape, (6, 6, 3))


if __name__ == "__main__":
    unittest.main()
