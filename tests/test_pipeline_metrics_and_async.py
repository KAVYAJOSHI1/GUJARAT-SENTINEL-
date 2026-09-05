"""
PHASE 2A — pipeline observability + async event delivery.

Covers:
  * metrics collection (get_metrics() structure + counters actually increment)
  * queue-full / backpressure behavior (bounded queue, drops counted, the
    inference hot path never blocks on a wedged sender)
  * async sender retry/failure (5xx-style "retry" -> buffered + delivered on
    flush; 4xx-style "drop" -> counted, never retried forever; an exception
    inside dispatch must not kill the sender thread)
  * graceful shutdown/drain (every enqueued event is accounted for: either
    delivered or moved to the retry buffer, never silently lost)
  * no event-schema regression (process_frame()'s returned event dict, and
    what eventually reaches _dispatch_event, are unchanged by the refactor
    that moved dispatch off the inference thread)
"""
import os
import shutil
import threading
import time
import unittest

import numpy as np

from ai.pipeline import AIPipeline


def _box(cx, cy, w=100, h=80):
    return [int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2)]


def _make_pipeline(evidence_dir: str, queue_size: int = None) -> AIPipeline:
    if queue_size is not None:
        os.environ["SENTINEL_EVENT_QUEUE_SIZE"] = str(queue_size)
    else:
        os.environ.pop("SENTINEL_EVENT_QUEUE_SIZE", None)
    pipe = AIPipeline(evidence_dir=evidence_dir, device="cpu")
    pipe.multivariant_ocr = False  # deterministic single-pass OCR stubbing
    return pipe


def _wait_until(predicate, timeout=3.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class TestEventSchemaUnchanged(unittest.TestCase):
    """The async hand-off must not change what process_frame() returns, or
    what eventually reaches the backend -- only WHEN/how it's sent."""

    EV_DIR = "tests/_tmp_metrics_ev1"

    def setUp(self):
        self.pipe = _make_pipeline(self.EV_DIR)
        self.pipe.vehicle_detector.detect = lambda frame: [
            {"bbox": _box(200, 240), "confidence": 0.91, "class": "car"}
        ]
        self.pipe.ocr_engine.extract_text = lambda img: {"raw_text": "GJ01AB1234", "confidence": 0.9}
        self.sent_payloads = []
        self.pipe._dispatch_event = lambda payload: (self.sent_payloads.append(payload) or True)

    def tearDown(self):
        self.pipe.shutdown(drain_timeout=3)
        shutil.rmtree(self.EV_DIR, ignore_errors=True)

    def test_returned_event_schema_unchanged(self):
        evs = self.pipe.process_frame(
            np.full((480, 640, 3), 110, np.uint8), camera_id="cam04", frame_timestamp="2026-09-05T09:00:00Z"
        )
        self.assertEqual(len(evs), 1)
        e = evs[0]
        expected_keys = {
            "event_id", "timestamp", "pts", "camera_id", "camera_name", "track_id",
            "latitude", "longitude", "seq_num", "vehicle", "license_plate", "evidence",
        }
        self.assertEqual(set(e.keys()), expected_keys, "event top-level shape must be unchanged")
        self.assertEqual(e["camera_id"], "cam04")
        self.assertEqual(e["license_plate"]["plate_number"], "GJ01AB1234")

    def test_dispatched_payload_matches_returned_event(self):
        """What eventually reaches _dispatch_event (and therefore the wire)
        must be exactly the same dict process_frame() returned -- proves
        the async hand-off doesn't mutate or add fields in transit."""
        evs = self.pipe.process_frame(
            np.full((480, 640, 3), 110, np.uint8), camera_id="cam04", frame_timestamp="2026-09-05T09:05:00Z"
        )
        self.assertTrue(_wait_until(lambda: len(self.sent_payloads) >= 1))
        self.assertEqual(len(self.sent_payloads), 1)
        self.assertEqual(self.sent_payloads[0], evs[0])


class TestMetricsCollection(unittest.TestCase):
    EV_DIR = "tests/_tmp_metrics_ev2"

    def setUp(self):
        self.pipe = _make_pipeline(self.EV_DIR)
        self.pipe._dispatch_event = lambda payload: True

    def tearDown(self):
        self.pipe.shutdown(drain_timeout=3)
        shutil.rmtree(self.EV_DIR, ignore_errors=True)

    def test_metrics_structure_and_empty_state_reports_null_not_fake_zero(self):
        m = self.pipe.get_metrics()
        for key in (
            "event_queue_depth", "event_queue_max_depth", "event_queue_maxsize",
            "events_enqueued", "events_sent_ok", "events_dropped_queue_full",
            "events_dropped_backend_rejected", "events_dropped_buffer_full",
            "events_buffered_for_retry", "yolo_latency_ms", "ocr_latency_ms",
            "send_latency_ms", "compute_latency_ms", "end_to_end_latency_ms",
            "frames_by_camera", "events_by_camera", "resource_usage",
        ):
            self.assertIn(key, m, f"get_metrics() missing expected key {key!r}")
        # No samples yet -> None, never a fabricated number.
        self.assertEqual(m["yolo_latency_ms"]["count"], 0)
        self.assertIsNone(m["yolo_latency_ms"]["p95_ms"])
        self.assertIsNone(m["ocr_latency_ms"]["avg_ms"])

    def test_per_camera_frame_and_event_counts(self):
        self.pipe.vehicle_detector.detect = lambda frame: [
            {"bbox": _box(200, 240), "confidence": 0.9, "class": "car"}
        ]
        self.pipe.ocr_engine.extract_text = lambda img: {"raw_text": "GJ01AB1234", "confidence": 0.9}
        frame = np.full((480, 640, 3), 110, np.uint8)
        self.pipe.process_frame(frame, camera_id="cam04", frame_timestamp="t1")
        self.pipe.process_frame(frame, camera_id="cam06", frame_timestamp="t2")
        self.pipe.process_frame(frame, camera_id="cam06", frame_timestamp="t3")
        m = self.pipe.get_metrics()
        self.assertEqual(m["frames_by_camera"]["cam04"], 1)
        self.assertEqual(m["frames_by_camera"]["cam06"], 2)
        # One event per (camera, track, plate) -- existing dedup is unaffected.
        self.assertEqual(m["events_by_camera"]["cam04"], 1)
        self.assertEqual(m["events_by_camera"]["cam06"], 1)

    def test_yolo_and_ocr_latency_samples_recorded_with_monotonic_durations(self):
        self.pipe.vehicle_detector.detect = lambda frame: [
            {"bbox": _box(200, 240), "confidence": 0.9, "class": "car"}
        ]
        self.pipe.ocr_engine.extract_text = lambda img: {"raw_text": "GJ01AB1234", "confidence": 0.9}
        frame = np.full((480, 640, 3), 110, np.uint8)
        self.pipe.process_frame(frame, camera_id="cam04", frame_timestamp="t1")
        m = self.pipe.get_metrics()
        self.assertEqual(m["yolo_latency_ms"]["count"], 1)
        self.assertGreaterEqual(m["yolo_latency_ms"]["avg_ms"], 0.0)
        self.assertEqual(m["ocr_latency_ms"]["count"], 1)


class TestQueueBackpressure(unittest.TestCase):
    EV_DIR = "tests/_tmp_metrics_ev3"

    def setUp(self):
        self.pipe = _make_pipeline(self.EV_DIR, queue_size=2)
        self.pipe.vehicle_detector.detect = lambda frame: [
            {"bbox": _box(200, 240), "confidence": 0.9, "class": "car"}
        ]
        self.dispatch_gate = threading.Event()  # left unset -> dispatch blocks until released
        self.dispatch_calls = []

        def blocking_dispatch(payload):
            self.dispatch_calls.append(payload["event_id"])
            self.dispatch_gate.wait(timeout=5)
            return True

        self.pipe._dispatch_event = blocking_dispatch

    def tearDown(self):
        self.dispatch_gate.set()
        self.pipe.shutdown(drain_timeout=3)
        shutil.rmtree(self.EV_DIR, ignore_errors=True)

    def test_hot_path_never_blocks_and_overflow_is_reported_not_silent(self):
        frame = np.full((480, 640, 3), 110, np.uint8)
        t0 = time.time()
        for i in range(6):
            plate = f"GJ01AB{1000 + i}"
            self.pipe.ocr_engine.extract_text = lambda img, plate=plate: {"raw_text": plate, "confidence": 0.9}
            self.pipe.process_frame(frame, camera_id="camX", frame_timestamp=f"t{i}")
        elapsed = time.time() - t0
        # 6 calls against a sender that blocks indefinitely must still
        # return near-instantly -- this is the entire point of Task 2.
        self.assertLess(elapsed, 1.0, f"hot path blocked for {elapsed:.2f}s -- should be near-instant")

        m = self.pipe.get_metrics()
        self.assertEqual(m["events_enqueued"] + m["events_dropped_queue_full"], 6)
        self.assertGreater(m["events_dropped_queue_full"], 0, "queue should have overflowed with maxsize=2")
        self.assertLessEqual(m["event_queue_max_depth"], 2)
        self.assertLessEqual(m["event_queue_depth"], 2)

        # release the wedged sender so tearDown's shutdown doesn't have to
        # wait out its full drain_timeout
        self.dispatch_gate.set()


class TestAsyncSenderRetryAndFailure(unittest.TestCase):
    EV_DIR = "tests/_tmp_metrics_ev4"

    def setUp(self):
        self.pipe = _make_pipeline(self.EV_DIR)
        self.pipe.vehicle_detector.detect = lambda frame: [
            {"bbox": _box(200, 240), "confidence": 0.9, "class": "car"}
        ]
        self.pipe.ocr_engine.extract_text = lambda img: {"raw_text": "GJ01AB1234", "confidence": 0.9}

    def tearDown(self):
        self.pipe.shutdown(drain_timeout=3)
        shutil.rmtree(self.EV_DIR, ignore_errors=True)

    def test_retry_outcome_buffers_event_and_flush_delivers_it(self):
        outcomes = iter(["retry", "ok"])  # backend down once, then recovers
        calls = []

        def fake_post_one(payload):
            calls.append(payload)
            return next(outcomes, "ok")

        self.pipe._post_one = fake_post_one
        frame = np.full((480, 640, 3), 110, np.uint8)
        self.pipe.process_frame(frame, camera_id="cam04", frame_timestamp="t1")

        self.assertTrue(_wait_until(lambda: len(calls) >= 1))
        remaining = self.pipe.flush_events()
        self.assertEqual(remaining, 0, "a buffered event must be retried and delivered on flush_events()")

    def test_backend_rejection_is_counted_and_never_retried_forever(self):
        self.pipe._post_one = lambda payload: "drop"
        frame = np.full((480, 640, 3), 110, np.uint8)
        self.pipe.process_frame(frame, camera_id="cam04", frame_timestamp="t1")
        self.pipe.flush_events()
        m = self.pipe.get_metrics()
        self.assertEqual(m["events_dropped_backend_rejected"], 1)
        self.assertEqual(m["events_buffered_for_retry"], 0, "a 4xx-rejected event must never sit in the retry buffer")

    def test_sender_thread_survives_an_exception_in_dispatch(self):
        """An unexpected exception inside dispatch must not kill the sender
        thread -- a later event must still be delivered. Uses two different
        cameras (each gets its own fresh ByteTrack tracker/track_id=1) so
        both calls unambiguously emit an event, independent of any
        IoU/motion-prediction tracking judgment call."""
        calls = []

        def flaky(payload):
            calls.append(payload["event_id"])
            if len(calls) == 1:
                raise RuntimeError("boom")
            return True

        self.pipe._dispatch_event = flaky
        frame = np.full((480, 640, 3), 110, np.uint8)
        evs1 = self.pipe.process_frame(frame, camera_id="cam04", frame_timestamp="t1")
        self.assertEqual(len(evs1), 1)

        self.pipe.ocr_engine.extract_text = lambda img: {"raw_text": "GJ02CD5678", "confidence": 0.9}
        evs2 = self.pipe.process_frame(frame, camera_id="cam06", frame_timestamp="t2")
        self.assertEqual(len(evs2), 1)

        self.assertTrue(_wait_until(lambda: len(calls) >= 2))
        self.assertEqual(len(calls), 2, "sender thread must keep processing after one event raises")
        self.assertTrue(self.pipe._sender_thread.is_alive())


class TestGracefulShutdown(unittest.TestCase):
    EV_DIR = "tests/_tmp_metrics_ev5"

    def tearDown(self):
        shutil.rmtree(self.EV_DIR, ignore_errors=True)

    def test_shutdown_accounts_for_every_enqueued_event(self):
        pipe = _make_pipeline(self.EV_DIR, queue_size=50)
        pipe.vehicle_detector.detect = lambda frame: [
            {"bbox": _box(200, 240), "confidence": 0.9, "class": "car"}
        ]
        delivered = []

        def slow_ok(payload):
            time.sleep(0.05)
            delivered.append(payload["event_id"])
            return True

        pipe._dispatch_event = slow_ok

        frame = np.full((480, 640, 3), 110, np.uint8)
        for i in range(5):
            plate = f"GJ01AB{2000 + i}"
            pipe.ocr_engine.extract_text = lambda img, plate=plate: {"raw_text": plate, "confidence": 0.9}
            pipe.process_frame(frame, camera_id="camY", frame_timestamp=f"t{i}")

        remaining = pipe.shutdown(drain_timeout=5.0)
        # Every event handed to the queue must be accounted for: either
        # actually delivered, or moved into the retry buffer -- never just
        # gone (Task 2 "graceful shutdown/drain").
        self.assertEqual(len(delivered) + remaining, 5)
        self.assertFalse(pipe._sender_thread.is_alive())


if __name__ == "__main__":
    unittest.main(verbosity=2)
