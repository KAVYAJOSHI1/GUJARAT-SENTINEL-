"""
PHASE 17 Step 15 -- benchmark smoke test.

Fast, deterministic checks that scripts/benchmark_phase17.py's three tiers
actually run end-to-end and produce the shape of report the docs/UI rely
on -- NOT a claim about any particular throughput number (that's what the
real, longer benchmark runs in docs/PHASE17_BENCHMARK.md are for).
"""
import os
import unittest

from scripts.benchmark_phase17 import run_decode_load, run_ingestion_simulation


class TestIngestionSimulationSmoke(unittest.TestCase):
    def test_runs_and_reports_shape(self):
        res = run_ingestion_simulation(20, duration_s=1.5, worker_fps_budget=10.0, source_fps=15.0)
        self.assertEqual(res["tier"], "SIMULATED")
        self.assertEqual(res["configured_cameras"], 20)
        self.assertGreater(res["frames_injected"], 0)
        self.assertIn("by_priority", res)
        self.assertIn("rss_growth_mb", res)

    def test_bounded_memory_at_higher_camera_count(self):
        res = run_ingestion_simulation(200, duration_s=1.5, worker_fps_budget=5.0, source_fps=15.0)
        self.assertEqual(res["configured_cameras"], 200)
        # Bounded-queue design (Step 2): RSS growth over a short run at 200
        # simulated cameras should stay small (a few MB at most), never
        # scale with frame arrival rate.
        if res["rss_growth_mb"] is not None:
            self.assertLess(res["rss_growth_mb"], 20.0)


@unittest.skipUnless(
    os.path.exists(os.path.join(os.path.dirname(__file__), "..", "trafficdataset", "Videos", "Videos")),
    "mock video dataset not present in this checkout",
)
class TestDecodeLoadSmoke(unittest.TestCase):
    def test_real_decode_of_a_couple_cameras(self):
        res = run_decode_load(2, duration_s=4.0)
        self.assertEqual(res["tier"], "DECODED")
        self.assertEqual(res["configured_cameras"], 2)
        self.assertGreaterEqual(res["active_streams"], 1)


if __name__ == "__main__":
    unittest.main()
