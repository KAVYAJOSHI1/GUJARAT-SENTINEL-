"""
PHASE 17 Step 4 -- ai/ocr_executor.py + AIPipeline's opt-in async OCR path
(SENTINEL_ASYNC_OCR=1).

Verifies the actual principle at stake: "ANPR/OCR must not block the
entire camera processing pipeline" -- detection/tracking must keep making
progress on OTHER frames while a bounded number of OCR jobs are in
flight, drops are counted (never silent / unbounded), and results
eventually apply and dispatch through the exact same event schema as the
synchronous path.
"""
import os
import time
import unittest

import numpy as np

from ai.ocr_executor import OCRExecutor, OCRJob
from ai.pipeline import AIPipeline


def _box(cx, cy, w=90, h=70):
    return [int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2)]


class TestOCRExecutorStandalone(unittest.TestCase):
    def test_submit_and_poll_results(self):
        def ocr_fn(crop):
            return {"raw_text": "GJ01AB1234", "confidence": 0.9}

        ex = OCRExecutor(ocr_fn, max_queue=4, num_threads=1)
        try:
            ex.submit(OCRJob(camera_id="cam01", track_id=1, track_key="cam01:1", plate_crop=np.zeros((10, 10, 3))))
            deadline = time.monotonic() + 3.0
            results = []
            while time.monotonic() < deadline and not results:
                results = ex.poll_results()
                time.sleep(0.02)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].raw_text, "GJ01AB1234")
            self.assertEqual(ex.metrics()["completed"], 1)
        finally:
            ex.shutdown()

    def test_bounded_queue_drops_are_counted(self):
        gate = threading_event = __import__("threading").Event()

        def slow_ocr_fn(crop):
            gate.wait(timeout=2.0)
            return {"raw_text": "UNKNOWN", "confidence": 0.0}

        ex = OCRExecutor(slow_ocr_fn, max_queue=2, num_threads=1)
        try:
            accepted = 0
            for i in range(10):
                ok = ex.submit(OCRJob(camera_id="cam01", track_id=i, track_key=f"cam01:{i}", plate_crop=None))
                accepted += int(ok)
            self.assertLess(accepted, 10)
            self.assertGreater(ex.metrics()["dropped_queue_full"], 0)
        finally:
            gate.set()
            ex.shutdown()

    def test_a_bad_crop_does_not_kill_the_worker_thread(self):
        def flaky_ocr_fn(crop):
            if crop is None:
                raise ValueError("boom")
            return {"raw_text": "OK", "confidence": 1.0}

        ex = OCRExecutor(flaky_ocr_fn, max_queue=4, num_threads=1)
        try:
            ex.submit(OCRJob(camera_id="cam01", track_id=1, track_key="cam01:1", plate_crop=None))
            ex.submit(OCRJob(camera_id="cam01", track_id=2, track_key="cam01:2", plate_crop="not-none"))
            deadline = time.monotonic() + 3.0
            results = []
            while time.monotonic() < deadline and len(results) < 2:
                results.extend(ex.poll_results())
                time.sleep(0.02)
            self.assertEqual(len(results), 2)
            errored = [r for r in results if r.error]
            ok = [r for r in results if not r.error]
            self.assertEqual(len(errored), 1)
            self.assertEqual(len(ok), 1)
            self.assertEqual(ex.metrics()["errors"], 1)
        finally:
            ex.shutdown()


class TestAsyncOCRPipelineIntegration(unittest.TestCase):
    """Real AIPipeline, real threads, stubbed OCR engine (deterministic,
    slow enough to prove non-blocking, no model load)."""

    def setUp(self):
        os.environ["SENTINEL_ASYNC_OCR"] = "1"
        os.environ["SENTINEL_OCR_QUEUE_SIZE"] = "8"
        self.p = AIPipeline(evidence_dir="tests/_tmp_async_ocr_ev", device="cpu")
        self._dets = []
        self.p.vehicle_detector.detect = lambda frame: list(self._dets)
        self.p.multivariant_ocr = False
        self.p._dispatch_event = lambda payload: True

        def slow_extract_text(img):
            time.sleep(0.15)  # slower than a YOLO call -- the actual bottleneck being tested
            return {"raw_text": "GJ01AB1234", "confidence": 0.9}

        self.p.ocr_engine.extract_text = slow_extract_text

    def tearDown(self):
        self.p.shutdown(drain_timeout=3.0)
        os.environ.pop("SENTINEL_ASYNC_OCR", None)
        os.environ.pop("SENTINEL_OCR_QUEUE_SIZE", None)
        import shutil
        shutil.rmtree("tests/_tmp_async_ocr_ev", ignore_errors=True)

    def _frame(self, dets, camera_id, ts):
        self._dets = dets
        f = np.full((480, 640, 3), 120, np.uint8)
        return self.p.process_frame(f, camera_id=camera_id, frame_timestamp=ts)

    def test_pipeline_reports_async_ocr_enabled(self):
        self.assertTrue(self.p.async_ocr)
        self.assertIsNotNone(self.p._ocr_executor)
        self.assertTrue(self.p.get_metrics()["async_ocr_enabled"])

    def test_detection_keeps_progressing_while_ocr_is_in_flight(self):
        """The core claim: submitting a slow OCR job for cam A must not
        stall processing of cam B's very next frame."""
        t0 = time.monotonic()
        dets_a = [{"bbox": _box(100, 150), "confidence": 0.9, "class": "car"}]
        self._frame(dets_a, "camA", "2026-09-09T09:00:00Z")  # submits OCR job, returns immediately
        elapsed_first = time.monotonic() - t0

        t1 = time.monotonic()
        dets_b = [{"bbox": _box(200, 250), "confidence": 0.9, "class": "car"}]
        self._frame(dets_b, "camB", "2026-09-09T09:00:00Z")  # must NOT wait on camA's OCR
        elapsed_second = time.monotonic() - t1

        # Both calls return well under the 150ms OCR stub latency -- proof
        # that camB's frame wasn't blocked behind camA's in-flight OCR job.
        self.assertLess(elapsed_first, 0.1)
        self.assertLess(elapsed_second, 0.1)

    def test_result_eventually_applies_and_dispatches_full_event(self):
        dets = [{"bbox": _box(100, 150), "confidence": 0.9, "class": "car"}]
        events_first = self._frame(dets, "camA", "2026-09-09T09:00:00Z")
        # Nothing emitted yet for THIS frame -- OCR job is in flight.
        self.assertEqual(events_first, [])

        deadline = time.monotonic() + 3.0
        found = None
        while time.monotonic() < deadline and found is None:
            # Draining happens at the top of process_frame -- feed more
            # frames (any camera) to give the pipeline a chance to drain.
            drained = self._frame(dets, "camA", "2026-09-09T09:00:01Z")
            if drained:
                found = drained[0]
            time.sleep(0.05)

        self.assertIsNotNone(found, "async OCR result never applied/dispatched")
        self.assertEqual(found["license_plate"]["plate_number"], "GJ01AB1234")
        self.assertIn("anpr", found)
        self.assertIn("evidence", found)

    def test_queue_full_falls_back_without_blocking(self):
        # Flood many distinct tracks (=> many distinct OCR jobs) faster
        # than the slow stub can drain -- the bounded queue must fill and
        # start reporting drops, never grow unboundedly or block.
        for i in range(40):
            dets = [{"bbox": _box(100 + i, 150), "confidence": 0.9, "class": "car"}]
            self._frame(dets, "camFlood", f"2026-09-09T09:00:{i:02d}Z")
        metrics = self.p.get_metrics()
        self.assertGreaterEqual(metrics["ocr_executor"]["queue_depth"], 0)
        self.assertLessEqual(metrics["ocr_executor"]["queue_depth"], metrics["ocr_executor"]["queue_maxsize"])
        # Either the executor's own bounded queue dropped some, or the
        # pipeline's own submit() call reported a full queue -- one of the
        # two MUST have engaged, given 40 distinct tracks vs an 8-slot queue
        # and a 150ms-per-job stub.
        self.assertTrue(
            metrics["ocr_executor"]["dropped_queue_full"] > 0 or metrics["ocr_dropped_queue_full"] > 0
        )


if __name__ == "__main__":
    unittest.main()
