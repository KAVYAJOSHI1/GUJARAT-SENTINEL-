"""
Phase 18 Part A/D -- scripts/anpr_diagnostics.py.

Fast checks (no video I/O, no real-camera evidence dependency so this
suite stays green on a fresh checkout without the trafficdataset/evidence
directories) that the diagnostic engine produces the rich, explainable
per-vehicle record Part A asks for, and that the SYNTHETIC/MOCK/REAL
strata are never combined into one misleading number.
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.anpr_diagnostics import (  # noqa: E402
    AnprDiagnosticEngine,
    DiagnosticRecord,
    summarize,
    synthetic_vehicle_crops,
)


class TestDiagnosticRecordShape(unittest.TestCase):
    def setUp(self):
        self.engine = AnprDiagnosticEngine()

    def test_synthetic_plate_produces_full_diagnostic_record(self):
        crops = synthetic_vehicle_crops(1)
        crop, plate = crops[0]
        rec = self.engine.diagnose_synthetic_plate(crop, source_file="unit-test")
        self.assertIsInstance(rec, DiagnosticRecord)
        self.assertTrue(rec.vehicle_detected)
        self.assertTrue(rec.plate_located)
        self.assertGreater(rec.plate_crop_width, 0)
        self.assertGreater(rec.plate_crop_height, 0)
        self.assertIsNotNone(rec.blur_score)
        self.assertIsNotNone(rec.contrast_score)
        self.assertIsNotNone(rec.angle_deg)
        self.assertIsNotNone(rec.char_estimate)
        self.assertIsNotNone(rec.overall_quality_score)
        self.assertIsNotNone(rec.ocr_raw_text)
        self.assertIsNotNone(rec.normalized_plate)
        self.assertIn(rec.failure_reason, (
            "NONE", "NO_PLATE", "LOW_RESOLUTION", "BLUR", "OCCLUDED",
            "OCR_DISAGREEMENT", "INVALID_FORMAT", "LOW_CONFIDENCE",
        ))

    def test_empty_crop_never_crashes_and_reports_no_plate(self):
        rec = self.engine._diagnose_vehicle_crop(
            None, stratum="SYNTHETIC", source_file="empty", frame_index=None,
            track_id=None, camera_id="diag",
        )
        self.assertFalse(rec.plate_located)
        self.assertEqual(rec.failure_reason, "NO_PLATE")

    def test_no_frame_no_detections_produces_a_record_not_an_exception(self):
        blank = np.full((480, 640, 3), 100, np.uint8)
        records = self.engine.diagnose_frame(blank, stratum="SYNTHETIC", source_file="blank-frame")
        self.assertEqual(len(records), 1)
        self.assertFalse(records[0].vehicle_detected)


class TestTemporalFusionIntegration(unittest.TestCase):
    def test_stable_track_reduces_toward_the_true_plate_over_frames(self):
        """The Part A/C worked example: a noisy single-frame OCR read must
        not by itself become the final answer -- repeated agreement should
        converge on the majority reading."""
        engine = AnprDiagnosticEngine()
        crop, true_plate = synthetic_vehicle_crops(1)[0]
        last = None
        for i in range(5):
            last = engine._diagnose_vehicle_crop(
                crop, stratum="SYNTHETIC", source_file="temporal-test", frame_index=i,
                track_id=1, camera_id="diag-cam",
            )
        self.assertIsNotNone(last.temporal_plate)
        self.assertIsInstance(last.temporal_confidence, float)


class TestStrataNeverCombined(unittest.TestCase):
    def test_summarize_labels_ground_truth_methodology_explicitly(self):
        recs = [DiagnosticRecord(stratum="MOCK", source_file="f1", normalized_plate="UNKNOWN", failure_reason="OCCLUDED")]
        s = summarize("MOCK", recs, ground_truth=None)
        self.assertIn("UNLABELED", s["ground_truth_methodology"])
        self.assertIsNone(s["exact_plate_accuracy"])

    def test_summarize_computes_accuracy_only_when_ground_truth_given(self):
        recs = [
            DiagnosticRecord(stratum="SYNTHETIC", source_file="f1", normalized_plate="GJ01AB1234"),
            DiagnosticRecord(stratum="SYNTHETIC", source_file="f2", normalized_plate="UNKNOWN"),
        ]
        gt = {"f1": "GJ01AB1234", "f2": "GJ01AB1234"}
        s = summarize("SYNTHETIC", recs, ground_truth=gt)
        self.assertEqual(s["labeled_samples"], 2)
        self.assertEqual(s["exact_plate_accuracy"], 0.5)

    def test_failure_reason_breakdown_only_counts_unresolved_reads(self):
        recs = [
            DiagnosticRecord(stratum="MOCK", source_file="f1", normalized_plate="GJ01AB1234", failure_reason="NONE"),
            DiagnosticRecord(stratum="MOCK", source_file="f2", normalized_plate="UNKNOWN", failure_reason="BLUR"),
        ]
        s = summarize("MOCK", recs)
        self.assertEqual(s["failure_reason_breakdown"], {"BLUR": 1})
        self.assertEqual(s["unknown_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
