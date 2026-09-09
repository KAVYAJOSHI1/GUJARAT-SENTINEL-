"""
PHASE 17 -- regression test for a real measurement bug this pass's own
benchmarking surfaced: psutil.Process.cpu_percent(interval=None) measures
"time since ITS OWN last call" and is unsafe to poll from more than one
independent caller at arbitrary intervals -- two callers racing reset each
other's reference point and can produce spurious, wildly inflated readings
(measured: >3000% "CPU" on an 8-core host once
ai.scheduled_consumer.ScheduledFrameConsumer started polling
AIPipeline.get_metrics() on its own timer, alongside the pre-existing
stats-loop poller). AIPipeline.get_resource_usage() now throttles the
actual psutil call and caches the result in between.
"""
import time
import unittest
from unittest import mock

from ai.pipeline import AIPipeline


class TestCpuSampleThrottling(unittest.TestCase):
    def setUp(self):
        self.p = AIPipeline(evidence_dir="tests/_tmp_resource_ev", device="cpu")

    def tearDown(self):
        import shutil
        shutil.rmtree("tests/_tmp_resource_ev", ignore_errors=True)

    def test_rapid_successive_calls_reuse_cached_value_not_repolled(self):
        if self.p._psutil_process is None:
            self.skipTest("psutil not available in this environment")
        calls = []
        real_cpu_percent = self.p._psutil_process.cpu_percent

        def spy(interval=None):
            calls.append(1)
            return real_cpu_percent(interval=interval)

        with mock.patch.object(self.p._psutil_process, "cpu_percent", side_effect=spy):
            first = self.p.get_resource_usage()
            # Simulate a SECOND independent poller (e.g. ScheduledFrameConsumer's
            # own load-state timer) hitting get_resource_usage() milliseconds
            # later -- this must NOT trigger a second real psutil call.
            second = self.p.get_resource_usage()
            third = self.p.get_resource_usage()

        self.assertEqual(len(calls), 1, "psutil.cpu_percent() was polled more than once within the throttle window")
        self.assertEqual(first["cpu_percent"], second["cpu_percent"])
        self.assertEqual(second["cpu_percent"], third["cpu_percent"])

    def test_value_refreshes_after_the_throttle_window(self):
        if self.p._psutil_process is None:
            self.skipTest("psutil not available in this environment")
        self.p._CPU_SAMPLE_MIN_INTERVAL_S = 0.05
        self.p.get_resource_usage()
        time.sleep(0.1)
        calls = []
        real_cpu_percent = self.p._psutil_process.cpu_percent

        def spy(interval=None):
            calls.append(1)
            return real_cpu_percent(interval=interval)

        with mock.patch.object(self.p._psutil_process, "cpu_percent", side_effect=spy):
            self.p.get_resource_usage()
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
