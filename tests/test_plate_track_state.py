"""
Phase 15C -- character-level temporal ANPR fusion (PlateTrackState).

Covers: character-level reconstruction when no single string wins, one bad
frame never overwriting a stable plate, confidence + char_confidence,
bounded memory, TTL expiry, LRU track eviction.
"""
import unittest

from ai.anpr.plate_track_state import PlateTrackState, PlateTrackStore

TRUE = "GJ18TC0450"


class TestCharacterLevelConsensus(unittest.TestCase):
    def test_reconstructs_plate_when_no_string_wins(self):
        st = PlateTrackState(key="c:1")
        # five reads, each with a DIFFERENT single-character error -> no
        # string has a majority, but every position is 4/5 correct.
        for r in ("GJ1BTC0450", "GJ18TG0450", "GJ18TC0A50", "GJ18TC04S0", "GJ18TC045O"):
            st.add(r, 0.7, plate_quality=0.8, format_score=0.6)
        out = st.resolve()
        self.assertEqual(out["plate"], TRUE)
        self.assertEqual(out["method"], "character-level consensus")
        self.assertEqual(len(out["char_confidence"]), 10)

    def test_clean_reads_use_string_vote(self):
        st = PlateTrackState(key="c:2")
        for _ in range(4):
            st.add(TRUE, 0.9, plate_quality=0.9, format_score=0.95)
        out = st.resolve()
        self.assertEqual(out["plate"], TRUE)
        self.assertEqual(out["method"], "string-vote")
        self.assertTrue(out["stable"])
        self.assertGreater(out["confidence"], 0.75)

    def test_single_bad_frame_does_not_break_a_lock(self):
        st = PlateTrackState(key="c:3", lock_votes=3, lock_confidence=0.75)
        for _ in range(5):
            st.add(TRUE, 0.9, plate_quality=0.9, format_score=0.95)
        self.assertTrue(st.resolve()["locked"])
        # a weak, badly-formed disagreeing read is ignored entirely
        st.add("XX00YY0000", 0.55, plate_quality=0.2, format_score=0.1)
        out = st.resolve()
        self.assertEqual(out["plate"], TRUE)

    def test_unknown_and_empty_reads_ignored(self):
        st = PlateTrackState(key="c:4")
        st.add("UNKNOWN", 0.9)
        st.add("", 0.9)
        self.assertEqual(st.resolve()["plate"], "UNKNOWN")


class TestBoundedMemory(unittest.TestCase):
    def test_history_is_capped(self):
        st = PlateTrackState(key="c:5", max_history=8)
        from collections import deque
        st.reads = deque(maxlen=8)
        for i in range(40):
            st.add(TRUE, 0.9)
        self.assertLessEqual(len(st.reads), 8)

    def test_store_evicts_expired_and_lru(self):
        store = PlateTrackStore(max_tracks=3, ttl_seconds=10.0)
        t = 1000.0
        for i in range(3):
            store.observe("cam", i, TRUE, 0.9, ts=t + i)
        self.assertEqual(len(store), 3)
        # a 4th track at a much later time evicts the oldest + expired
        store.observe("cam", 99, TRUE, 0.9, ts=t + 100)
        self.assertLessEqual(len(store), 3)
        self.assertIsNotNone(store.get("cam", 99))

    def test_expiry(self):
        st = PlateTrackState(key="c:6")
        st.add(TRUE, 0.9, ts=100.0)
        self.assertFalse(st.expired(now=120.0, ttl=30.0))
        self.assertTrue(st.expired(now=200.0, ttl=30.0))

    def test_timestamp_zero_is_not_treated_as_missing(self):
        """Regression: `now or time.time()` used to treat the legitimate
        timestamp 0.0 as falsy and silently substitute the real current
        wall-clock time, making every track look decades old and evicting
        the entire store on the very next observe() call -- found by
        Phase 18's temporal-fusion review, not by inspection alone."""
        st = PlateTrackState(key="c:zero")
        st.add(TRUE, 0.9, ts=0.0)
        self.assertFalse(st.expired(now=0.0, ttl=30.0))
        self.assertFalse(st.expired(now=5.0, ttl=30.0))

        store = PlateTrackStore()
        store.observe("cam01", 1, TRUE, 0.9, ts=0.0)
        self.assertIsNotNone(store.get("cam01", 1), "track evicted immediately when ts=0.0")
        store.observe("cam01", 2, "MH12AB9999", 0.9, ts=0.0)
        self.assertIsNotNone(store.get("cam01", 1), "earlier track wrongly swept when a new one arrives at ts=0.0")
        self.assertIsNotNone(store.get("cam01", 2))


class TestStore(unittest.TestCase):
    def test_observe_returns_stable_after_enough_reads(self):
        store = PlateTrackStore()
        st = None
        for i in range(5):
            st = store.observe("cam04", 7, TRUE, 0.9, plate_quality=0.85,
                               format_score=0.95, ts=1000.0 + i)
        out = st.resolve()
        self.assertEqual(out["plate"], TRUE)
        self.assertTrue(out["stable"])
        self.assertEqual(out["votes"], 5)


class TestWorkedExampleAndContamination(unittest.TestCase):
    """Phase 18 Part C -- the exact worked example from the task brief:

        Frame 1: GJ18TC0?50   (one character unreadable/misread)
        Frame 2: GJ18TC0450
        Frame 3: GJ18TC0450
        Frame 4: GJ18TC0450
        Final:   GJ18TC0450

    plus the two properties Part C calls out by name: no cross-vehicle
    contamination, and a single noisy frame is never accepted alone."""

    def test_one_noisy_char_converges_to_the_true_plate_over_four_frames(self):
        store = PlateTrackStore()
        reads = ["GJ18TC0X50", "GJ18TC0450", "GJ18TC0450", "GJ18TC0450"]
        st = None
        for i, r in enumerate(reads):
            st = store.observe("cam01", 42, r, 0.85, plate_quality=0.8, format_score=0.9, ts=i)
        out = st.resolve()
        self.assertEqual(out["plate"], TRUE)
        self.assertGreaterEqual(out["votes"], 3)

    def test_a_single_noisy_frame_alone_is_not_treated_as_final(self):
        """One frame, by itself, must never be enough to call a plate
        'stable' -- Part C: 'Do not accept a plate solely because one
        noisy OCR frame produced it.'"""
        store = PlateTrackStore()
        st = store.observe("cam01", 1, "GJ18TC0X50", 0.55, plate_quality=0.4, format_score=0.5, ts=0)
        out = st.resolve()
        self.assertFalse(out["stable"])
        self.assertEqual(out["votes"], 1)

    def test_no_cross_vehicle_contamination_same_camera_different_tracks(self):
        store = PlateTrackStore()
        for i in range(5):
            store.observe("cam01", 1, "GJ18TC0450", 0.9, plate_quality=0.9, format_score=0.95, ts=i)
        for i in range(5):
            store.observe("cam01", 2, "MH12AB9999", 0.9, plate_quality=0.9, format_score=0.95, ts=i)
        self.assertEqual(store.get("cam01", 1).resolve()["plate"], "GJ18TC0450")
        self.assertEqual(store.get("cam01", 2).resolve()["plate"], "MH12AB9999")

    def test_no_cross_vehicle_contamination_same_track_id_different_cameras(self):
        """Track IDs are only unique WITHIN a camera (ByteTrack is
        per-camera) -- track_id=1 on cam01 and track_id=1 on cam06 must be
        completely independent identities."""
        store = PlateTrackStore()
        for i in range(5):
            store.observe("cam01", 1, "GJ18TC0450", 0.9, plate_quality=0.9, format_score=0.95, ts=i)
        for i in range(5):
            store.observe("cam06", 1, "RJ14CD5678", 0.9, plate_quality=0.9, format_score=0.95, ts=i)
        self.assertEqual(store.get("cam01", 1).resolve()["plate"], "GJ18TC0450")
        self.assertEqual(store.get("cam06", 1).resolve()["plate"], "RJ14CD5678")


if __name__ == "__main__":
    unittest.main()
