"""
PHASE 17 -- ai/degradation.py: measurable system load states.
"""
import unittest

from ai.degradation import DegradationInputs, SystemLoadMonitor, SystemLoadState


class TestHealthy(unittest.TestCase):
    def test_no_inputs_is_healthy(self):
        report = SystemLoadMonitor().evaluate(DegradationInputs())
        self.assertEqual(report.state, SystemLoadState.HEALTHY)
        self.assertEqual(report.reasons, [])

    def test_low_cpu_is_healthy(self):
        report = SystemLoadMonitor().evaluate(DegradationInputs(cpu_percent=20.0))
        self.assertEqual(report.state, SystemLoadState.HEALTHY)


class TestDegraded(unittest.TestCase):
    def test_cpu_over_degraded_threshold(self):
        report = SystemLoadMonitor().evaluate(DegradationInputs(cpu_percent=75.0))
        self.assertEqual(report.state, SystemLoadState.DEGRADED)
        self.assertTrue(any("CPU" in r for r in report.reasons))

    def test_event_queue_backpressure(self):
        report = SystemLoadMonitor().evaluate(
            DegradationInputs(event_queue_depth=300, event_queue_maxsize=500)
        )
        self.assertEqual(report.state, SystemLoadState.DEGRADED)

    def test_missing_queue_maxsize_never_fabricates_a_ratio(self):
        report = SystemLoadMonitor().evaluate(DegradationInputs(event_queue_depth=300, event_queue_maxsize=None))
        self.assertEqual(report.state, SystemLoadState.HEALTHY)


class TestOverloaded(unittest.TestCase):
    def test_cpu_over_overloaded_threshold(self):
        report = SystemLoadMonitor().evaluate(DegradationInputs(cpu_percent=95.0))
        self.assertEqual(report.state, SystemLoadState.OVERLOADED)
        self.assertIn("Critical/alert cameras preserved at full target FPS (reduced only as a last resort)", report.actions)

    def test_starvation_rate_overloaded(self):
        report = SystemLoadMonitor().evaluate(
            DegradationInputs(starvation_events=25, frames_processed=100)
        )
        self.assertEqual(report.state, SystemLoadState.OVERLOADED)

    def test_worst_axis_wins(self):
        # CPU says degraded, queue says overloaded -- overall must be overloaded.
        report = SystemLoadMonitor().evaluate(
            DegradationInputs(cpu_percent=75.0, event_queue_depth=450, event_queue_maxsize=500)
        )
        self.assertEqual(report.state, SystemLoadState.OVERLOADED)


class TestExplain(unittest.TestCase):
    def test_explain_is_human_readable(self):
        report = SystemLoadMonitor().evaluate(DegradationInputs(cpu_percent=95.0))
        text = report.explain()
        self.assertIn("SYSTEM: OVERLOADED", text)
        self.assertIn("Reason:", text)

    def test_to_dict_roundtrip_shape(self):
        report = SystemLoadMonitor().evaluate(DegradationInputs(cpu_percent=95.0))
        d = report.to_dict()
        self.assertEqual(set(d.keys()), {"state", "reasons", "actions"})


if __name__ == "__main__":
    unittest.main()
