import logging
from collections import defaultdict, Counter
from typing import Dict, List, Any, Tuple, Optional, Union

logger = logging.getLogger("MultiFrameConsensus")

class MultiFrameConsensus:
    """
    Multi-Frame Consensus Voting Engine for license plate recognition.
    Accumulates frame-by-frame plate predictions grouped by vehicle track_id
    and applies weighted frequency voting to eliminate misreads.
    """

    def __init__(self, max_history_per_track: int = 20, min_confidence_threshold: float = 0.50):
        self.max_history = max_history_per_track
        self.min_conf = min_confidence_threshold
        # State: track_id -> List[Tuple[normalized_plate, confidence]]
        self.track_history: Dict[Union[int, str], List[Tuple[str, float]]] = defaultdict(list)

    def add_prediction(
        self,
        track_id: Union[int, str],
        plate_number: str,
        confidence: float
    ) -> Dict[str, Any]:
        """
        Add a frame's plate prediction for a vehicle track and compute current consensus.

        :param track_id: Unique vehicle tracking ID across frames (e.g. from ByteTrack)
        :param plate_number: Normalized plate string for current frame
        :param confidence: OCR confidence score for current frame
        :return: Dict containing consensus plate, confidence, vote breakdown, and full history
        """
        if not plate_number or plate_number == "UNKNOWN" or confidence < self.min_conf:
            # Return current consensus if frame prediction is low confidence
            return self.get_consensus(track_id)

        # Append to track history
        history = self.track_history[track_id]
        history.append((plate_number, confidence))

        # Enforce sliding window history length
        if len(history) > self.max_history:
            self.track_history[track_id] = history[-self.max_history:]

        return self.get_consensus(track_id)

    def get_consensus(self, track_id: Union[int, str]) -> Dict[str, Any]:
        """
        Compute weighted frequency voting consensus for a given track_id.

        :param track_id: Vehicle tracking ID
        :return: Consensus summary dictionary
        """
        history = self.track_history.get(track_id, [])

        if not history:
            return {
                "consensus_plate": "UNKNOWN",
                "confidence": 0.0,
                "total_votes": 0,
                "raw_reads": []
            }

        # Weighted voting dictionary: plate_string -> total_accumulated_score
        weighted_scores: Dict[str, float] = defaultdict(float)
        frequency_counts: Dict[str, int] = defaultdict(int)
        raw_reads = []

        for plate, conf in history:
            raw_reads.append(plate)
            frequency_counts[plate] += 1
            # Weight formula: count * confidence
            weighted_scores[plate] += conf

        # Select winner with highest accumulated weighted score
        best_plate = max(weighted_scores.keys(), key=lambda p: weighted_scores[p])
        total_weight = sum(weighted_scores.values())
        winner_weight = weighted_scores[best_plate]
        winner_freq = frequency_counts[best_plate]

        # Average OCR confidence of winning plate predictions
        avg_winner_conf = winner_weight / winner_freq if winner_freq > 0 else 0.0
        # Agreement ratio factor
        agreement_ratio = winner_freq / len(history)
        consensus_confidence = min(0.99, avg_winner_conf * (0.8 + 0.2 * agreement_ratio))

        return {
            "consensus_plate": best_plate,
            "confidence": round(float(consensus_confidence), 4),
            "total_votes": len(history),
            "winner_votes": winner_freq,
            "raw_reads": raw_reads
        }

    def clear_track(self, track_id: Union[int, str]) -> None:
        """Clear tracking memory when vehicle leaves scene."""
        if track_id in self.track_history:
            del self.track_history[track_id]
