"""
PHASE 17 -- ai/modes.py: explicit AI processing modes.
"""
import unittest

from ai.modes import ModeRegistry, ProcessingMode, mode_flags
from ai.scheduler import CameraPriority


class TestModeFlags(unittest.TestCase):
    def test_detection_only_no_tracking_no_ocr(self):
        f = mode_flags(ProcessingMode.DETECTION)
        self.assertFalse(f.run_tracking)
        self.assertFalse(f.run_ocr)

    def test_tracking_no_ocr(self):
        f = mode_flags(ProcessingMode.TRACKING)
        self.assertTrue(f.run_tracking)
        self.assertFalse(f.run_ocr)

    def test_anpr_runs_everything(self):
        f = mode_flags(ProcessingMode.ANPR)
        self.assertTrue(f.run_tracking)
        self.assertTrue(f.run_ocr)

    def test_alert_runs_everything_and_defaults_critical(self):
        f = mode_flags(ProcessingMode.ALERT)
        self.assertTrue(f.run_tracking)
        self.assertTrue(f.run_ocr)
        self.assertEqual(f.default_priority, CameraPriority.CRITICAL)

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            mode_flags("SUPER_MODE")


class TestModeRegistry(unittest.TestCase):
    def test_default_mode_is_anpr_matches_pre_phase17_behavior(self):
        reg = ModeRegistry()
        self.assertEqual(reg.get_mode("any-camera"), ProcessingMode.ANPR)
        flags = reg.get_flags("any-camera")
        self.assertTrue(flags.run_tracking)
        self.assertTrue(flags.run_ocr)

    def test_per_camera_override(self):
        reg = ModeRegistry()
        reg.set_mode("cam01", ProcessingMode.DETECTION)
        self.assertEqual(reg.get_mode("cam01"), ProcessingMode.DETECTION)
        self.assertEqual(reg.get_mode("cam02"), ProcessingMode.ANPR)  # unaffected

    def test_snapshot_only_lists_overrides(self):
        reg = ModeRegistry()
        reg.set_mode("cam01", ProcessingMode.ALERT)
        self.assertEqual(reg.snapshot(), {"cam01": ProcessingMode.ALERT})


if __name__ == "__main__":
    unittest.main()
