"""
Per-track plate identity with character-level temporal consensus
(Phase 15C).

`MultiFrameConsensus` votes on whole plate STRINGS. `PlateTrackState` adds
a second, finer layer: among the reads that agree on the modal length, it
votes **per character position** (weighted by OCR confidence + plate
quality). A single misread frame (`GJ18TC0450` vs `GJ18TC04S0`) is then
corrected at position 8 rather than being allowed to fork the vote.

    store = PlateTrackStore()
    st = store.observe(camera_id, track_id, plate, ocr_conf,
                       plate_quality=0.8, format_score=0.9, ts=...)
    st.resolve()   ->  {plate, confidence, method, char_confidence[],
                        stable, votes, length}

Memory is bounded: at most `max_history` reads per track, at most
`max_tracks` tracks (LRU eviction), tracks expire after `ttl_seconds`.
"""
from __future__ import annotations

import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

_UNKNOWN = "UNKNOWN"


@dataclass
class _Read:
    plate: str
    ocr_conf: float
    plate_quality: float
    format_score: float
    ts: float

    @property
    def weight(self) -> float:
        return max(0.01, self.ocr_conf) * (0.6 + 0.4 * self.plate_quality) * (0.7 + 0.3 * self.format_score)


@dataclass
class PlateTrackState:
    key: str
    max_history: int = 24
    lock_votes: int = 4
    lock_confidence: float = 0.82
    reads: Deque[_Read] = field(default_factory=lambda: deque(maxlen=24))
    last_seen: float = field(default_factory=time.time)
    locked_plate: Optional[str] = None
    locked_at: float = 0.0

    def add(self, plate: str, ocr_conf: float, *, plate_quality: float = 1.0,
            format_score: float = 0.0, ts: Optional[float] = None) -> None:
        now = ts if ts is not None else time.time()
        self.last_seen = now
        plate = (plate or "").strip().upper()
        if not plate or plate == _UNKNOWN:
            return
        # a strong, well-formed disagreement is required to disturb a lock
        if self.locked_plate and plate != self.locked_plate:
            if not (ocr_conf >= 0.92 and format_score >= 0.9):
                return
        self.reads.append(_Read(plate, float(ocr_conf), float(plate_quality),
                                float(format_score), float(now)))

    # ------------------------------------------------------------------ #
    def resolve(self) -> Dict[str, object]:
        if not self.reads:
            return {"plate": _UNKNOWN, "confidence": 0.0, "method": "no-reads",
                    "char_confidence": [], "stable": False, "votes": 0, "length": 0}

        # 1. string-level weighted vote
        wsum: Dict[str, float] = defaultdict(float)
        freq: Counter = Counter()
        for r in self.reads:
            wsum[r.plate] += r.weight
            freq[r.plate] += 1
        str_winner = max(wsum, key=lambda p: wsum[p])
        winner_votes = freq[str_winner]

        # 2. character-level vote among reads of the MODAL length
        modal_len = Counter(len(r.plate) for r in self.reads).most_common(1)[0][0]
        same_len = [r for r in self.reads if len(r.plate) == modal_len]
        char_conf: List[float] = []
        char_plate_chars: List[str] = []
        if len(same_len) >= 2 and modal_len > 0:
            for i in range(modal_len):
                col: Dict[str, float] = defaultdict(float)
                for r in same_len:
                    col[r.plate[i]] += r.weight
                total = sum(col.values()) or 1.0
                ch, w = max(col.items(), key=lambda kv: kv[1])
                char_plate_chars.append(ch)
                char_conf.append(round(w / total, 3))
            char_plate = "".join(char_plate_chars)
        else:
            char_plate = str_winner if len(str_winner) == modal_len else ""
            char_conf = []

        # 3. pick the final identity
        method = "string-vote"
        final = str_winner
        if char_plate and len(char_plate) == len(str_winner) and char_plate != str_winner:
            # trust the per-position vote only where it is clearly strong
            diffs = [i for i in range(len(str_winner)) if str_winner[i] != char_plate[i]]
            if all(char_conf[i] >= 0.6 for i in diffs) and len(diffs) <= 2:
                final = char_plate
                method = "character-level consensus"
        elif char_plate and not str_winner:
            final = char_plate
            method = "character-level consensus"

        # 4. confidence
        avg_w_conf = (
            sum(r.ocr_conf for r in self.reads if r.plate == str_winner)
            / max(1, winner_votes)
        )
        agreement = winner_votes / len(self.reads)
        stability = min(1.0, winner_votes / 5.0)
        char_floor = min(char_conf) if char_conf else agreement
        confidence = round(min(
            0.99,
            avg_w_conf * (0.55 + 0.2 * agreement + 0.15 * stability + 0.1 * char_floor),
        ), 4)

        stable = final != _UNKNOWN and winner_votes >= 3 and confidence >= 0.75
        if (not self.locked_plate and winner_votes >= self.lock_votes
                and confidence >= self.lock_confidence and final != _UNKNOWN):
            self.locked_plate = final
            self.locked_at = time.time()

        return {
            "plate": final,
            "confidence": confidence,
            "method": method,
            "char_confidence": char_conf,
            "stable": bool(stable),
            "votes": int(winner_votes),
            "length": int(modal_len),
            "locked": self.locked_plate is not None,
        }

    def expired(self, now: Optional[float] = None, ttl: float = 30.0) -> bool:
        return (now or time.time()) - self.last_seen > ttl


class PlateTrackStore:
    def __init__(self, *, max_tracks: int = 128, max_history: int = 24,
                 ttl_seconds: float = 30.0):
        self.max_tracks = max_tracks
        self.max_history = max_history
        self.ttl = ttl_seconds
        self._states: Dict[str, PlateTrackState] = {}

    @staticmethod
    def _key(camera_id: str, track_id) -> str:
        return f"{camera_id}:{track_id}"

    def observe(self, camera_id: str, track_id, plate: str, ocr_conf: float, *,
                plate_quality: float = 1.0, format_score: float = 0.0,
                ts: Optional[float] = None) -> PlateTrackState:
        key = self._key(camera_id, track_id)
        st = self._states.get(key)
        if st is None:
            st = PlateTrackState(key=key, max_history=self.max_history)
            st.reads = deque(maxlen=self.max_history)
            self._states[key] = st
        st.add(plate, ocr_conf, plate_quality=plate_quality,
               format_score=format_score, ts=ts)
        self._sweep(ts)
        return st

    def get(self, camera_id: str, track_id) -> Optional[PlateTrackState]:
        return self._states.get(self._key(camera_id, track_id))

    def clear(self, camera_id: str, track_id) -> None:
        self._states.pop(self._key(camera_id, track_id), None)

    def _sweep(self, now: Optional[float] = None) -> None:
        now = now if now is not None else time.time()
        dead = [k for k, s in self._states.items() if s.expired(now, self.ttl)]
        for k in dead:
            self._states.pop(k, None)
        if len(self._states) > self.max_tracks:
            by_age = sorted(self._states.items(), key=lambda kv: kv[1].last_seen)
            for k, _ in by_age[: len(self._states) - self.max_tracks]:
                self._states.pop(k, None)

    def __len__(self) -> int:
        return len(self._states)
