import time
import logging
from collections import defaultdict, Counter
from typing import Dict, List, Any, Tuple, Optional, Union

logger = logging.getLogger("MultiFrameConsensus")

class MultiFrameConsensus:
    """
    Multi-Frame Consensus Voting Engine for license plate recognition.
    Accumulates frame-by-frame plate predictions grouped by vehicle track_id (isolated per camera)
    and applies weighted frequency voting to eliminate misreads.
    Enforces bounded memory via track count limits and LRU/TTL cleanup.
    """

    def __init__(
        self,
        max_history_per_track: int = 20,
        min_confidence_threshold: float = 0.50,
        max_tracks: int = 100,
        track_ttl_seconds: float = 30.0
    ):
        self.max_history = max_history_per_track
        self.min_conf = min_confidence_threshold
        self.max_tracks = max_tracks
        self.track_ttl_seconds = track_ttl_seconds

        # State: track_key -> List[Tuple[normalized_plate, confidence]]
        self.track_history: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        # LRU timestamp tracking: track_key -> last_updated_time
        self.track_last_seen: Dict[str, float] = {}

    def _make_key(self, track_id: Union[int, str], camera_id: str = "CAM-001") -> str:
        """Construct multi-camera isolated track key."""
        return f"{camera_id}:{track_id}"

    def _cleanup_old_tracks(self) -> None:
        """Evict expired or overflow tracks to prevent memory leaks."""
        now = time.time()
        expired_keys = [
            k for k, last_seen in self.track_last_seen.items()
            if (now - last_seen) > self.track_ttl_seconds
        ]
        for k in expired_keys:
            self.track_history.pop(k, None)
            self.track_last_seen.pop(k, None)

        # Enforce max active tracks limit via LRU eviction
        if len(self.track_history) > self.max_tracks:
            sorted_by_time = sorted(self.track_last_seen.items(), key=lambda item: item[1])
            excess = len(self.track_history) - self.max_tracks
            for k, _ in sorted_by_time[:excess]:
                self.track_history.pop(k, None)
                self.track_last_seen.pop(k, None)

    def add_prediction(
        self,
        track_id: Union[int, str],
        plate_number: str,
        confidence: float,
        camera_id: str = "CAM-001"
    ) -> Dict[str, Any]:
        """
        Add a frame's plate prediction for a vehicle track and compute current consensus.

        :param track_id: Unique vehicle tracking ID across frames
        :param plate_number: Normalized plate string for current frame
        :param confidence: OCR confidence score for current frame
        :param camera_id: Identifier of camera stream (for multi-camera isolation)
        :return: Dict containing consensus plate, confidence, vote breakdown, and full history
        """
        track_key = self._make_key(track_id, camera_id)
        self.track_last_seen[track_key] = time.time()

        if not plate_number or plate_number == "UNKNOWN" or confidence < self.min_conf:
            res = self.get_consensus(track_id, camera_id=camera_id)
            self._cleanup_old_tracks()
            return res

        history = self.track_history[track_key]
        history.append((plate_number, confidence))

        if len(history) > self.max_history:
            self.track_history[track_key] = history[-self.max_history:]

        res = self.get_consensus(track_id, camera_id=camera_id)
        self._cleanup_old_tracks()
        return res

    def get_consensus(
        self,
        track_id: Union[int, str],
        camera_id: str = "CAM-001"
    ) -> Dict[str, Any]:
        """
        Compute weighted frequency voting consensus for a given track_id and camera_id.

        :param track_id: Vehicle tracking ID
        :param camera_id: Camera identifier
        :return: Consensus summary dictionary
        """
        track_key = self._make_key(track_id, camera_id)
        history = self.track_history.get(track_key, [])

        if not history:
            return {
                "consensus_plate": "UNKNOWN",
                "confidence": 0.0,
                "total_votes": 0,
                "winner_votes": 0,
                "raw_reads": []
            }

        weighted_scores: Dict[str, float] = defaultdict(float)
        frequency_counts: Dict[str, int] = defaultdict(int)
        raw_reads = []

        for plate, conf in history:
            raw_reads.append(plate)
            frequency_counts[plate] += 1
            weighted_scores[plate] += conf

        best_plate = max(weighted_scores.keys(), key=lambda p: weighted_scores[p])
        winner_weight = weighted_scores[best_plate]
        winner_freq = frequency_counts[best_plate]

        avg_winner_conf = winner_weight / winner_freq if winner_freq > 0 else 0.0
        agreement_ratio = winner_freq / len(history)
        consensus_confidence = min(0.99, avg_winner_conf * (0.8 + 0.2 * agreement_ratio))

        return {
            "consensus_plate": best_plate,
            "confidence": round(float(consensus_confidence), 4),
            "total_votes": len(history),
            "winner_votes": winner_freq,
            "raw_reads": raw_reads
        }

    def is_stable(
        self,
        track_id: Union[int, str],
        camera_id: str = "CAM-001",
        min_votes: int = 3,
        min_confidence: float = 0.75
    ) -> bool:
        """
        Check if a track has reached a stable high-confidence consensus.

        :param track_id: Vehicle tracking ID
        :param camera_id: Camera identifier
        :param min_votes: Minimum number of winning votes required
        :param min_confidence: Minimum consensus confidence required
        :return: True if stable consensus achieved, False otherwise
        """
        c = self.get_consensus(track_id, camera_id=camera_id)
        return (
            c["consensus_plate"] != "UNKNOWN"
            and c["winner_votes"] >= min_votes
            and c["confidence"] >= min_confidence
        )

    def clear_track(self, track_id: Union[int, str], camera_id: str = "CAM-001") -> None:
        """Clear tracking memory when vehicle leaves scene."""
        track_key = self._make_key(track_id, camera_id)
        self.track_history.pop(track_key, None)
        self.track_last_seen.pop(track_key, None)
