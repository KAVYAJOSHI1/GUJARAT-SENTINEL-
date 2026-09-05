"""
PHASE 3 -- ANPR / license-plate accuracy improvements.

Covers the specific changes made this pass, each tied to an audit finding:

  * plate localisation -- the morphological-closing second candidate source
    recovers plate regions the thin-contour / contourArea-undercount failure
    mode used to miss; deskew only fires on a genuinely tilted candidate;
    fallback stays bounded.
  * OCR scoring -- extract_best early-exits on a clearly-good variant
    (bounded per-vehicle OCR cost) but still tries every variant for
    ambiguous crops.
  * temporal consensus -- a low plate-locator-quality vote is weighted below
    an otherwise-identical high-quality vote.
  * Indian-plate normalisation -- realistic multi-character OCR confusions
    are fixed when the result is a real plate; arbitrary text / heavy
    garbage is NOT fabricated into a plate (honest-UNKNOWN preservation).
  * false-positive rejection -- dictionary words and digit runs never
    validate as plates.
"""
import unittest

import cv2
import numpy as np

from ai.anpr.consensus import MultiFrameConsensus
from ai.anpr.plate_locator import PlateLocator
from ai.anpr.preprocess import ImagePreprocessor
from ai.ocr.normalizer import PlateNormalizer
from ai.ocr.plate_format import correct_by_position, is_valid


def _plate_on_scene(text="GJ18TC0450", tilt_deg=0.0):
    """A rendered plate dropped into a textured scene -- the same shape the
    locator sees from a real vehicle crop."""
    plate = np.full((110, 430, 3), 255, np.uint8)
    cv2.rectangle(plate, (5, 5), (424, 104), (0, 0, 0), 3)
    cv2.putText(plate, text, (18, 78), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 5, cv2.LINE_AA)
    if tilt_deg:
        m = cv2.getRotationMatrix2D((215, 55), tilt_deg, 1.0)
        plate = cv2.warpAffine(plate, m, (430, 110), borderValue=(255, 255, 255))
    rng = np.random.default_rng(3)
    scene = rng.integers(60, 150, size=(300, 560, 3), dtype=np.uint8)
    scene[150:260, 70:500] = cv2.resize(plate, (430, 110))
    return scene, [70, 150, 500, 260]


class TestPlateLocalization(unittest.TestCase):
    def setUp(self):
        self.loc = PlateLocator()

    def test_locates_plate_region_in_scene(self):
        scene, plate_box = _plate_on_scene()
        crop = scene[plate_box[1]:plate_box[3], plate_box[0]:plate_box[2]]
        res = self.loc.locate_plate(crop)
        self.assertGreater(res["confidence"], 0.0)
        self.assertIsNotNone(res["plate_crop"])
        self.assertGreater(res["plate_crop"].size, 0)

    def test_returns_multiple_ranked_candidates(self):
        scene, plate_box = _plate_on_scene()
        crop = scene[plate_box[1]:plate_box[3], plate_box[0]:plate_box[2]]
        cands = self.loc.locate_candidates(crop, max_candidates=2)
        self.assertEqual(len(cands), 2)
        self.assertGreaterEqual(cands[0]["confidence"], cands[1]["confidence"] - 1e-6)
        for c in cands:
            self.assertIn("plate_crop", c)
            self.assertIn("bbox", c)

    def test_tiny_or_empty_input_is_safe(self):
        self.assertEqual(self.loc.locate_candidates(None), [])
        self.assertEqual(self.loc.locate_candidates(np.zeros((5, 5, 3), np.uint8)), [])
        # locate_plate must still honour its "always returns a dict" contract
        r = self.loc.locate_plate(np.zeros((5, 5, 3), np.uint8))
        self.assertEqual(r["confidence"], 0.0)

    def test_fallback_crop_is_bounded_and_not_full_frame(self):
        # a flat crop with no edges -> no contour candidate -> fallback path
        flat = np.full((200, 400, 3), 128, np.uint8)
        res = self.loc.locate_plate(flat)
        x1, y1, x2, y2 = res["bbox"]
        self.assertGreater(x1, 0)
        self.assertLess(x2, 400)
        self.assertGreater(y1, 0)
        self.assertLessEqual(res["confidence"], 0.5)

    def test_mildly_tilted_plate_still_located(self):
        scene, plate_box = _plate_on_scene(tilt_deg=8.0)
        crop = scene[plate_box[1]:plate_box[3], plate_box[0]:plate_box[2]]
        res = self.loc.locate_plate(crop)
        self.assertGreater(res["confidence"], 0.0)
        self.assertGreater(res["plate_crop"].size, 0)


class TestOCRScoringEarlyExit(unittest.TestCase):
    class _FakeEngine:
        """Stands in for OCREngine.extract_text: variant 0 is already a
        perfect read, variants 1+ would return junk. Real extract_best
        logic (the code under test) decides how many to consult."""

        def __init__(self):
            self.calls = 0

        def extract_text(self, img):
            self.calls += 1
            if self.calls == 1:
                return {"raw_text": "GJ18TC0450", "confidence": 0.99}
            return {"raw_text": "XYZ", "confidence": 0.20}

    def test_early_exit_stops_after_a_confident_variant(self):
        from ai.ocr.ocr_engine import OCREngine

        eng = OCREngine()
        fake = self._FakeEngine()
        eng.extract_text = fake.extract_text
        nz = PlateNormalizer()
        variants = [np.zeros((40, 160, 3), np.uint8) for _ in range(4)]
        res = eng.extract_best(variants, nz)
        self.assertEqual(res["raw_text"], "GJ18TC0450")
        self.assertEqual(fake.calls, 1)  # did NOT run the other 3 variants

    def test_all_variants_tried_when_none_are_confident(self):
        from ai.ocr.ocr_engine import OCREngine

        eng = OCREngine()
        calls = {"n": 0}

        def only_junk(img):
            calls["n"] += 1
            return {"raw_text": "J", "confidence": 0.15}

        eng.extract_text = only_junk
        variants = [np.zeros((40, 160, 3), np.uint8) for _ in range(4)]
        eng.extract_best(variants, PlateNormalizer())
        self.assertEqual(calls["n"], 4)


class TestConsensusPlateQualityWeighting(unittest.TestCase):
    def test_low_locator_quality_vote_loses_to_high_quality_vote(self):
        c = MultiFrameConsensus(min_confidence_threshold=0.4)
        # plate A: three votes, but each from a crude fallback crop
        for _ in range(3):
            c.add_prediction(1, "GJ01AB1234", 0.70, camera_id="cam",
                             detection_confidence=0.9, format_score=1.0,
                             plate_quality=0.50)
        # plate B: three votes from well-localised contour crops
        res = None
        for _ in range(3):
            res = c.add_prediction(1, "GJ01AB9999", 0.70, camera_id="cam",
                                   detection_confidence=0.9, format_score=1.0,
                                   plate_quality=0.95)
        self.assertEqual(res["consensus_plate"], "GJ01AB9999")

    def test_plate_quality_is_optional_backwards_compatible(self):
        c = MultiFrameConsensus(min_confidence_threshold=0.4)
        res = None
        for _ in range(3):
            res = c.add_prediction(2, "MH12AB3456", 0.9, camera_id="cam", format_score=1.0)
        self.assertEqual(res["consensus_plate"], "MH12AB3456")


class TestNormalizationRealisticOCRErrors(unittest.TestCase):
    def setUp(self):
        self.nz = PlateNormalizer()

    def test_single_char_confusions_fixed(self):
        cases = {
            "GJO1AB1234": "GJ01AB1234",   # O -> 0  (district)
            "GJ01A81234": "GJ01AB1234",   # 8 -> B  (series)
            "GJ18TC045O": "GJ18TC0450",   # O -> 0  (number)
            "MH1ZDE5678": "MH12DE5678",   # Z -> 2  (district)
        }
        for raw, want in cases.items():
            self.assertEqual(self.nz.normalize(raw), want, raw)

    def test_multi_char_confusion_fixed_when_result_is_a_real_plate(self):
        # 6->G, S->5, D->0 : three real confusions, result strictly valid
        self.assertEqual(self.nz.normalize("6J27DOL3S8D"), "GJ27DOL3580")

    def test_valid_series_letters_never_rewritten(self):
        # 2-digit-district standard plates: the layout model is unambiguous
        # here, so a legit series letter that collides with a digit-confusion
        # (S/5, B/8, G/6, ...) must survive.
        for p in ("GJ01SB1234", "MH12BC3456", "KA05GA1234", "TN09BB4321"):
            self.assertEqual(self.nz.normalize(p), p, p)

    def test_arbitrary_text_is_not_fabricated_into_a_plate(self):
        for junk in ("RANDOMTEXT", "12345678", "GARBAGE1", "2ZBH1234AA"):
            out = self.nz.normalize(junk)
            self.assertFalse(is_valid(out)[0], f"{junk!r} -> {out!r} wrongly validated")

    def test_partial_reads_preserved_not_padded(self):
        self.assertEqual(self.nz.normalize("GJ01"), "GJ01")   # too short to correct
        self.assertEqual(self.nz.normalize(""), "UNKNOWN")
        self.assertEqual(self.nz.normalize(None), "UNKNOWN")
        # a short partial is returned verbatim, never padded into a fake plate
        self.assertEqual(self.nz.normalize("GJ1"), "GJ1")

    def test_correction_count_cap(self):
        # a 4+ correction transform is refused even if it would "improve" score
        self.assertEqual(correct_by_position("AAAAAAAA"), "AAAAAAAA")


class TestFalsePositiveRejection(unittest.TestCase):
    def test_words_and_number_runs_do_not_validate(self):
        for s in ("HELLO", "POLICE", "STOP", "99999999", "CAMERA01"):
            ok, score = is_valid(s)
            self.assertFalse(ok, s)

    def test_real_plates_still_validate(self):
        for s in ("GJ18TC0450", "MH12AB3456", "DL3C9999", "22BH1234AA"):
            ok, _ = is_valid(s)
            self.assertTrue(ok, s)


class TestPreprocessQualityGate(unittest.TestCase):
    def setUp(self):
        self.pre = ImagePreprocessor()

    def test_rejects_unreadable_crops(self):
        self.assertFalse(self.pre.quality_ok(None))
        self.assertFalse(self.pre.quality_ok(np.zeros((40, 120, 3), np.uint8)))  # flat black
        self.assertFalse(self.pre.quality_ok(np.full((40, 120, 3), 255, np.uint8)))  # blown white
        self.assertFalse(self.pre.quality_ok(np.zeros((6, 8, 3), np.uint8)))  # too small

    def test_accepts_a_textured_plate_crop(self):
        rng = np.random.default_rng(1)
        crop = rng.integers(0, 255, size=(45, 160, 3), dtype=np.uint8)
        self.assertTrue(self.pre.quality_ok(crop))
        self.assertGreater(len(self.pre.variants(crop)), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
