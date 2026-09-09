"""
PHASE 17 Step 6 -- ai/regions.py: deterministic regional simulation.
"""
import unittest

from ai.regions import REGION_NAMES, camera_region, regional_topology, topology_summary


class TestCameraRegion(unittest.TestCase):
    def test_deterministic(self):
        for cam in ("cam01", "MOCK_CAM17", "camXYZ"):
            self.assertEqual(camera_region(cam), camera_region(cam))

    def test_always_a_known_region(self):
        for i in range(50):
            r = camera_region(f"cam{i:03d}")
            self.assertIn(r, REGION_NAMES)


class TestRegionalTopology(unittest.TestCase):
    def test_every_camera_assigned_exactly_once(self):
        cams = [f"cam{i:03d}" for i in range(100)]
        topo = regional_topology(cams, workers_per_region=2)
        all_assigned = []
        for a in topo.values():
            all_assigned.extend(a.camera_ids)
        self.assertEqual(sorted(all_assigned), sorted(cams))

    def test_worker_ids_disjoint_across_regions(self):
        cams = [f"cam{i:03d}" for i in range(20)]
        topo = regional_topology(cams, workers_per_region=3)
        seen = set()
        for a in topo.values():
            for w in a.worker_ids:
                self.assertNotIn(w, seen)
                seen.add(w)

    def test_summary_is_labeled_simulated(self):
        cams = ["cam01", "cam02"]
        topo = regional_topology(cams, workers_per_region=1)
        summary = topology_summary(topo)
        self.assertIn("SIMULATED", summary["label"])
        self.assertEqual(summary["total_cameras"], 2)


if __name__ == "__main__":
    unittest.main()
