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


if __name__ == "__main__":
    unittest.main()
