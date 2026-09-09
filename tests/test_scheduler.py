"""
PHASE 17 -- ai/scheduler.py: fair, priority-aware, bounded camera scheduler.
"""
import time
import unittest

from ai.scheduler import CameraPriority, DropReason, FairCameraScheduler


class TestBackwardCompatibleDefaults(unittest.TestCase):
    """With every camera left at the default NORMAL priority, behavior must
    exactly match ai.worker_pool.PerCameraLatestQueue (same tests as
    tests/test_worker_pool.py::TestPerCameraLatestQueue, ported)."""

    def test_bounded_one_per_camera(self):
        q = FairCameraScheduler()
        for i in range(50):
            q.put("cam01", f"frame{i}")
        self.assertEqual(q.depth(), 1)
        cam, item = q.get(timeout=0.1)
        self.assertEqual(cam, "cam01")
        self.assertEqual(item, "frame49")
        self.assertEqual(q.depth(), 0)

    def test_stale_eviction_counted(self):
        q = FairCameraScheduler()
        q.put("cam01", "a")
        q.put("cam01", "b")
        q.put("cam01", "c")
        snap = q.stale_evicted_snapshot()
        self.assertEqual(snap.get("cam01"), 2)

    def test_round_robin_fairness_equal_priority(self):
        q = FairCameraScheduler()
        cams = [f"cam{i:02d}" for i in range(5)]
        for c in cams:
            q.put(c, f"{c}-1")
        served = []
        for _ in range(5):
            cam, _ = q.get(timeout=0.1)
            served.append(cam)
        self.assertEqual(served, cams)

    def test_get_returns_none_on_empty_timeout(self):
        q = FairCameraScheduler()
        t0 = time.monotonic()
        result = q.get(timeout=0.2)
        self.assertIsNone(result)
        self.assertGreaterEqual(time.monotonic() - t0, 0.15)


class TestPriorityWeighting(unittest.TestCase):
    def test_critical_served_more_often_than_background(self):
        q = FairCameraScheduler()
        q.set_priority("critical-cam", CameraPriority.CRITICAL)
        q.set_priority("background-cam", CameraPriority.BACKGROUND)

        served = {"critical-cam": 0, "background-cam": 0}
        for _ in range(60):
            # both cameras always have a pending frame available
            q.put("critical-cam", "x")
            q.put("background-cam", "x")
            cam, _ = q.get(timeout=0.5)
            served[cam] += 1

        self.assertGreater(served["critical-cam"], served["background-cam"])
        # background must still make some progress -- never fully starved
        # by construction (SWRR always includes every non-empty bucket).
        self.assertGreater(served["background-cam"], 0)

    def test_one_busy_camera_cannot_starve_others_fairness_test(self):
        """Phase 17 Step 9: a busy/heavy camera flooding puts at the same
        priority as several normal cameras must not starve them."""
        q = FairCameraScheduler()
        normal_cams = [f"normal{i}" for i in range(4)]
        busy_cam = "busy0"

        served = {c: 0 for c in normal_cams + [busy_cam]}
        for round_ in range(40):
            q.put(busy_cam, f"f{round_}")   # flooding camera
            if round_ % 3 == 0:
                for c in normal_cams:
                    q.put(c, f"f{round_}")
            got = q.get(timeout=0.5)
            if got:
                served[got[0]] += 1

        for c in normal_cams:
            self.assertGreater(served[c], 0, f"{c} was starved by the busy camera")

    def test_unknown_priority_rejected(self):
        q = FairCameraScheduler()
        with self.assertRaises(ValueError):
            q.set_priority("cam01", "SUPER_URGENT")


class TestBoundedQueueDepth(unittest.TestCase):
    def test_depth_greater_than_one_drops_oldest_with_reason(self):
        q = FairCameraScheduler(max_queue_depth=3)
        for i in range(6):
            q.put("cam01", f"frame{i}")
        snap = q.snapshot()
        cam_stats = snap["cameras"]["cam01"]
        self.assertEqual(cam_stats["frames_dropped"].get(DropReason.QUEUE_FULL, 0), 3)
        self.assertLessEqual(cam_stats["queue_depth"], 3)


class TestStatsSnapshot(unittest.TestCase):
    def test_snapshot_shape(self):
        q = FairCameraScheduler()
        q.set_priority("cam01", CameraPriority.HIGH)
        q.set_target_fps("cam01", 5.0)
        q.put("cam01", "x")
        q.get(timeout=0.1)

        snap = q.snapshot()
        self.assertIn("cam01", snap["cameras"])
        cam = snap["cameras"]["cam01"]
        self.assertEqual(cam["priority"], CameraPriority.HIGH)
        self.assertEqual(cam["target_fps"], 5.0)
        self.assertEqual(cam["frames_received"], 1)
        self.assertEqual(cam["frames_processed"], 1)
        self.assertIsNotNone(cam["last_processed_ts"])
        self.assertEqual(snap["active_cameras"], 1)
        self.assertEqual(snap["totals"]["frames_processed"], 1)

    def test_record_drop_before_put(self):
        q = FairCameraScheduler()
        q.record_drop("cam01", DropReason.RATE_LIMIT)
        snap = q.snapshot()
        self.assertEqual(snap["cameras"]["cam01"]["frames_dropped"].get(DropReason.RATE_LIMIT), 1)


class TestStarvation(unittest.TestCase):
    def test_starvation_counted_when_threshold_exceeded(self):
        # A genuinely fair scheduler (this one) will always serve a pending
        # camera within one scheduling round, so "neglected past the
        # threshold" can't be reproduced by simply not calling get() often
        # enough -- it would just get served. Instead, verify the actual
        # bookkeeping invariant directly: a camera whose frame has been
        # pending since before the threshold gets counted as starved the
        # next time the scheduler's internal accounting runs (on any get()
        # call), even though it hasn't itself been served yet.
        q = FairCameraScheduler(starvation_threshold_s=0.05)
        q.set_priority("neglected", CameraPriority.BACKGROUND)
        q.set_priority("other", CameraPriority.CRITICAL)
        q.put("neglected", "x")
        q._stats["neglected"].pending_since_mono = time.monotonic() - 10.0

        q.put("other", "y")
        q.get(timeout=0.2)  # CRITICAL outweighs BACKGROUND on this call -> serves "other"

        snap = q.snapshot()
        self.assertGreater(snap["cameras"]["neglected"]["starvation_count"], 0)
        # "neglected" is still pending -- fairness didn't silently drop it.
        self.assertEqual(snap["cameras"]["neglected"]["frames_processed"], 0)


if __name__ == "__main__":
    unittest.main()
