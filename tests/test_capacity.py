"""
PHASE 17 Step 10 -- ai/capacity.py: transparent capacity model.

These tests pin down the ARITHMETIC and the honesty guarantees (every
number traces to a measured baseline or a labeled assumption) -- not any
particular camera count, which is a policy choice, not a fact to assert.
"""
import unittest

from ai.capacity import CapacityAssumptions, MeasuredBaseline, compute_capacity


class TestBasicArithmetic(unittest.TestCase):
    def test_pure_detection_workload(self):
        baseline = MeasuredBaseline(worker_fps_budget=20.0, source="unit-test")
        assumptions = CapacityAssumptions(
            target_fps=2.0, anpr_percentage=0.0, redundancy_factor=1.0, headroom_pct=0.0,
        )
        est = compute_capacity(baseline, assumptions, target_cameras=100)
        # 20 fps budget / 2 fps per camera = 10 cameras/worker, no redundancy/headroom applied
        self.assertAlmostEqual(est.raw_cameras_per_worker, 10.0)
        self.assertAlmostEqual(est.effective_cameras_per_worker, 10.0)
        self.assertEqual(est.required_workers, 10)

    def test_anpr_percentage_increases_required_workers(self):
        baseline = MeasuredBaseline(worker_fps_budget=20.0, source="unit-test", anpr_cost_multiplier=4.0)
        no_anpr = compute_capacity(
            baseline, CapacityAssumptions(anpr_percentage=0.0, redundancy_factor=1.0, headroom_pct=0.0),
            target_cameras=1000,
        )
        all_anpr = compute_capacity(
            baseline, CapacityAssumptions(anpr_percentage=1.0, redundancy_factor=1.0, headroom_pct=0.0),
            target_cameras=1000,
        )
        self.assertGreater(all_anpr.required_workers, no_anpr.required_workers)

    def test_redundancy_and_headroom_reduce_effective_capacity(self):
        baseline = MeasuredBaseline(worker_fps_budget=20.0, source="unit-test")
        bare = compute_capacity(
            baseline, CapacityAssumptions(redundancy_factor=1.0, headroom_pct=0.0), target_cameras=1000,
        )
        padded = compute_capacity(
            baseline, CapacityAssumptions(redundancy_factor=1.5, headroom_pct=0.3), target_cameras=1000,
        )
        self.assertLess(padded.effective_cameras_per_worker, bare.effective_cameras_per_worker)
        self.assertGreater(padded.required_workers, bare.required_workers)


class TestHonestyGuarantees(unittest.TestCase):
    def test_gpu_estimate_absent_unless_explicitly_assumed(self):
        baseline = MeasuredBaseline(worker_fps_budget=20.0, source="unit-test")
        est = compute_capacity(baseline, CapacityAssumptions(gpu_speedup_factor=None), target_cameras=1000)
        self.assertIsNone(est.estimated_gpu_count)

    def test_gpu_estimate_flagged_unverified_when_present(self):
        baseline = MeasuredBaseline(worker_fps_budget=20.0, source="unit-test")
        est = compute_capacity(baseline, CapacityAssumptions(gpu_speedup_factor=5.0), target_cameras=1000)
        self.assertIsNotNone(est.estimated_gpu_count)
        d = est.to_dict()
        self.assertFalse(d["assumptions"]["gpu_speedup_verified"])
        self.assertTrue(any("NOT measured" in n for n in est.notes))

    def test_small_sample_baseline_is_flagged(self):
        baseline = MeasuredBaseline(worker_fps_budget=1.2, source="unit-test", measured_cameras=3)
        est = compute_capacity(baseline, target_cameras=1000)
        self.assertTrue(any("small sample" in n.lower() or "small a sample" in n.lower() or "real source of error" in n for n in est.notes))

    def test_zero_budget_never_crashes_and_is_flagged(self):
        baseline = MeasuredBaseline(worker_fps_budget=0.0, source="unit-test")
        est = compute_capacity(baseline, target_cameras=1000)
        self.assertEqual(est.raw_cameras_per_worker, 0.0)
        self.assertTrue(any("not yet achievable" in n for n in est.notes))

    def test_to_dict_never_presents_assumption_as_measured(self):
        baseline = MeasuredBaseline(worker_fps_budget=20.0, source="benchmark-run-xyz")
        est = compute_capacity(baseline, target_cameras=1000)
        d = est.to_dict()
        self.assertEqual(d["measured"]["source"], "benchmark-run-xyz")
        self.assertIn("assumptions", d)
        self.assertNotEqual(set(d["measured"].keys()) & set(d["assumptions"].keys()), set(d["measured"].keys()))


class TestRegionalAndInfra(unittest.TestCase):
    def test_workers_per_region_divides_required_workers(self):
        baseline = MeasuredBaseline(worker_fps_budget=20.0, source="unit-test")
        est = compute_capacity(baseline, CapacityAssumptions(num_regions=4), target_cameras=1000)
        self.assertGreaterEqual(est.workers_per_region * 4, est.required_workers)

    def test_bandwidth_scales_linearly_with_camera_count(self):
        baseline = MeasuredBaseline(worker_fps_budget=20.0, source="unit-test")
        est_small = compute_capacity(baseline, target_cameras=1000)
        est_big = compute_capacity(baseline, target_cameras=2000)
        self.assertAlmostEqual(est_big.estimated_ingress_bandwidth_mbps, est_small.estimated_ingress_bandwidth_mbps * 2, places=3)

    def test_storage_scales_linearly_with_camera_count(self):
        baseline = MeasuredBaseline(worker_fps_budget=20.0, source="unit-test")
        est_small = compute_capacity(baseline, target_cameras=1000)
        est_big = compute_capacity(baseline, target_cameras=2000)
        self.assertAlmostEqual(est_big.estimated_storage_gb_per_day, est_small.estimated_storage_gb_per_day * 2, places=3)


if __name__ == "__main__":
    unittest.main()
