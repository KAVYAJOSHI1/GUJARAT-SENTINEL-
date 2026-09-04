"""PHASE 3 — Indian plate format model + position-aware correction."""
import unittest

from ai.ocr.normalizer import PlateNormalizer
from ai.ocr.plate_format import (
    correct_by_position,
    expected_classes,
    format_score,
    is_valid,
)


class TestFormatModel(unittest.TestCase):
    def test_standard_plates_valid(self):
        for p in ("GJ18TC0450", "MH12AB3456", "DL7CN1234", "KA01MJ4321", "RJ14CB0001"):
            ok, score = is_valid(p)
            self.assertTrue(ok, p)
            self.assertEqual(score, 1.0, p)

    def test_bad_state_valid_shape_lower_score(self):
        ok, score = is_valid("SJ18TC0450")  # SJ is not a real state
        self.assertFalse(ok)
        self.assertGreater(score, 0.5)
        self.assertLess(score, 1.0)

    def test_expected_classes_layout(self):
        self.assertEqual(
            expected_classes("GJ18TC0450"),
            ["A", "A", "N", "N", "A", "A", "N", "N", "N", "N"],
        )
        self.assertEqual(expected_classes("DL3C9999"),
                         ["A", "A", "N", "A", "N", "N", "N", "N"])

    def test_garbage_low_score(self):
        self.assertLess(format_score("XQ9Z"), 0.5)
        self.assertEqual(format_score(""), 0.0)


class TestPositionAwareCorrection(unittest.TestCase):
    def test_fixes_only_class_mismatches(self):
        # O in the district (numeric) position -> 0
        self.assertEqual(correct_by_position("GJO1AB1234"), "GJ01AB1234")
        # 8 in the series (alpha) position -> B
        self.assertEqual(correct_by_position("GJ01A81234"), "GJ01AB1234")
        # trailing A in the number position -> 4
        self.assertEqual(correct_by_position("GJ01AB123A"), "GJ01AB1234")

    def test_does_not_corrupt_valid_letters(self):
        # 'S' is a legit series letter here and must NOT become '5'
        self.assertEqual(correct_by_position("GJ01SB1234"), "GJ01SB1234")
        # 'B' as a series letter stays 'B', not '8'
        self.assertEqual(correct_by_position("MH12BC3456"), "MH12BC3456")

    def test_confidence_gate_blocks_correction(self):
        # high per-char confidence on the mismatching char -> leave it alone
        conf = [0.99] * 10
        self.assertEqual(correct_by_position("GJO1AB1234", conf, 0.85), "GJO1AB1234")

    def test_rejects_correction_that_lowers_validity(self):
        # no sensible swap for 'C' at a numeric position -> unchanged
        self.assertEqual(correct_by_position("GJ18TC045C"), "GJ18TC045C")


class TestNormalizerIntegration(unittest.TestCase):
    def test_normalize_uses_position_aware(self):
        nz = PlateNormalizer()
        self.assertEqual(nz.normalize("GJ-O1 AB 1234"), "GJ01AB1234")
        self.assertEqual(nz.normalize("gj01a81234"), "GJ01AB1234")
        self.assertEqual(nz.normalize(""), "UNKNOWN")
        self.assertEqual(nz.normalize("AB"), "AB")

    def test_format_score_exposed(self):
        nz = PlateNormalizer()
        self.assertEqual(nz.format_score("GJ18TC0450"), 1.0)
        self.assertLess(nz.format_score("SJ18TC0450"), 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
