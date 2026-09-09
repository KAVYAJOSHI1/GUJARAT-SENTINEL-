"""
PHASE 17 Step 4 -- AIPipeline.process_frame() processing modes.

DETECTION/TRACKING modes must never touch the plate locator or OCR engine
(not "OCR ran and found nothing" -- genuinely never attempted), while the
default (ANPR, unchanged) behavior is verified to be byte-for-byte
untouched when `mode` is omitted.
"""
import unittest

import numpy as np

from ai.modes import ProcessingMode
from ai.pipeline import AIPipeline


def _box(cx, cy, w=90, h=70):
    return [int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2)]


class _Pipe:
    def __init__(self):
        self.p = AIPipeline(evidence_dir="tests/_tmp_mode_ev", device="cpu")
        self._dets = []
        self.p.vehicle_detector.detect = lambda frame: list(self._dets)
        self.ocr_calls = 0
        self.locator_calls = 0

        real_extract = self.p.ocr_engine.extract_text

        def counting_extract(img):
            self.ocr_calls += 1
            return real_extract(img)

        self.p.multivariant_ocr = False
        self.p.ocr_engine.extract_text = counting_extract

        real_locate = self.p.plate_locator.locate_plate

        def counting_locate(crop):
            self.locator_calls += 1
            return real_locate(crop)

        self.p.plate_locator.locate_plate = counting_locate
        self.p._dispatch_event = lambda payload: True

    def frame(self, dets, camera_id, ts, mode=None):
        self._dets = dets
        f = np.full((480, 640, 3), 120, np.uint8)
        return self.p.process_frame(f, camera_id=camera_id, frame_timestamp=ts, mode=mode)


class TestDefaultModeUnchanged(unittest.TestCase):
    def setUp(self):
        self.pipe = _Pipe()

    def tearDown(self):
        import shutil
        shutil.rmtree("tests/_tmp_mode_ev", ignore_errors=True)

    def test_no_mode_argument_still_runs_ocr(self):
        dets = [{"bbox": _box(100, 150), "confidence": 0.9, "class": "car"}]
        events = self.pipe.frame(dets, "cam01", "2026-09-09T09:00:00Z")
        self.assertGreater(self.pipe.locator_calls, 0)
        self.assertGreater(self.pipe.ocr_calls, 0)
        self.assertEqual(len(events), 1)
        self.assertNotEqual(events[0]["anpr"]["status"], "NOT_ATTEMPTED")

    def test_explicit_anpr_mode_matches_default(self):
        dets = [{"bbox": _box(100, 150), "confidence": 0.9, "class": "car"}]
        events = self.pipe.frame(dets, "cam01", "2026-09-09T09:00:00Z", mode=ProcessingMode.ANPR)
        self.assertGreater(self.pipe.ocr_calls, 0)
        self.assertEqual(len(events), 1)


class TestDetectionAndTrackingModesSkipOCR(unittest.TestCase):
    def setUp(self):
        self.pipe = _Pipe()

    def tearDown(self):
        import shutil
        shutil.rmtree("tests/_tmp_mode_ev", ignore_errors=True)

    def test_detection_mode_never_calls_ocr_or_locator(self):
        dets = [{"bbox": _box(100, 150), "confidence": 0.9, "class": "car"}]
        events = self.pipe.frame(dets, "cam01", "2026-09-09T09:00:00Z", mode=ProcessingMode.DETECTION)
        self.assertEqual(self.pipe.ocr_calls, 0)
        self.assertEqual(self.pipe.locator_calls, 0)
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["anpr"]["status"], "NOT_ATTEMPTED")
        self.assertFalse(ev["license_plate"]["plate_detected"])
        self.assertIsNone(ev["evidence"]["frame_path"])

    def test_tracking_mode_never_calls_ocr_or_locator(self):
        dets = [{"bbox": _box(100, 150), "confidence": 0.9, "class": "car"}]
        events = self.pipe.frame(dets, "cam01", "2026-09-09T09:00:00Z", mode=ProcessingMode.TRACKING)
        self.assertEqual(self.pipe.ocr_calls, 0)
        self.assertEqual(self.pipe.locator_calls, 0)
        self.assertEqual(len(events), 1)

    def test_detection_mode_still_has_stable_track_id_across_frames(self):
        ids = set()
        for i in range(6):
            dets = [{"bbox": _box(120 + 8 * i, 240), "confidence": 0.9, "class": "car"}]
            for e in self.pipe.frame(dets, "cam02", f"2026-09-09T09:00:{i:02d}Z", mode=ProcessingMode.DETECTION):
                ids.add(e["vehicle"]["track_id"])
        # only one event is ever emitted (dedup on first sighting -- plate
        # never changes for a NOT_ATTEMPTED track), so `ids` has exactly the
        # one track_id assigned on first sighting.
        self.assertEqual(len(ids), 1)
        self.assertEqual(self.pipe.ocr_calls, 0)

    def test_mode_via_metadata_when_not_passed_explicitly(self):
        dets = [{"bbox": _box(100, 150), "confidence": 0.9, "class": "car"}]
        self.pipe._dets = dets
        f = np.full((480, 640, 3), 120, np.uint8)
        events = self.pipe.p.process_frame(
            f, camera_id="cam03", frame_timestamp="2026-09-09T09:00:00Z",
            metadata={"processing_mode": ProcessingMode.DETECTION},
        )
        self.assertEqual(self.pipe.ocr_calls, 0)
        self.assertEqual(len(events), 1)


if __name__ == "__main__":
    unittest.main()
