import unittest
import numpy as np
import os
import shutil

from ai.detection.vehicle_detector import VehicleDetector
from ai.anpr.plate_locator import PlateLocator
from ai.anpr.preprocess import ImagePreprocessor
from ai.anpr.consensus import MultiFrameConsensus
from ai.ocr.normalizer import PlateNormalizer
from ai.pipeline import AIPipeline

class TestAIPipeline(unittest.TestCase):

    def setUp(self):
        self.normalizer = PlateNormalizer()
        self.consensus = MultiFrameConsensus()
        self.locator = PlateLocator()
        self.preprocessor = ImagePreprocessor()

    def test_plate_normalization(self):
        """Test normalization regex on 20+ dirty test strings."""
        test_cases = [
            ("GJ-01 AB 1234", "GJ01AB1234"),
            ("G.J.01.AB.1234", "GJ01AB1234"),
            ("GJ 01 AB 1234", "GJ01AB1234"),
            ("GJ-05-XX-7821", "GJ05XX7821"),
            ("MH-12-DE-5678", "MH12DE5678"),
            ("DL 3C 9999", "DL3C9999"),
            ("GJO1AB1234", "GJ01AB1234"), # 'O' in district position -> '0'
            ("GJ01A81234", "GJ01AB1234"), # '8' in series position -> 'B'
            ("GJ01AB123A", "GJ01AB1234"), # 'A' in last digit position -> '4'
            ("RJ-14-CB-0001", "RJ14CB0001"),
            ("KA-01-MJ-4321", "KA01MJ4321"),
            ("TN-09-AX-9990", "TN09AX9990"),
            ("UP-32-BZ-1111", "UP32BZ1111"),
            ("HR-26-DQ-5555", "HR26DQ5555"),
            ("WB-02-AK-7777", "WB02AK7777"),
            ("GJ/01/AB/1234", "GJ01AB1234"),
            ("gj-01-ab-1234", "GJ01AB1234"),
            ("  GJ-01 AB 1234  ", "GJ01AB1234"),
            ("GJ-01-A-1234", "GJ01A1234"),
            ("MH01A1234", "MH01A1234"),
            ("UK07AA1000", "UK07AA1000"),
            ("MP09CB9876", "MP09CB9876")
        ]

        for dirty_input, expected in test_cases:
            result = self.normalizer.normalize(dirty_input)
            self.assertEqual(result, expected, f"Failed for input: '{dirty_input}'. Got '{result}', expected '{expected}'.")

        print("Plate Normalization Test Passed (22/22 test cases).")

    def test_multi_frame_consensus(self):
        """Test consensus algorithm correcting noisy frame misreads across track frames."""
        track_id = 101
        
        # 10 simulated frame predictions with noisy outlier misreads
        frame_predictions = [
            ("GJ01AB1234", 0.92),
            ("GJ01AB1234", 0.90),
            ("GJ01A81234", 0.65), # Noisy frame misread (8 instead of B)
            ("GJ01AB1234", 0.94),
            ("GJ01AB1234", 0.88),
            ("GJ01AB1234", 0.95),
            ("GJ01A81234", 0.60), # Noisy frame misread
            ("GJ01AB1234", 0.91),
            ("GJ01AB1234", 0.93),
            ("GJ01AB1234", 0.89)
        ]

        final_res = None
        for plate, conf in frame_predictions:
            final_res = self.consensus.add_prediction(track_id, plate, conf)

        self.assertIsNotNone(final_res)
        self.assertEqual(final_res["consensus_plate"], "GJ01AB1234")
        self.assertEqual(final_res["total_votes"], 10)
        self.assertEqual(final_res["winner_votes"], 8)
        self.assertTrue(final_res["confidence"] > 0.85)

        print(f"Multi-Frame Consensus Test Passed! Winner: {final_res['consensus_plate']} ({final_res['winner_votes']}/10 votes, conf {final_res['confidence']}).")

    def test_plate_locator_and_preprocessor(self):
        """Test license plate locator and preprocessor on synthetic frame."""
        synthetic_vehicle = np.ones((200, 300, 3), dtype=np.uint8) * 128
        # Draw a simulated license plate rectangle in bottom area
        synthetic_vehicle[120:160, 80:220] = 255

        loc_res = self.locator.locate_plate(synthetic_vehicle)
        self.assertIsNotNone(loc_res["plate_crop"])
        self.assertGreater(loc_res["confidence"], 0.0)

        preprocessed = self.preprocessor.preprocess(loc_res["plate_crop"])
        self.assertEqual(len(preprocessed.shape), 3)

        print("Plate Locator and Preprocessor Test Passed.")

    def test_vehicle_detector_and_pipeline(self):
        """Test AIPipeline process_frame on sample frame array."""
        pipeline = AIPipeline(evidence_dir="tests/test_evidence", device="cpu")
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        events = pipeline.process_frame(dummy_frame, camera_id="CAM-TEST-01")
        self.assertIsInstance(events, list)

        # Clean up test evidence directory if created
        if os.path.exists("tests/test_evidence"):
            shutil.rmtree("tests/test_evidence")

        print("AIPipeline End-to-End Frame Processing Test Passed.")

if __name__ == "__main__":
    unittest.main()
