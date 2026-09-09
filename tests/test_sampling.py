"""
PHASE 17 -- ai/sampling.py: adaptive per-camera frame sampling.
"""
import time
import unittest

from ai.degradation import SystemLoadState
from ai.scheduler import CameraPriority, DropReason
from ai.sampling import AdaptiveFrameSampler, SamplingConfig


class TestDefaultIsNoOp(unittest.TestCase):
    def test_unconfigured_camera_always_accepted(self):
        s = AdaptiveFrameSampler()
        for _ in range(20):
            d = s.should_process("cam01")
            self.assertTrue(d.accept)
            self.assertIsNone(d.effective_fps)


class TestRateLimiting(unittest.TestCase):
    def test_target_fps_enforced(self):
        s = AdaptiveFrameSampler()
        s.configure("cam01", SamplingConfig(target_fps=2.0, min_fps=2.0, max_fps=2.0))
        s.set_priority("cam01", CameraPriority.NORMAL)

        t0 = 1000.0
        first = s.should_process("cam01", now=t0)
        self.assertTrue(first.accept)
        # immediately after -- must be rejected, rate limited
        second = s.should_process("cam01", now=t0 + 0.05)
        self.assertFalse(second.accept)
        self.assertEqual(second.reason, DropReason.RATE_LIMIT)
        # after a full interval (1/2fps = 0.5s) -- accepted again
        third = s.should_process("cam01", now=t0 + 0.5)
        self.assertTrue(third.accept)

    def test_paused_camera_rejected(self):
        s = AdaptiveFrameSampler()
        s.configure("cam01", SamplingConfig(target_fps=5.0))
        d = s.should_process("cam01", paused=True)
        self.assertFalse(d.accept)
        self.assertEqual(d.reason, DropReason.CAMERA_PAUSED)


class TestPriorityInfluence(unittest.TestCase):
    def test_critical_gets_higher_effective_fps_than_background(self):
        s = AdaptiveFrameSampler()
        cfg = SamplingConfig(target_fps=10.0, min_fps=1.0, max_fps=10.0)
        s.configure("critical-cam", cfg)
        s.configure("background-cam", cfg)
        s.set_priority("critical-cam", CameraPriority.CRITICAL)
        s.set_priority("background-cam", CameraPriority.BACKGROUND)

        d_crit = s.should_process("critical-cam", now=0.0)
        d_bg = s.should_process("background-cam", now=0.0)
        self.assertGreater(d_crit.effective_fps, d_bg.effective_fps)


class TestLoadInfluence(unittest.TestCase):
    def test_overload_reduces_background_more_than_critical(self):
        s = AdaptiveFrameSampler()
        cfg = SamplingConfig(target_fps=10.0, min_fps=1.0, max_fps=10.0)
        s.configure("critical-cam", cfg)
        s.configure("background-cam", cfg)
        s.set_priority("critical-cam", CameraPriority.CRITICAL)
        s.set_priority("background-cam", CameraPriority.BACKGROUND)

        healthy_crit = s.should_process("critical-cam", now=0.0, load_state=SystemLoadState.HEALTHY).effective_fps
        overloaded_crit = s.should_process("critical-cam", now=100.0, load_state=SystemLoadState.OVERLOADED).effective_fps
        healthy_bg = s.should_process("background-cam", now=0.0, load_state=SystemLoadState.HEALTHY).effective_fps
        overloaded_bg = s.should_process("background-cam", now=100.0, load_state=SystemLoadState.OVERLOADED).effective_fps

        crit_retained = overloaded_crit / healthy_crit
        bg_retained = overloaded_bg / healthy_bg
        self.assertGreater(crit_retained, bg_retained)

    def test_critical_never_drops_below_its_own_min_fps(self):
        s = AdaptiveFrameSampler()
        s.configure("critical-cam", SamplingConfig(target_fps=10.0, min_fps=3.0, max_fps=10.0))
        s.set_priority("critical-cam", CameraPriority.CRITICAL)
        d = s.should_process("critical-cam", now=0.0, load_state=SystemLoadState.OVERLOADED)
        self.assertGreaterEqual(d.effective_fps, 3.0)


class TestMotionInfluence(unittest.TestCase):
    def test_high_activity_boosts_effective_fps(self):
        s = AdaptiveFrameSampler()
        cfg = SamplingConfig(target_fps=10.0, min_fps=1.0, max_fps=10.0, motion_influence=True, motion_boost_factor=2.0)
        s.configure("cam01", cfg)
        s.set_priority("cam01", CameraPriority.NORMAL)

        no_motion = s.should_process("cam01", now=0.0, activity_score=0.0).effective_fps
        with_motion = s.should_process("cam01", now=100.0, activity_score=0.9).effective_fps
        self.assertGreater(with_motion, no_motion)
        self.assertLessEqual(with_motion, cfg.max_fps)


if __name__ == "__main__":
    unittest.main()
