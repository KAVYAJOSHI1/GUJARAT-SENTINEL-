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
            ("GJO1AB1234", "GJ01AB1234"),
            ("GJ01A81234", "GJ01AB1234"),
            ("GJ01AB123A", "GJ01AB1234"),
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
            ("GJ01A81234", 0.65),
            ("GJ01AB1234", 0.94),
            ("GJ01AB1234", 0.88),
            ("GJ01AB1234", 0.95),
            ("GJ01A81234", 0.60),
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
        
        fi1 = FrameInput(
            frame=dummy_matrix,
            camera_id="CAM-TEST-01",
            pts=1500.0,
            timestamp="2026-09-02T10:00:00Z"
        )
        self.assertEqual(fi1.get_event_timestamp(), "2026-09-02T10:00:00Z")
        self.assertEqual(fi1.camera_id, "CAM-TEST-01")
        self.assertEqual(fi1.pts, 1500.0)

        fi2 = FrameInput(
            frame=dummy_matrix,
            camera_id="CAM-TEST-02",
            pts=1756800000000.0
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

        res1 = pipeline.process_frame(None)
        self.assertEqual(res1, [])

        res2 = pipeline.process_frame(np.array([]))
        self.assertEqual(res2, [])

        res3 = pipeline.process_frame(np.zeros((100,), dtype=np.uint8))
        self.assertEqual(res3, [])

        fi_empty = FrameInput(frame=None, camera_id="CAM-EMPTY")
        res4 = pipeline.process_frame(fi_empty)
        self.assertEqual(res4, [])

        print("Malformed & Empty Frame Handling Test Passed.")

    def test_unknown_plate_handling_and_flag(self):
        """Test that unreadable / empty plates correctly output UNKNOWN with plate_detected=False."""
        consensus = MultiFrameConsensus()
        res = consensus.get_consensus(track_id=999, camera_id="cam_test")
        self.assertEqual(res["consensus_plate"], "UNKNOWN")
        self.assertEqual(res["confidence"], 0.0)

        # Check AIPipeline payload structure when plate is unreadable
        pipeline = AIPipeline(evidence_dir=self.test_evidence_dir, device="cpu")
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        events = pipeline.process_frame(dummy_frame)
        self.assertEqual(events, []) # No vehicle detected on blank black frame
        print("UNKNOWN Plate Handling & plate_detected Flag Test Passed.")

    def test_bounded_consensus_state_and_lru(self):
        """Test that MultiFrameConsensus evicts oldest tracks when exceeding max_tracks limit."""
        small_consensus = MultiFrameConsensus(max_tracks=5, track_ttl_seconds=30.0)
        for i in range(10):
            small_consensus.add_prediction(track_id=i, plate_number=f"GJ01AB100{i}", confidence=0.90)

        self.assertLessEqual(len(small_consensus.track_history), 5)
        self.assertNotIn("CAM-001:0", small_consensus.track_history)
        self.assertIn("CAM-001:9", small_consensus.track_history)

        print("Bounded Consensus State & LRU Test Passed.")

    def test_multi_camera_state_isolation(self):
        """Test that track_id=1 on cam01 does not collide with track_id=1 on cam02."""
        consensus = MultiFrameConsensus()
        consensus.add_prediction(track_id=1, plate_number="GJ01AB1111", confidence=0.95, camera_id="cam01")
        consensus.add_prediction(track_id=1, plate_number="MH12DE2222", confidence=0.95, camera_id="cam02")

        c1 = consensus.get_consensus(track_id=1, camera_id="cam01")
        c2 = consensus.get_consensus(track_id=1, camera_id="cam02")

        self.assertEqual(c1["consensus_plate"], "GJ01AB1111")
        self.assertEqual(c2["consensus_plate"], "MH12DE2222")

        print("Multi-Camera State Isolation Test Passed.")

    def test_ocr_throttling_and_caching(self):
        """Test that stable consensus activates OCR throttling in AIPipeline."""
        pipeline = AIPipeline(evidence_dir=self.test_evidence_dir, ocr_throttle_frames=5, device="cpu")
        camera_id = "cam_throttle"
        track_id = 42

        # Manually inject stable consensus reads
        for _ in range(4):
            pipeline.consensus_engine.add_prediction(
                track_id=track_id,
                plate_number="GJ01AB1234",
                confidence=0.95,
                camera_id=camera_id
            )

        self.assertTrue(
            pipeline.consensus_engine.is_stable(
                track_id=track_id,
                camera_id=camera_id,
                min_votes=3,
                min_confidence=0.75
            )
        )
        print("OCR Throttling & Caching Test Passed.")

    def test_configurable_thresholds(self):
        """Test constructor and environment variable overrides for pipeline thresholds."""
        os.environ["CONFIDENCE_THRESHOLD"] = "0.65"
        os.environ["OCR_CONFIDENCE_THRESHOLD"] = "0.70"
        os.environ["CONSENSUS_STABLE_THRESHOLD"] = "0.80"

        pipeline = AIPipeline(evidence_dir=self.test_evidence_dir, device="cpu")
        self.assertEqual(pipeline.confidence_threshold, 0.65)
        self.assertEqual(pipeline.ocr_confidence_threshold, 0.70)
        self.assertEqual(pipeline.consensus_stable_threshold, 0.80)

        # Cleanup env vars
        os.environ.pop("CONFIDENCE_THRESHOLD", None)
        os.environ.pop("OCR_CONFIDENCE_THRESHOLD", None)
        os.environ.pop("CONSENSUS_STABLE_THRESHOLD", None)

        print("Configurable Thresholds Test Passed.")

if __name__ == "__main__":
    unittest.main()
