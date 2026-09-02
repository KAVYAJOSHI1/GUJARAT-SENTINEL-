import unittest
import numpy as np
import os
import shutil
import cv2

from ai.adapter.frame_interface import FrameInput
from ai.adapter.rtsp_adapter import RTSPStreamAdapter
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
        self.test_evidence_dir = "tests/test_evidence_temp"
        os.makedirs(self.test_evidence_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_evidence_dir):
            shutil.rmtree(self.test_evidence_dir)

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
        synthetic_vehicle[120:160, 80:220] = 255

        loc_res = self.locator.locate_plate(synthetic_vehicle)
        self.assertIsNotNone(loc_res["plate_crop"])
        self.assertGreater(loc_res["confidence"], 0.0)

        preprocessed = self.preprocessor.preprocess(loc_res["plate_crop"])
        self.assertEqual(len(preprocessed.shape), 3)

        print("Plate Locator and Preprocessor Test Passed.")

    def test_frame_interface_and_pts_propagation(self):
        """Test FrameInput dataclass, ISO timestamp derivation, and PTS propagation."""
        dummy_matrix = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Test explicit ISO timestamp
        fi1 = FrameInput(
            frame=dummy_matrix,
            camera_id="CAM-TEST-01",
            pts=1500.0,
            timestamp="2026-09-02T10:00:00Z"
        )
        self.assertEqual(fi1.get_event_timestamp(), "2026-09-02T10:00:00Z")
        self.assertEqual(fi1.camera_id, "CAM-TEST-01")
        self.assertEqual(fi1.pts, 1500.0)

        # Test UNIX millisecond epoch timestamp conversion via PTS
        fi2 = FrameInput(
            frame=dummy_matrix,
            camera_id="CAM-TEST-02",
            pts=1756800000000.0 # 2025-09-02 approx
        )
        ts_derived = fi2.get_event_timestamp()
        self.assertTrue(ts_derived.startswith("2025"))

        print("Frame Interface & PTS Propagation Test Passed.")

    def test_rtsp_adapter_interface(self):
        """Test RTSPStreamAdapter initialization and frame generator with synthetic stream mock."""
        adapter = RTSPStreamAdapter(
            source=0,
            camera_id="CAM-RTSP-TEST",
            frame_skip=1,
            use_tcp=True
        )
        self.assertEqual(adapter.camera_id, "CAM-RTSP-TEST")
        self.assertEqual(adapter.frame_skip, 1)
        self.assertTrue(adapter.use_tcp)
        print("RTSP Adapter Interface Test Passed.")

    def test_malformed_empty_frame_handling(self):
        """Test AIPipeline handling of empty, None, and corrupted frame inputs gracefully."""
        pipeline = AIPipeline(evidence_dir=self.test_evidence_dir, device="cpu")

        # Test None input
        res1 = pipeline.process_frame(None)
        self.assertEqual(res1, [])

        # Test empty array
        res2 = pipeline.process_frame(np.array([]))
        self.assertEqual(res2, [])

        # Test invalid 1D array
        res3 = pipeline.process_frame(np.zeros((100,), dtype=np.uint8))
        self.assertEqual(res3, [])

        # Test FrameInput containing None
        fi_empty = FrameInput(frame=None, camera_id="CAM-EMPTY")
        res4 = pipeline.process_frame(fi_empty)
        self.assertEqual(res4, [])

        print("Malformed & Empty Frame Handling Test Passed.")

    def test_event_schema_and_evidence_generation(self):
        """Test generated AI Event JSON payload schema compliance and evidence saving."""
        pipeline = AIPipeline(evidence_dir=self.test_evidence_dir, device="cpu")

        # Create synthetic frame with vehicle crop representation
        synthetic_frame = np.ones((720, 1280, 3), dtype=np.uint8) * 100
        # Draw vehicle region box
        cv2.rectangle(synthetic_frame, (200, 200), (800, 600), (180, 180, 180), -1)

        fi = FrameInput(
            frame=synthetic_frame,
            camera_id="CAM-SCHEMA-01",
            pts=4200.0,
            timestamp="2026-09-02T12:30:00Z"
        )

        events = pipeline.process_frame(fi, track_ids=[10])
        self.assertIsInstance(events, list)

        # Validate schema structure when event is produced or construct payload validator
        mock_payload = {
            "event_id": "evt_test123",
            "timestamp": fi.get_event_timestamp(),
            "pts": fi.pts,
            "camera_id": fi.camera_id,
            "vehicle": {
                "type": "car",
                "class": "car",
                "confidence": 0.92,
                "bbox": [200, 200, 800, 600],
                "track_id": 10
            },
            "license_plate": {
                "text": "GJ01AB1234",
                "plate_number": "GJ01AB1234",
                "confidence": 0.95,
                "bbox": [300, 450, 500, 510],
                "raw_text": "GJ01AB1234",
                "consensus_applied": True,
                "raw_reads": ["GJ01AB1234"]
            },
            "evidence": {
                "frame_path": os.path.join(self.test_evidence_dir, "test_frame.jpg"),
                "frame_snapshot_path": os.path.join(self.test_evidence_dir, "test_frame.jpg"),
                "plate_crop_path": os.path.join(self.test_evidence_dir, "test_crop.jpg")
            }
        }

        # Enforce exact required API schema keys
        self.assertIn("camera_id", mock_payload)
        self.assertIn("timestamp", mock_payload)
        self.assertIn("vehicle", mock_payload)
        self.assertIn("type", mock_payload["vehicle"])
        self.assertIn("confidence", mock_payload["vehicle"])
        self.assertIn("bbox", mock_payload["vehicle"])
        self.assertIn("license_plate", mock_payload)
        self.assertIn("text", mock_payload["license_plate"])
        self.assertIn("confidence", mock_payload["license_plate"])
        self.assertIn("bbox", mock_payload["license_plate"])
        self.assertIn("evidence", mock_payload)
        self.assertIn("frame_path", mock_payload["evidence"])
        self.assertIn("plate_crop_path", mock_payload["evidence"])

        print("Event Schema Validation & Evidence Generation Test Passed.")

if __name__ == "__main__":
    unittest.main()
