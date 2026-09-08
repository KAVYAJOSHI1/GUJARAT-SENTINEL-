"""
Phase 15E -- pipeline-side VehicleEmbedder (optional real CNN embedding).
"""
import unittest

import numpy as np

from ai.reid.embed import VehicleEmbedder


class TestVehicleEmbedder(unittest.TestCase):
    def test_disabled_by_default(self):
        e = VehicleEmbedder(enabled=None)
        # env not set -> disabled
        self.assertIn(e.enabled, (True, False))
        if not e.enabled:
            self.assertIsNone(e.embed_bgr(np.zeros((80, 120, 3), np.uint8)))

    def test_status_shape(self):
        s = VehicleEmbedder(enabled=False).status()
        for k in ("enabled", "loaded", "failed", "model", "device", "dim"):
            self.assertIn(k, s)
        self.assertFalse(s["enabled"])
        self.assertIn(s["model"], ("torch-mobilenetv3s-imagenet", "torch-resnet50-imagenet"))

    def test_bad_input_returns_none(self):
        e = VehicleEmbedder(enabled=True)
        self.assertIsNone(e.embed_bgr(None))
        self.assertIsNone(e.embed_bgr(np.zeros((0, 0, 3), np.uint8)))

    def test_enabled_embedder_produces_normalised_vector(self):
        import math
        try:
            import torch  # noqa: F401
            import torchvision  # noqa: F401
            from PIL import Image  # noqa: F401
        except Exception:  # noqa: BLE001
            self.skipTest("torch/torchvision/PIL not available")
        e = VehicleEmbedder(model_key="mobilenet_v3_small", enabled=True)
        crop = np.random.default_rng(2).integers(0, 255, (110, 180, 3)).astype("uint8")
        vec = e.embed_bgr(crop)
        self.assertIsNotNone(vec)
        self.assertEqual(len(vec), 576)
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in vec)), 1.0, places=4)


if __name__ == "__main__":
    unittest.main()
