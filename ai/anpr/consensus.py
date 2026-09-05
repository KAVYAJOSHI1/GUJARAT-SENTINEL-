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
        track_ttl_seconds: float = 30.0,
        lock_min_votes: int = 4,
        lock_min_confidence: float = 0.82,
        lock_ttl_seconds: float = 20.0,
    ):
        self.max_history = max_history_per_track
        self.min_conf = min_confidence_threshold
        self.max_tracks = max_tracks
        self.track_ttl_seconds = track_ttl_seconds
        self.lock_min_votes = lock_min_votes
        self.lock_min_confidence = lock_min_confidence
        self.lock_ttl_seconds = lock_ttl_seconds

        # State: track_key -> List[Tuple[plate, ocr_conf, detection_conf, format_score]]
        self.track_history: Dict[str, List[Tuple[str, float, float, float]]] = defaultdict(list)
        # LRU timestamp tracking: track_key -> last_updated_time
        self.track_last_seen: Dict[str, float] = {}
        # Locked stable plates: track_key -> (plate, lock_time)
        self._locked: Dict[str, Tuple[str, float]] = {}

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
            self._locked.pop(k, None)

        # Enforce max active tracks limit via LRU eviction
        if len(self.track_history) > self.max_tracks:
            sorted_by_time = sorted(self.track_last_seen.items(), key=lambda item: item[1])
            excess = len(self.track_history) - self.max_tracks
            for k, _ in sorted_by_time[:excess]:
                self.track_history.pop(k, None)
                self.track_last_seen.pop(k, None)
                self._locked.pop(k, None)

    def add_prediction(
        self,
        track_id: Union[int, str],
        plate_number: str,
        confidence: float,
        camera_id: str = "CAM-001",
        detection_confidence: float = 1.0,
        format_score: float = 0.0,
        plate_quality: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Add a frame's plate prediction for a vehicle track and compute current consensus.

        :param track_id: Unique vehicle tracking ID across frames
        :param plate_number: Normalized plate string for current frame
        :param confidence: OCR confidence score for current frame
        :param camera_id: Identifier of camera stream (for multi-camera isolation)
        :param detection_confidence: vehicle-detection confidence for this frame
        :param format_score: Indian-plate format validity of this read (0-1)
        :param plate_quality: plate-LOCATOR confidence for this frame (0-1) --
            distinct from ``format_score``: this reflects how much the region
            fed to OCR looks like an actual, well-localised plate (a real
            contour match vs. a crude heuristic fallback crop), independent
            of whether the resulting text happens to parse as a valid
            Indian format. A vote built on a fallback-crop (low
            plate_quality) is weighted down even if the OCR text it produced
            looks superficially well-formed.
        :return: Dict containing consensus plate, confidence, vote breakdown, and full history
        """
        track_key = self._make_key(track_id, camera_id)
        self.track_last_seen[track_key] = time.time()

        if not plate_number or plate_number == "UNKNOWN" or confidence < self.min_conf:
            res = self.get_consensus(track_id, camera_id=camera_id)
            self._cleanup_old_tracks()
            return res

        # A single bad frame must not overwrite a locked, stable plate. It takes
        # a strong, well-formed disagreeing read to break the lock.
        locked = self._locked.get(track_key)
        if locked is not None:
            plate_locked, lock_t = locked
            if time.time() - lock_t <= self.lock_ttl_seconds:
                if plate_number != plate_locked and not (
                    confidence >= 0.92 and format_score >= 0.9
                ):
                    return self.get_consensus(track_id, camera_id=camera_id)
            else:
                self._locked.pop(track_key, None)

        history = self.track_history[track_key]
        history.append((
            plate_number, float(confidence), float(detection_confidence),
            float(format_score), float(plate_quality),
        ))

        if len(history) > self.max_history:
            self.track_history[track_key] = history[-self.max_history:]

        res = self.get_consensus(track_id, camera_id=camera_id)

        # Lock once the plate is genuinely stable and well-formed.
        if (
            track_key not in self._locked
            and res["consensus_plate"] != "UNKNOWN"
            and res["winner_votes"] >= self.lock_min_votes
            and res["confidence"] >= self.lock_min_confidence
        ):
            self._locked[track_key] = (res["consensus_plate"], time.time())

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
        conf_sum: Dict[str, float] = defaultdict(float)
        raw_reads = []
        recency_bonus = 1.0

        for entry in history:
            plate, conf = entry[0], entry[1]
            det_conf = entry[2] if len(entry) > 2 else 1.0
            fmt = entry[3] if len(entry) > 3 else 0.0
            plate_q = entry[4] if len(entry) > 4 else 1.0
            raw_reads.append(plate)
            frequency_counts[plate] += 1
            conf_sum[plate] += conf
            # weight = ocr_conf * detection_quality * format_validity *
            #          plate_locator_quality * recency
            weight = (
                conf * (0.55 + 0.45 * det_conf) * (0.7 + 0.3 * fmt)
                * (0.7 + 0.3 * plate_q) * recency_bonus
            )
            weighted_scores[plate] += weight
            recency_bonus = min(1.6, recency_bonus + 0.05)  # newer reads count a little more

        best_plate = max(weighted_scores.keys(), key=lambda p: weighted_scores[p])
        winner_freq = frequency_counts[best_plate]

        avg_winner_conf = conf_sum[best_plate] / winner_freq if winner_freq > 0 else 0.0
        agreement_ratio = winner_freq / len(history)
        # temporal stability: more agreeing frames -> higher confidence
        stability = min(1.0, winner_freq / 5.0)
        consensus_confidence = min(
            0.99, avg_winner_conf * (0.7 + 0.15 * agreement_ratio + 0.15 * stability)
        )

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
        self._locked.pop(track_key, None)
