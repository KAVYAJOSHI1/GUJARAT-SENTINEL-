"""
PHASE 2C — parallel AI processing + fair camera scheduling.

Covers:
  * camera_worker_index() is deterministic and stable (never Python's
    randomized hash()) and spreads cameras across workers.
  * PerCameraLatestQueue: bounded memory (one resident item per camera),
    fair round-robin service order, stale-frame eviction is counted (never
    silently dropped).
  * AIWorkerPool end-to-end (real subprocesses, stubbed pipeline_factory so
    no YOLO/EasyOCR model load is required): frames for a given camera are
    only ever seen by the one worker that owns it, metrics aggregate across
    workers, and shutdown() terminates cleanly without hanging.
"""
import multiprocessing
import queue
import time
import unittest

from ai.worker_pool import AIWorkerPool, PerCameraLatestQueue, camera_worker_index


def _compute_indices_in_subprocess(cams, n, out_q):
    """Module-level (picklable) target for the cross-process determinism
    check below -- a spawn-context Process target must be importable by
    reference, not a local closure."""
    out_q.put([camera_worker_index(c, n) for c in cams])


class TestCameraWorkerIndex(unittest.TestCase):
    def test_single_worker_always_zero(self):
        for cam in ("cam01", "MOCK_CAM17", "anything"):
            self.assertEqual(camera_worker_index(cam, 1), 0)
            self.assertEqual(camera_worker_index(cam, 0), 0)

    def test_deterministic_across_calls(self):
        cams = [f"cam{i:02d}" for i in range(30)]
        first = [camera_worker_index(c, 4) for c in cams]
        second = [camera_worker_index(c, 4) for c in cams]
        self.assertEqual(first, second)

    def test_deterministic_across_processes(self):
        # This is the property that actually matters: PYTHONHASHSEED is
        # randomized per-process by default, so if this used Python's
        # built-in hash() a camera could land on a different worker in a
        # freshly spawned process than in the parent -- silently breaking
        # the "a camera's frames never touch two workers" guarantee.
        ctx = multiprocessing.get_context("spawn")
        q = ctx.Queue()

        cams = [f"cam{i:02d}" for i in range(10)]
        p = ctx.Process(target=_compute_indices_in_subprocess, args=(cams, 4, q))
        p.start()
        child_result = q.get(timeout=10)
        p.join(timeout=5)
        parent_result = [camera_worker_index(c, 4) for c in cams]
        self.assertEqual(child_result, parent_result)

    def test_spreads_across_workers(self):
        cams = [f"MOCK_CAM{i:02d}" for i in range(1, 31)]
        assignment = {c: camera_worker_index(c, 4) for c in cams}
        used = set(assignment.values())
        # 30 cameras across 4 workers should not all collapse onto one
        # worker -- not a strict balance guarantee, just "actually shards".
        self.assertGreater(len(used), 1)
        for idx in used:
            self.assertGreaterEqual(idx, 0)
            self.assertLess(idx, 4)


class TestPerCameraLatestQueue(unittest.TestCase):
    def test_bounded_one_per_camera(self):
        q = PerCameraLatestQueue()
        for i in range(50):
            q.put("cam01", f"frame{i}")
        self.assertEqual(q.depth(), 1)  # only one distinct camera pending
        cam, item = q.get(timeout=0.1)
        self.assertEqual(cam, "cam01")
        self.assertEqual(item, "frame49")  # latest wins, not FIFO backlog
        self.assertEqual(q.depth(), 0)

    def test_stale_eviction_counted(self):
        q = PerCameraLatestQueue()
        q.put("cam01", "a")
        q.put("cam01", "b")  # "a" never consumed -> stale eviction
        q.put("cam01", "c")
        snap = q.stale_evicted_snapshot()
        self.assertEqual(snap.get("cam01"), 2)

    def test_round_robin_fairness(self):
        q = PerCameraLatestQueue()
        cams = [f"cam{i:02d}" for i in range(5)]
        for c in cams:
            q.put(c, f"{c}-1")
        # every camera should be served once, in first-arrival order,
        # before any camera is served a second time
        served = []
        for _ in range(5):
            cam, _ = q.get(timeout=0.1)
            served.append(cam)
        self.assertEqual(served, cams)

    def test_get_returns_none_on_empty_timeout(self):
        q = PerCameraLatestQueue()
        t0 = time.monotonic()
        result = q.get(timeout=0.2)
        self.assertIsNone(result)
        self.assertGreaterEqual(time.monotonic() - t0, 0.15)


class _FakePipeline:
    """Picklable-by-reference stand-in for ai.pipeline.AIPipeline: no model
    load, near-instant process_frame(), records which camera_ids it saw so
    the test can assert isolation (a camera's frames only ever reach the
    one worker/pipeline instance that owns it)."""

    def __init__(self, **kwargs):
        self.frames_by_camera: dict = {}

    def process_frame(self, frame_input):
        cam = getattr(frame_input, "camera_id", None)
        self.frames_by_camera[cam] = self.frames_by_camera.get(cam, 0) + 1
        return []

    def get_metrics(self):
        return {
            "total_ai_events_generated": 0, "events_sent_ok": 0,
            "events_dropped_queue_full": 0, "events_dropped_backend_rejected": 0,
            "events_dropped_buffer_full": 0, "events_buffered_for_retry": 0,
            "event_queue_max_depth": 0,
            "frames_by_camera": dict(self.frames_by_camera), "events_by_camera": {},
            "resource_usage": {"cpu_percent": 0.0, "rss_mb": 0.0},
        }

    def shutdown(self, drain_timeout=5.0):
        return 0


def _fake_pipeline_factory(**kwargs):
    return _FakePipeline(**kwargs)


class _FakeEnvelope:
    def __init__(self, camera_id, seq):
        self.camera_id = camera_id
        self.seq = seq
        self.frame = None
        self.timestamp = None
        self.pts = None
        self.width = 640
        self.height = 480


class TestAIWorkerPoolIntegration(unittest.TestCase):
    """Real subprocesses, stubbed pipeline -- exercises the actual routing/
    sharding/shutdown code paths without paying YOLO/EasyOCR's load cost."""

    def test_camera_isolation_and_shutdown(self):
        ctx = multiprocessing.get_context("spawn")
        frame_queue = ctx.Queue(maxsize=500)
        camera_ids = [f"cam{i:02d}" for i in range(6)]

        pool = AIWorkerPool(
            frame_queue, camera_ids, num_workers=2,
            backend_url="http://unused", ingest_api_key=None,
            evidence_dir="/tmp/sentinel_test_worker_pool_evidence",
            device="cpu", no_backend=True, stats_interval=1.0,
            pipeline_factory=_fake_pipeline_factory,
        )
        try:
            # Every camera assigned to exactly one worker; disjoint sets.
            assigned_sets = [set(w.camera_ids) for w in pool.workers]
            all_assigned = set().union(*assigned_sets)
            self.assertEqual(all_assigned, set(camera_ids))
            for i in range(len(assigned_sets)):
                for j in range(i + 1, len(assigned_sets)):
                    self.assertEqual(assigned_sets[i] & assigned_sets[j], set())

            pool.start()

            seq = 0
            t0 = time.monotonic()
            while time.monotonic() - t0 < 6.0:
                for cam in camera_ids:
                    try:
                        frame_queue.put(_FakeEnvelope(cam, seq), timeout=0.5)
                    except queue.Full:
                        pass
                seq += 1
                time.sleep(0.05)

            deadline = time.monotonic() + 5.0
            metrics = None
            while time.monotonic() < deadline:
                metrics = pool.get_metrics()
                if metrics["processed_frames"] > 0:
                    break
                time.sleep(0.5)

            self.assertIsNotNone(metrics)
            self.assertGreater(metrics["processed_frames"], 0)
            # Every camera that got any frames must be attributed to it by
            # camera_id, and only cameras assigned to this pool appear.
            for cam in metrics["frames_by_camera"]:
                self.assertIn(cam, camera_ids)
        finally:
            pool.shutdown(timeout=10)
            for w in pool.workers:
                self.assertFalse(w.process.is_alive())

    def test_single_worker_default_matches_index_zero(self):
        ctx = multiprocessing.get_context("spawn")
        frame_queue = ctx.Queue(maxsize=10)
        camera_ids = ["camA", "camB"]
        pool = AIWorkerPool(
            frame_queue, camera_ids, num_workers=1,
            backend_url="http://unused", ingest_api_key=None,
            evidence_dir="/tmp/sentinel_test_worker_pool_evidence2",
            device="cpu", no_backend=True, stats_interval=1.0,
            pipeline_factory=_fake_pipeline_factory,
        )
        try:
            self.assertEqual(len(pool.workers), 1)
            self.assertEqual(set(pool.workers[0].camera_ids), set(camera_ids))
            pool.start()
        finally:
            pool.shutdown(timeout=10)


if __name__ == "__main__":
    unittest.main()
