"""
Tests for ai/ocr/ocr_engine.OCREngine (PHASE 1 — OCR fix).

Covers:
  * successful OCR on a rendered plate  (real EasyOCR, skipped if unavailable)
  * inference-failure -> the *other* backend is actually reached
  * both backends dead / crops too small -> "UNKNOWN"
  * OCR output -> PlateNormalizer still yields the canonical plate string
"""
import unittest

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

from ai.anpr.preprocess import ImagePreprocessor
from ai.ocr.normalizer import PlateNormalizer
from ai.ocr.ocr_engine import OCREngine


def _render_plate(text: str, w: int = 560, h: int = 170) -> np.ndarray:
    img = np.full((h, w, 3), 255, np.uint8)
    font = cv2.FONT_HERSHEY_DUPLEX
    (tw, th), _ = cv2.getTextSize(text, font, 3.0, 7)
    cv2.putText(img, text, ((w - tw) // 2, (h + th) // 2), font, 3.0, (0, 0, 0), 7, cv2.LINE_AA)
    return img


def _easyocr_available() -> bool:
    try:
        eng = OCREngine(engine="easyocr")
        eng._ensure_init()
        return eng._easy is not None
    except Exception:
        return False


class TestOCRSuccess(unittest.TestCase):
    @unittest.skipUnless(cv2 is not None and _easyocr_available(),
                         "EasyOCR / OpenCV not available in this environment")
    def test_reads_a_clear_plate(self):
        eng = OCREngine(engine="easyocr")
        res = eng.extract_text(_render_plate("GJ01AB1234"))
        self.assertIn("raw_text", res)
        self.assertIn("confidence", res)
        # Real OCR on a synthetic (out-of-distribution) font may misread some
        # letters (G->5, B->8, ...). What must hold: it produces REAL text, not
        # "UNKNOWN", with a sane confidence, and the digit run reads through.
        self.assertNotEqual(res["raw_text"], "UNKNOWN", "clear synthetic plate must be read")
        self.assertGreater(res["confidence"], 0.3)
        normalized = PlateNormalizer().normalize(res["raw_text"])
        self.assertGreaterEqual(len(normalized), 8)
        self.assertTrue(normalized.endswith("1234"), f"digit run lost: {normalized!r}")
        self.assertEqual(eng.active_engine, "easyocr")


class TestOCRFailureAndFallback(unittest.TestCase):
    def test_primary_inference_crash_falls_back_to_other_backend(self):
        """PaddleOCR-primary that crashes at inference must hand off to EasyOCR."""
        eng = OCREngine(engine="paddleocr")
        eng._initialised = True  # skip real init

        class _Boom:
            def predict(self, *_a, **_k):
                raise NotImplementedError("ConvertPirAttribute2RuntimeAttribute not support")
            def ocr(self, *_a, **_k):
                raise NotImplementedError("ConvertPirAttribute2RuntimeAttribute not support")

        class _FakeEasy:
            def readtext(self, *_a, **_k):
                return [([[0, 0], [10, 0], [10, 10], [0, 10]], "GJ 05 XX 7821", 0.88)]

        eng._paddle = _Boom()
        eng._easy = _FakeEasy()
        eng._recompute_active()

        res = eng.extract_text(np.zeros((60, 200, 3), np.uint8))
        self.assertEqual(PlateNormalizer().normalize(res["raw_text"]), "GJ05XX7821")
        self.assertAlmostEqual(res["confidence"], 0.88, places=4)
        # the crashing backend must be permanently disabled
        self.assertIsNone(eng._paddle)
        self.assertTrue(eng._paddle_disabled)
        self.assertEqual(eng.active_engine, "easyocr")

    def test_all_backends_dead_returns_unknown(self):
        eng = OCREngine()
        eng._initialised = True
        eng._easy = None
        eng._paddle = None
        eng._recompute_active()
        res = eng.extract_text(np.zeros((60, 200, 3), np.uint8))
        self.assertEqual(res, {"raw_text": "UNKNOWN", "confidence": 0.0})
        self.assertEqual(eng.active_engine, "none")

    def test_easyocr_crash_is_swallowed_and_disabled(self):
        eng = OCREngine(engine="easyocr")
        eng._initialised = True

        class _BoomEasy:
            def readtext(self, *_a, **_k):
                raise RuntimeError("cuda / model corrupted")

        eng._easy = _BoomEasy()
        eng._paddle = None
        eng._recompute_active()
        res = eng.extract_text(np.zeros((60, 200, 3), np.uint8))
        self.assertEqual(res["raw_text"], "UNKNOWN")
        self.assertTrue(eng._easy_disabled)


class TestOCRUnknownGuards(unittest.TestCase):
    def test_none_and_empty(self):
        eng = OCREngine()
        self.assertEqual(eng.extract_text(None)["raw_text"], "UNKNOWN")
        self.assertEqual(eng.extract_text(np.array([]))["raw_text"], "UNKNOWN")

    def test_tiny_crop_short_circuits_before_init(self):
        eng = OCREngine()
        res = eng.extract_text(np.zeros((5, 5, 3), np.uint8))
        self.assertEqual(res, {"raw_text": "UNKNOWN", "confidence": 0.0})
        self.assertFalse(eng._initialised, "tiny crops must not trigger backend init")

    def test_paddle_3x_dict_result_parsing(self):
        parts, confs = OCREngine._parse_paddle(
            [{"rec_texts": ["GJ01AB1234", "IND"], "rec_scores": [0.97, 0.5]}]
        )
        self.assertEqual(parts, ["GJ01AB1234", "IND"])
        self.assertEqual(confs, [0.97, 0.5])

    def test_paddle_2x_list_result_parsing(self):
        # PaddleOCR 2.x: result[0] is a list of [bbox, (text, conf)] lines.
        parts, confs = OCREngine._parse_paddle(
            [[[[[0, 0], [1, 0], [1, 1], [0, 1]], ("GJ01AB1234", 0.95)]]]
        )
        self.assertEqual(parts, ["GJ01AB1234"])
        self.assertEqual(confs, [0.95])


class TestPreprocessVariants(unittest.TestCase):
    def setUp(self):
        self.pre = ImagePreprocessor()

    def test_quality_gate_rejects_flat_crop(self):
        self.assertFalse(self.pre.quality_ok(np.full((40, 120, 3), 128, np.uint8)))
        self.assertEqual(self.pre.variants(np.full((40, 120, 3), 128, np.uint8)), [])

    def test_quality_gate_rejects_tiny_crop(self):
        self.assertFalse(self.pre.quality_ok(np.random.randint(0, 255, (6, 8, 3), dtype=np.uint8)))

    def test_variants_on_textured_crop(self):
        img = np.full((50, 200, 3), 240, np.uint8)
        cv2.putText(img, "GJ01AB1234", (6, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        vs = self.pre.variants(img, max_variants=4)
        self.assertEqual(len(vs), 4)
        for v in vs:
            self.assertEqual(v.ndim, 3)
            self.assertGreaterEqual(v.shape[0], self.pre.ocr_height - 1)

    def test_max_variants_respected(self):
        img = np.full((50, 200, 3), 240, np.uint8)
        cv2.putText(img, "MH12AB1234", (6, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        self.assertEqual(len(self.pre.variants(img, max_variants=2)), 2)


class TestExtractBest(unittest.TestCase):
    def test_prefers_valid_plate_format(self):
        eng = OCREngine()
        eng._initialised = True
        eng._paddle = None

        class _Easy:
            def __init__(self, seq):
                self.seq = list(seq)
            def readtext(self, *_a, **_k):
                t, c = self.seq.pop(0)
                return [([[0, 0], [1, 0], [1, 1], [0, 1]], t, c)]

        # variant 0: high conf but ill-formed; variant 1: lower conf, valid plate
        eng._easy = _Easy([("999999", 0.96), ("GJ01AB1234", 0.72)])
        eng._recompute_active()
        v = np.zeros((40, 160, 3), np.uint8)
        res = eng.extract_best([v, v.copy()], PlateNormalizer())
        self.assertEqual(res["raw_text"], "GJ01AB1234")
        self.assertEqual(res["variant"], 1)
        self.assertGreater(res["format_score"], 0.9)

    def test_empty_variants_returns_unknown(self):
        eng = OCREngine()
        self.assertEqual(eng.extract_best([], PlateNormalizer())["raw_text"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
