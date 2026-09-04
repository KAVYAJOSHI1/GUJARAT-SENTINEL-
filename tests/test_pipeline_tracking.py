"""
PHASE 2 — ByteTrack wiring into ai/pipeline.py.

Proves the pipeline now assigns PERSISTENT, CAMERA-LOCAL track IDs instead of
the old per-frame ``track_id = idx + 1``:

  * one vehicle across many frames  -> one stable track_id
  * two vehicles in frame           -> two distinct track_ids
  * camera A and camera B           -> independent tracker state (no leak)
  * bbox / class / confidence / timestamp / event schema preserved
"""
import unittest

import numpy as np

from ai.pipeline import AIPipeline


def _box(cx, cy, w=90, h=70):
    return [int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2)]


class _Pipe:
    """AIPipeline with the two heavy/IO stages stubbed, tracker left REAL."""

    def __init__(self):
        self.p = AIPipeline(evidence_dir="tests/_tmp_track_ev", device="cpu")
        self._dets = []
        self.p.vehicle_detector.detect = lambda frame: list(self._dets)
        self.p.ocr_engine.extract_text = lambda img: {"raw_text": "GJ01AB1234", "confidence": 0.9}
        self.p._dispatch_event = lambda payload: True  # don't POST anywhere

    def frame(self, dets, camera_id, ts):
        self._dets = dets
        f = np.full((480, 640, 3), 120, np.uint8)
        return self.p.process_frame(f, camera_id=camera_id, frame_timestamp=ts)


class TestPipelinePersistentIDs(unittest.TestCase):
    def setUp(self):
        self.pipe = _Pipe()

    def tearDown(self):
        import shutil
        shutil.rmtree("tests/_tmp_track_ev", ignore_errors=True)

    def test_one_vehicle_keeps_one_track_id_across_frames(self):
        ids = set()
        for i in range(12):
            dets = [{"bbox": _box(120 + 8 * i, 240), "confidence": 0.9, "class": "car"}]
            evs = self.pipe.frame(dets, "cam04", f"2026-09-03T09:00:{i:02d}Z")
            self.assertEqual(len(evs), 1)
            ids.add(evs[0]["vehicle"]["track_id"])
        self.assertEqual(len(ids), 1, f"track id not stable: {ids}")

    def test_two_vehicles_get_distinct_ids(self):
        last = None
        for i in range(6):
            dets = [
                {"bbox": _box(100 + 6 * i, 150), "confidence": 0.92, "class": "car"},
                {"bbox": _box(520 - 6 * i, 380), "confidence": 0.88, "class": "truck"},
            ]
            last = self.pipe.frame(dets, "cam04", f"2026-09-03T09:10:{i:02d}Z")
        self.assertEqual(len(last), 2)
        tids = {e["vehicle"]["track_id"] for e in last}
        self.assertEqual(len(tids), 2, f"expected 2 distinct track ids, got {tids}")
        classes = {e["vehicle"]["track_id"]: e["vehicle"]["class"] for e in last}
        self.assertEqual(set(classes.values()), {"car", "truck"})

    def test_camera_state_does_not_leak_between_cameras(self):
        # feed cam04 for a while
        for i in range(8):
            self.pipe.frame([{"bbox": _box(120 + 5 * i, 240), "confidence": 0.9, "class": "car"}],
                            "cam04", f"2026-09-03T09:00:{i:02d}Z")
        # now cam12: a *different* vehicle, first frame -> its own tracker
        ev12 = self.pipe.frame([{"bbox": _box(400, 300), "confidence": 0.9, "class": "bus"}],
                               "cam12", "2026-09-03T09:20:00Z")
        self.assertEqual(len(ev12), 1)
        self.assertEqual(ev12[0]["camera_id"], "cam12")
        self.assertEqual(ev12[0]["vehicle"]["class"], "bus")
        # cam04 and cam12 are different tracker objects
        self.assertIsNot(self.pipe.p._trackers["cam04"], self.pipe.p._trackers["cam12"])
        # cam12's first track id is allocated by cam12's own tracker (starts at 1),
        # independent of how many tracks cam04 has created
        self.assertEqual(ev12[0]["vehicle"]["track_id"], 1)

    def test_event_schema_and_fields_preserved(self):
        evs = self.pipe.frame([{"bbox": _box(200, 240), "confidence": 0.91, "class": "car"}],
                              "cam04", "2026-09-03T09:30:00Z")
        e = evs[0]
        self.assertEqual(set(e), {"event_id", "timestamp", "pts", "camera_id", "vehicle",
                                  "license_plate", "evidence"})
        self.assertEqual(e["camera_id"], "cam04")
        self.assertEqual(e["timestamp"], "2026-09-03T09:30:00Z")
        self.assertEqual(len(e["vehicle"]["bbox"]), 4)
        self.assertEqual(e["vehicle"]["class"], "car")
        self.assertGreater(e["vehicle"]["confidence"], 0.0)
        self.assertIn("track_id", e["vehicle"])
        self.assertEqual(e["license_plate"]["plate_number"], "GJ01AB1234")

    def test_reset_camera_clears_only_that_camera(self):
        self.pipe.frame([{"bbox": _box(120, 240), "confidence": 0.9, "class": "car"}],
                        "cam04", "2026-09-03T09:00:00Z")
        self.pipe.frame([{"bbox": _box(300, 240), "confidence": 0.9, "class": "car"}],
                        "cam12", "2026-09-03T09:00:00Z")
        self.pipe.p.reset_camera("cam04")
        self.assertNotIn("cam04", self.pipe.p._trackers)
        self.assertIn("cam12", self.pipe.p._trackers)


if __name__ == "__main__":
    unittest.main(verbosity=2)
