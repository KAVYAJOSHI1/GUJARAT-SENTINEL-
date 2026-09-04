"""
Unit + integration tests for the Vehicle Tracking & Cross-Camera Correlation
engine (DEVELOPER_README section 16 / section 24).

Runnable with the standard library only (numpy + scipy) -- no OpenCV / GPU:
    python -m unittest tests.test_tracking -v
"""
import time
import unittest

from ai.tracking.tracker import ByteTrackTracker, TrackEventDeduplicator
from ai.tracking.track_association import iou, associate_plates_to_tracks
from ai.tracking.correlation import CrossCameraCorrelator


def _moving_car(frame_idx, x0=100.0, y0=200.0, vx=3.0, vy=0.0, w=80.0, h=60.0, score=0.90):
    """A vehicle detection drifting at constant velocity across frames."""
    x1 = x0 + vx * frame_idx
    y1 = y0 + vy * frame_idx
    return {"bbox": [x1, y1, x1 + w, y1 + h], "confidence": score, "class": "car"}


class TestIoUAssociation(unittest.TestCase):
    """DEVELOPER_README section 16: unit-test IoU association vehicle bbox <-> plate crop."""

    def test_iou_identical_disjoint_partial(self):
        self.assertAlmostEqual(iou([0, 0, 10, 10], [0, 0, 10, 10]), 1.0)
        self.assertEqual(iou([0, 0, 10, 10], [20, 20, 30, 30]), 0.0)
        # 50% x-overlap, full y-overlap -> inter 50, union 150 -> 1/3
        self.assertAlmostEqual(iou([0, 0, 10, 10], [5, 0, 15, 10]), 1.0 / 3.0, places=6)

    def test_plate_bound_to_correct_track(self):
        tracks = [
            {"track_id": 1, "bbox": [100, 100, 200, 260]},
            {"track_id": 2, "bbox": [400, 100, 520, 280]},
        ]
        plates = [
            {"bbox": [430, 230, 470, 250], "plate_number": "GJ05XX7821", "confidence": 0.88},
            {"bbox": [130, 220, 170, 240], "plate_number": "GJ01AB1234", "confidence": 0.91},
        ]
        result = associate_plates_to_tracks(tracks, plates)
        self.assertEqual(result[1]["plate_number"], "GJ01AB1234")
        self.assertEqual(result[2]["plate_number"], "GJ05XX7821")
        self.assertTrue(result[1]["matched"] and result[2]["matched"])

    def test_unplated_track_gets_temp_identity_and_never_crashes(self):
        tracks = [{"track_id": 7, "bbox": [0, 0, 100, 100]}]
        # DEVELOPER_README section 15: "No Plate Match" -> UNPLATED_TRACK_{id}
        result = associate_plates_to_tracks(tracks, [])
        self.assertEqual(result[7]["plate_number"], "UNPLATED_TRACK_7")
        self.assertFalse(result[7]["matched"])


class TestByteTrackLifecycle(unittest.TestCase):
    """DEVELOPER_README section 24.1 + section 16."""

    def test_persistent_id_across_100_frames(self):
        tracker = ByteTrackTracker()
        ids_seen = set()
        for f in range(1, 101):
            out = tracker.update([_moving_car(f)], frame_id=f)
            self.assertEqual(len(out), 1, f"lost the vehicle at frame {f}")
            ids_seen.add(out[0]["track_id"])
        self.assertEqual(ids_seen, {1}, "track ID was not stable across 100 frames")
        self.assertGreaterEqual(out[0]["hits"], 99)

    def test_survives_frame_drops(self):
        """< 15-frame occlusion must keep the same ID (Kalman prediction, section 15)."""
        tracker = ByteTrackTracker()
        track_id = None
        for f in range(1, 21):
            out = tracker.update([_moving_car(f)], frame_id=f)
            track_id = out[0]["track_id"]

        # 6 consecutive frames with NO detections (vehicle briefly occluded)
        for f in range(21, 27):
            out = tracker.update([], frame_id=f)
            self.assertEqual(out, [], "occluded vehicle should not produce online tracks")

        # reappears -> same ID, no new track spawned
        for f in range(27, 40):
            out = tracker.update([_moving_car(f)], frame_id=f)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["track_id"], track_id, "ID switched after brief occlusion")

    def test_track_termination_emits_exactly_one_event(self):
        """DEVELOPER_README section 24.2: dedup -> 1 consolidated event per completed track."""
        tracker = ByteTrackTracker(track_buffer=5)
        dedup = TrackEventDeduplicator()
        emitted = []

        for f in range(1, 16):                       # vehicle present, plenty of frames
            tracker.update([_moving_car(f)], frame_id=f)
        for f in range(16, 40):                      # vehicle gone -> track ages out
            tracker.update([], frame_id=f)
            for t in tracker.get_finalized_tracks():
                if dedup.should_emit("cam05", t["track_id"], "GJ01AB1234", f):
                    emitted.append(dedup.build_event(t, "cam05", {"plate_number": "GJ01AB1234", "confidence": 0.9}))

        self.assertEqual(len(emitted), 1, "expected exactly one consolidated event")
        self.assertEqual(emitted[0]["license_plate"]["plate_number"], "GJ01AB1234")
        self.assertTrue(emitted[0]["license_plate"]["plate_detected"])

    def test_two_vehicles_get_distinct_ids(self):
        tracker = ByteTrackTracker()
        for f in range(1, 12):
            dets = [_moving_car(f, x0=50, y0=100), _moving_car(f, x0=600, y0=400, vx=-2)]
            out = tracker.update(dets, frame_id=f)
        self.assertEqual(len(out), 2)
        self.assertEqual(len({t["track_id"] for t in out}), 2)


class TestCrossCameraCorrelation(unittest.TestCase):
    """DEVELOPER_README section 24.3 + section 16."""

    def test_out_of_order_sightings_sorted_ascending(self):
        corr = CrossCameraCorrelator()
        # 4 cameras, deliberately inserted out of chronological order
        corr.add_event({"plate_number": "GJ01AB1234", "camera_id": "cam03", "location": "ONGC",
                        "timestamp": "2026-09-03T09:15:00Z", "event_id": "e3"})
        corr.add_event({"plate_number": "GJ01AB1234", "camera_id": "cam01", "location": "Chimanbhai",
                        "timestamp": "2026-09-03T09:00:00Z", "event_id": "e1"})
        corr.add_event({"plate_number": "GJ01AB1234", "camera_id": "cam05", "location": "Visat",
                        "timestamp": "2026-09-03T09:25:00Z", "event_id": "e4"})
        corr.add_event({"plate_number": "GJ-01-AB-1234", "camera_id": "cam02", "location": "Janpath",
                        "timestamp": 1788426600.0, "event_id": "e2"})   # 2026-09-03T09:10:00Z as epoch

        traj = corr.build_trajectory("GJ01AB1234")
        self.assertEqual([h["camera_id"] for h in traj], ["cam01", "cam02", "cam03", "cam05"])
        self.assertEqual([h["event_id"] for h in traj], ["e1", "e2", "e3", "e4"])
        # monotonic non-decreasing epochs
        epochs = [h["epoch"] for h in traj]
        self.assertEqual(epochs, sorted(epochs))
        self.assertIsNone(traj[0]["seconds_since_previous"])
        self.assertEqual(traj[1]["previous_camera_id"], "cam01")
        self.assertGreater(traj[1]["seconds_since_previous"], 0)

    def test_composite_identity_dedup(self):
        """plate + timestamp + camera_id + location -> identical sighting stored once."""
        corr = CrossCameraCorrelator()
        base = {"plate_number": "GJ01AB1234", "camera_id": "cam01", "location": "Chimanbhai",
                "timestamp": "2026-09-03T09:00:00Z"}
        self.assertTrue(corr.add_event(dict(base)))
        self.assertFalse(corr.add_event(dict(base)))            # exact duplicate
        self.assertFalse(corr.add_event({**base, "event_id": "x"}))
        self.assertEqual(len(corr.build_trajectory("GJ01AB1234")), 1)

    def test_unplated_and_unknown_events_rejected(self):
        corr = CrossCameraCorrelator()
        self.assertFalse(corr.add_event({"plate_number": "UNPLATED_TRACK_4", "camera_id": "cam01",
                                         "timestamp": "2026-09-03T09:00:00Z"}))
        self.assertFalse(corr.add_event({"plate_number": "UNKNOWN", "camera_id": "cam01",
                                         "timestamp": "2026-09-03T09:00:00Z"}))
        self.assertEqual(corr.all_plates(), [])

    def test_vehicle_history_contract_shape(self):
        """Matches backend/app/schemas/vehicle.py :: VehicleHistoryResponse / VehicleSighting."""
        corr = CrossCameraCorrelator()
        corr.add_event({"plate_number": "GJ01AB1234", "camera_id": "cam01", "camera_name": "Chimanbhai",
                        "timestamp": "2026-09-03T09:00:00Z", "latitude": 23.02, "longitude": 72.5,
                        "confidence": 0.93, "snapshot_url": "http://x/a.jpg", "event_id": "e1"})
        hist = corr.to_vehicle_history("GJ01AB1234", is_watchlisted=True)
        self.assertEqual(set(hist), {"plate_number", "total_sightings", "is_watchlisted", "sightings"})
        self.assertEqual(hist["plate_number"], "GJ01AB1234")
        self.assertEqual(hist["total_sightings"], 1)
        self.assertTrue(hist["is_watchlisted"])
        self.assertEqual(
            set(hist["sightings"][0]),
            {"event_id", "camera_id", "camera_name", "timestamp",
             "latitude", "longitude", "snapshot_url", "confidence_score"},
        )


class TestPerformanceBudgets(unittest.TestCase):
    """DEVELOPER_README section 17 -- measured, with generous CI-safe ceilings."""

    def test_latency_budgets(self):
        tracker = ByteTrackTracker()
        dets = [_moving_car(0, x0=50 + 90 * i, y0=100 + 5 * i) for i in range(15)]

        # warm up
        for f in range(1, 4):
            tracker.update(dets, frame_id=f)

        t0 = time.perf_counter()
        for f in range(4, 104):
            tracker.update(dets, frame_id=f)
        per_frame_ms = (time.perf_counter() - t0) / 100 * 1000

        tracks = [{"track_id": i, "bbox": d["bbox"]} for i, d in enumerate(dets)]
        plates = [{"bbox": [d["bbox"][0] + 20, d["bbox"][1] + 40, d["bbox"][0] + 50, d["bbox"][1] + 55],
                   "plate_number": f"GJ01AB{1000 + i}", "confidence": 0.9} for i, d in enumerate(dets)]
        t0 = time.perf_counter()
        for _ in range(100):
            associate_plates_to_tracks(tracks, plates)
        assoc_ms = (time.perf_counter() - t0) / 100 * 1000

        corr = CrossCameraCorrelator()
        for i in range(200):
            corr.add_event({"plate_number": "GJ01AB1234", "camera_id": f"cam{i % 8:02d}",
                            "location": f"loc{i % 8}", "timestamp": 1_757_000_000 + i * 37,
                            "event_id": f"e{i}"})
        t0 = time.perf_counter()
        for _ in range(100):
            corr.build_trajectory("GJ01AB1234")
        sort_ms = (time.perf_counter() - t0) / 100 * 1000

        print(f"\n[perf] ByteTrack update: {per_frame_ms:.3f} ms/frame (target <5, budget "
              f"15 vehicles)\n[perf] plate<->track assoc: {assoc_ms:.3f} ms (target <2)\n"
              f"[perf] trajectory sort (200 evt): {sort_ms:.3f} ms (target <10)")

        # CI-safe upper bounds (order-of-magnitude headroom over the section-17 targets)
        self.assertLess(per_frame_ms, 50.0)
        self.assertLess(assoc_ms, 25.0)
        self.assertLess(sort_ms, 50.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
