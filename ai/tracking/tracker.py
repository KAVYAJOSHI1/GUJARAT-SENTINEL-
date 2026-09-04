"""
ai/tracking/tracker.py

Self-contained ByteTrack multi-object tracker for the SENTINEL platform.

DEVELOPER_README section 6/7 nominate ByteTrack + ``lap``.  ByteTrack is an
*algorithm*, not a stable pip package, and its reference repo pulls in a heavy
CV stack.  This module implements the ByteTrack association algorithm directly on
NumPy + SciPy (``scipy.optimize.linear_sum_assignment`` for the Hungarian step,
``scipy.linalg`` for the Kalman update) so the tracking engine has zero fragile
dependencies and stays unit-testable without a GPU or OpenCV.

Public surface:
  * ``ByteTrackTracker``       -- frame-by-frame tracker, persistent camera-local IDs
  * ``Track`` / ``TrackState`` -- track lifecycle objects
  * ``KalmanFilter``           -- constant-velocity box filter (occlusion bridging)
  * ``TrackEventDeduplicator`` -- "one consolidated AI event per completed track"

Input  (per frame): list of detections ``{"bbox": [x1,y1,x2,y2],
        "confidence": float, "class": str}`` -- exactly Kavya's
        ``VehicleDetector.detect()`` output shape.
Output (per frame): list of online tracks ``{"track_id", "bbox", "score",
        "class", "age", "hits", "time_since_update", "state", "start_frame"}``.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import scipy.linalg
from scipy.optimize import linear_sum_assignment

from ai.tracking.track_association import iou_matrix

logger = logging.getLogger("ByteTrack")


# --------------------------------------------------------------------------- #
#  Kalman filter (8-state constant velocity: cx, cy, aspect, h, + velocities)   #
# --------------------------------------------------------------------------- #
class KalmanFilter:
    """A simple Kalman filter for tracking bounding boxes in image space.

    State space (8-d): ``x, y, a, h, vx, vy, va, vh`` where ``(x, y)`` is the box
    centre, ``a`` the aspect ratio ``w / h`` and ``h`` the height.
    """

    def __init__(self) -> None:
        ndim, dt = 4, 1.0
        self._motion_mat = np.eye(2 * ndim, 2 * ndim)
        for i in range(ndim):
            self._motion_mat[i, ndim + i] = dt
        self._update_mat = np.eye(ndim, 2 * ndim)
        self._std_weight_position = 1.0 / 20
        self._std_weight_velocity = 1.0 / 160

    def initiate(self, measurement: np.ndarray):
        mean_pos = np.asarray(measurement, dtype=np.float64)
        mean_vel = np.zeros_like(mean_pos)
        mean = np.r_[mean_pos, mean_vel]
        std = [
            2 * self._std_weight_position * measurement[3],
            2 * self._std_weight_position * measurement[3],
            1e-2,
            2 * self._std_weight_position * measurement[3],
            10 * self._std_weight_velocity * measurement[3],
            10 * self._std_weight_velocity * measurement[3],
            1e-5,
            10 * self._std_weight_velocity * measurement[3],
        ]
        covariance = np.diag(np.square(std))
        return mean, covariance

    def predict(self, mean: np.ndarray, covariance: np.ndarray):
        std_pos = [
            self._std_weight_position * mean[3],
            self._std_weight_position * mean[3],
            1e-2,
            self._std_weight_position * mean[3],
        ]
        std_vel = [
            self._std_weight_velocity * mean[3],
            self._std_weight_velocity * mean[3],
            1e-5,
            self._std_weight_velocity * mean[3],
        ]
        motion_cov = np.diag(np.square(np.r_[std_pos, std_vel]))
        mean = self._motion_mat @ mean
        covariance = np.linalg.multi_dot((self._motion_mat, covariance, self._motion_mat.T)) + motion_cov
        return mean, covariance

    def project(self, mean: np.ndarray, covariance: np.ndarray):
        std = [
            self._std_weight_position * mean[3],
            self._std_weight_position * mean[3],
            1e-1,
            self._std_weight_position * mean[3],
        ]
        innovation_cov = np.diag(np.square(std))
        mean = self._update_mat @ mean
        covariance = np.linalg.multi_dot((self._update_mat, covariance, self._update_mat.T))
        return mean, covariance + innovation_cov

    def update(self, mean: np.ndarray, covariance: np.ndarray, measurement: np.ndarray):
        projected_mean, projected_cov = self.project(mean, covariance)
        chol_factor, lower = scipy.linalg.cho_factor(projected_cov, lower=True, check_finite=False)
        kalman_gain = scipy.linalg.cho_solve(
            (chol_factor, lower),
            (covariance @ self._update_mat.T).T,
            check_finite=False,
        ).T
        innovation = measurement - projected_mean
        new_mean = mean + innovation @ kalman_gain.T
        new_covariance = covariance - np.linalg.multi_dot((kalman_gain, projected_cov, kalman_gain.T))
        return new_mean, new_covariance


# --------------------------------------------------------------------------- #
#  Track lifecycle                                                             #
# --------------------------------------------------------------------------- #
class TrackState:
    New = 0
    Tracked = 1
    Lost = 2
    Removed = 3

    _NAMES = {0: "new", 1: "tracked", 2: "lost", 3: "removed"}


def _tlbr_to_tlwh(tlbr: Sequence[float]) -> np.ndarray:
    ret = np.asarray(tlbr, dtype=np.float64).copy()
    ret[2:] -= ret[:2]
    return ret


class Track:
    """A single vehicle track with a Kalman-filtered box estimate."""

    def __init__(self, tlwh: Sequence[float], score: float, cls: Any = None):
        self._tlwh = np.asarray(tlwh, dtype=np.float64)
        self.kalman_filter: Optional[KalmanFilter] = None
        self.mean: Optional[np.ndarray] = None
        self.covariance: Optional[np.ndarray] = None

        self.track_id: int = 0
        self.state: int = TrackState.New
        self.is_activated: bool = False

        self.score: float = float(score)
        self.cls: Any = cls
        self.best_score: float = float(score)

        self.hits: int = 0            # total frames this track was updated
        self.age: int = 0             # total frames since creation
        self.time_since_update: int = 0
        self.frame_id: int = 0
        self.start_frame: int = 0

    # -- geometry ---------------------------------------------------------- #
    @staticmethod
    def tlwh_to_xyah(tlwh: Sequence[float]) -> np.ndarray:
        ret = np.asarray(tlwh, dtype=np.float64).copy()
        ret[:2] += ret[2:] / 2.0
        ret[2] /= ret[3]
        return ret

    @property
    def tlwh(self) -> np.ndarray:
        if self.mean is None:
            return self._tlwh.copy()
        ret = self.mean[:4].copy()
        ret[2] *= ret[3]          # a * h -> w
        ret[:2] -= ret[2:] / 2.0
        return ret

    @property
    def tlbr(self) -> np.ndarray:
        ret = self.tlwh.copy()
        ret[2:] += ret[:2]
        return ret

    # -- lifecycle transitions ------------------------------------------- #
    def activate(self, kalman_filter: KalmanFilter, frame_id: int, track_id: int) -> None:
        self.kalman_filter = kalman_filter
        self.track_id = track_id
        self.mean, self.covariance = kalman_filter.initiate(self.tlwh_to_xyah(self._tlwh))
        self.time_since_update = 0
        self.hits = 1
        self.age = 1
        self.state = TrackState.Tracked
        self.is_activated = frame_id == 1
        self.frame_id = frame_id
        self.start_frame = frame_id

    def re_activate(self, new_track: "Track", frame_id: int) -> None:
        self.mean, self.covariance = self.kalman_filter.update(
            self.mean, self.covariance, self.tlwh_to_xyah(new_track.tlwh)
        )
        self.time_since_update = 0
        self.hits += 1
        self.state = TrackState.Tracked
        self.is_activated = True
        self.frame_id = frame_id
        self.score = new_track.score
        self.best_score = max(self.best_score, new_track.score)
        if new_track.cls is not None:
            self.cls = new_track.cls

    def update(self, new_track: "Track", frame_id: int) -> None:
        self.frame_id = frame_id
        self.hits += 1
        self.time_since_update = 0
        self.mean, self.covariance = self.kalman_filter.update(
            self.mean, self.covariance, self.tlwh_to_xyah(new_track.tlwh)
        )
        self.state = TrackState.Tracked
        self.is_activated = True
        self.score = new_track.score
        self.best_score = max(self.best_score, new_track.score)
        if new_track.cls is not None:
            self.cls = new_track.cls

    def predict(self) -> None:
        mean_state = self.mean.copy()
        if self.state != TrackState.Tracked:
            mean_state[7] = 0.0      # freeze height-velocity while not actively tracked
        self.mean, self.covariance = self.kalman_filter.predict(mean_state, self.covariance)
        self.age += 1
        self.time_since_update += 1

    def mark_lost(self) -> None:
        self.state = TrackState.Lost

    def mark_removed(self) -> None:
        self.state = TrackState.Removed

    def as_dict(self) -> Dict[str, Any]:
        x1, y1, x2, y2 = (float(v) for v in self.tlbr)
        return {
            "track_id": self.track_id,
            "bbox": [x1, y1, x2, y2],
            "score": round(float(self.score), 4),
            "best_score": round(float(self.best_score), 4),
            "class": self.cls,
            "cls": self.cls,
            "age": self.age,
            "hits": self.hits,
            "frames_tracked": self.hits,
            "time_since_update": self.time_since_update,
            "state": TrackState._NAMES.get(self.state, "unknown"),
            "start_frame": self.start_frame,
            "frame_id": self.frame_id,
        }


# --------------------------------------------------------------------------- #
#  Track-pool helpers (ByteTrack)                                              #
# --------------------------------------------------------------------------- #
def _join_tracks(a: List[Track], b: List[Track]) -> List[Track]:
    seen = {t.track_id for t in a}
    out = list(a)
    for t in b:
        if t.track_id not in seen:
            seen.add(t.track_id)
            out.append(t)
    return out


def _sub_tracks(a: List[Track], b: List[Track]) -> List[Track]:
    drop = {t.track_id for t in b}
    return [t for t in a if t.track_id not in drop]


def _remove_duplicate_tracks(a: List[Track], b: List[Track], iou_thresh: float = 0.15):
    if not a or not b:
        return a, b
    dist = 1.0 - iou_matrix([t.tlbr for t in a], [t.tlbr for t in b])
    pairs = np.where(dist < iou_thresh)
    dup_a, dup_b = set(), set()
    for p, q in zip(*pairs):
        age_a = a[p].frame_id - a[p].start_frame
        age_b = b[q].frame_id - b[q].start_frame
        if age_a > age_b:
            dup_b.add(q)
        else:
            dup_a.add(p)
    res_a = [t for i, t in enumerate(a) if i not in dup_a]
    res_b = [t for i, t in enumerate(b) if i not in dup_b]
    return res_a, res_b


def _linear_assignment(cost_matrix: np.ndarray, thresh: float):
    """Hungarian assignment; returns ``(matches Nx2 int, unmatched_a, unmatched_b)``."""
    if cost_matrix.size == 0:
        return (
            np.empty((0, 2), dtype=int),
            list(range(cost_matrix.shape[0])),
            list(range(cost_matrix.shape[1])),
        )
    matches = []
    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    for r, c in zip(row_ind, col_ind):
        if cost_matrix[r, c] <= thresh:
            matches.append((int(r), int(c)))
    matched_rows = {r for r, _ in matches}
    matched_cols = {c for _, c in matches}
    unmatched_a = [r for r in range(cost_matrix.shape[0]) if r not in matched_rows]
    unmatched_b = [c for c in range(cost_matrix.shape[1]) if c not in matched_cols]
    return np.asarray(matches, dtype=int).reshape(-1, 2), unmatched_a, unmatched_b


# --------------------------------------------------------------------------- #
#  ByteTrack tracker                                                           #
# --------------------------------------------------------------------------- #
class ByteTrackTracker:
    """ByteTrack: two-stage IoU association keeping low-score detections in play.

    One instance per camera feed -> IDs are camera-local and persistent.
    """

    def __init__(
        self,
        track_thresh: float = 0.5,
        match_thresh: float = 0.8,
        low_thresh: float = 0.1,
        new_track_thresh: Optional[float] = None,
        track_buffer: int = 30,
        frame_rate: int = 30,
    ) -> None:
        self.track_thresh = track_thresh
        self.match_thresh = match_thresh          # IoU-distance ceiling for stage 1
        self.low_thresh = low_thresh
        self.new_track_thresh = new_track_thresh if new_track_thresh is not None else track_thresh + 0.1
        self.max_time_lost = max(1, int(frame_rate / 30.0 * track_buffer))

        self.kalman_filter = KalmanFilter()
        self.tracked_tracks: List[Track] = []
        self.lost_tracks: List[Track] = []
        self.removed_tracks: List[Track] = []

        self.frame_id = 0
        self._id_count = 0
        self._newly_finalized: List[Track] = []

    # -- id allocation --------------------------------------------------- #
    def _next_id(self) -> int:
        self._id_count += 1
        return self._id_count

    def reset(self) -> None:
        self.tracked_tracks.clear()
        self.lost_tracks.clear()
        self.removed_tracks.clear()
        self.frame_id = 0
        self._id_count = 0
        self._newly_finalized.clear()

    # -- main step ----------------------------------------------------- #
    def update(
        self,
        detections: Optional[Sequence[Dict[str, Any]]],
        frame_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Advance the tracker by one frame and return the online tracks."""
        self.frame_id = frame_id if frame_id is not None else self.frame_id + 1
        self._newly_finalized = []
        activated: List[Track] = []
        refind: List[Track] = []
        lost: List[Track] = []
        removed: List[Track] = []

        boxes, scores, clss = [], [], []
        for d in detections or []:
            b = d["bbox"]
            boxes.append([float(b[0]), float(b[1]), float(b[2]), float(b[3])])
            scores.append(float(d.get("confidence", d.get("score", 0.0))))
            clss.append(d.get("class", d.get("cls")))
        scores = np.asarray(scores, dtype=np.float64)

        high_mask = scores >= self.track_thresh
        low_mask = (scores > self.low_thresh) & (scores < self.track_thresh)

        dets_high = [Track(_tlbr_to_tlwh(boxes[i]), scores[i], clss[i]) for i in np.where(high_mask)[0]]
        dets_low = [Track(_tlbr_to_tlwh(boxes[i]), scores[i], clss[i]) for i in np.where(low_mask)[0]]

        unconfirmed = [t for t in self.tracked_tracks if not t.is_activated]
        tracked = [t for t in self.tracked_tracks if t.is_activated]

        # predict every candidate forward
        strack_pool = _join_tracks(tracked, self.lost_tracks)
        for t in strack_pool:
            t.predict()
        for t in unconfirmed:
            t.predict()

        # -- Stage 1: high-score detections vs tracked + lost -------------- #
        dists = 1.0 - iou_matrix([t.tlbr for t in strack_pool], [d.tlbr for d in dets_high])
        matches, u_track, u_det = _linear_assignment(dists, thresh=self.match_thresh)
        for it, idet in matches:
            track, det = strack_pool[it], dets_high[idet]
            if track.state == TrackState.Tracked:
                track.update(det, self.frame_id)
                activated.append(track)
            else:
                track.re_activate(det, self.frame_id)
                refind.append(track)

        # -- Stage 2: low-score detections vs still-unmatched tracked ----- #
        r_tracked = [strack_pool[i] for i in u_track if strack_pool[i].state == TrackState.Tracked]
        dists2 = 1.0 - iou_matrix([t.tlbr for t in r_tracked], [d.tlbr for d in dets_low])
        matches2, u_track2, _ = _linear_assignment(dists2, thresh=0.5)
        for it, idet in matches2:
            track, det = r_tracked[it], dets_low[idet]
            track.update(det, self.frame_id)
            activated.append(track)
        for it in u_track2:
            track = r_tracked[it]
            if track.state != TrackState.Lost:
                track.mark_lost()
                lost.append(track)

        # -- unconfirmed (age-1) tracks vs leftover high detections ------- #
        leftover = [dets_high[i] for i in u_det]
        dists3 = 1.0 - iou_matrix([t.tlbr for t in unconfirmed], [d.tlbr for d in leftover])
        matches3, u_unconfirmed, u_det3 = _linear_assignment(dists3, thresh=0.7)
        for it, idet in matches3:
            unconfirmed[it].update(leftover[idet], self.frame_id)
            activated.append(unconfirmed[it])
        for it in u_unconfirmed:
            unconfirmed[it].mark_removed()
            removed.append(unconfirmed[it])

        # -- spawn new tracks from remaining strong detections ----------- #
        for idet in u_det3:
            det = leftover[idet]
            if det.score < self.new_track_thresh:
                continue
            det.activate(self.kalman_filter, self.frame_id, self._next_id())
            activated.append(det)

        # -- age out long-lost tracks ----------------------------------- #
        for track in self.lost_tracks:
            if self.frame_id - track.frame_id > self.max_time_lost:
                track.mark_removed()
                removed.append(track)

        # -- rebuild pools --------------------------------------------- #
        self.tracked_tracks = [t for t in self.tracked_tracks if t.state == TrackState.Tracked]
        self.tracked_tracks = _join_tracks(self.tracked_tracks, activated)
        self.tracked_tracks = _join_tracks(self.tracked_tracks, refind)
        self.lost_tracks = _sub_tracks(self.lost_tracks, self.tracked_tracks)
        self.lost_tracks.extend(lost)
        self.lost_tracks = _sub_tracks(self.lost_tracks, removed)
        self.tracked_tracks, self.lost_tracks = _remove_duplicate_tracks(
            self.tracked_tracks, self.lost_tracks
        )

        # de-dup the removed list, keep only genuinely finalized tracks
        seen: set = set()
        for t in removed:
            if t.track_id and t.track_id not in seen:
                seen.add(t.track_id)
                self._newly_finalized.append(t)
        self.removed_tracks.extend(self._newly_finalized)

        return [t.as_dict() for t in self.tracked_tracks if t.is_activated]

    # -- track termination stream ------------------------------------- #
    def get_finalized_tracks(self) -> List[Dict[str, Any]]:
        """Tracks that terminated on the **most recent** ``update()`` call.

        These are the moments to emit exactly one consolidated AI event per
        vehicle (see ``TrackEventDeduplicator``).
        """
        return [t.as_dict() for t in self._newly_finalized]

    def flush(self) -> List[Dict[str, Any]]:
        """End-of-stream: force-terminate every still-live track and return them."""
        out: List[Track] = []
        for t in list(self.tracked_tracks) + list(self.lost_tracks):
            if t.state != TrackState.Removed:
                t.mark_removed()
                out.append(t)
        self.tracked_tracks.clear()
        self.lost_tracks.clear()
        self.removed_tracks.extend(out)
        return [t.as_dict() for t in out]

    @property
    def active_count(self) -> int:
        return len([t for t in self.tracked_tracks if t.is_activated])


# --------------------------------------------------------------------------- #
#  Local event deduplication                                                   #
# --------------------------------------------------------------------------- #
def _to_epoch(ts: Any) -> Optional[float]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        v = float(ts)
        return v / 1000.0 if v > 1e11 else v
    try:
        from datetime import datetime

        s = str(ts).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        try:
            return float(ts)
        except Exception:
            return None


class TrackEventDeduplicator:
    """Guarantees **one** consolidated AI event per completed vehicle track.

    Continuous video emits a detection every frame; without this guard a single
    vehicle passing one camera would generate hundreds of near-identical events.
    Rules:
      * a ``(camera_id, track_id)`` pair emits at most once
      * the same readable plate on the same camera inside ``replay_window_seconds``
        is suppressed (absorbs ByteTrack ID switches / quick re-entries)
    """

    def __init__(self, replay_window_seconds: float = 5.0) -> None:
        self.replay_window_seconds = replay_window_seconds
        self._emitted: set = set()                     # (camera_id, track_id)
        self._recent_plate_ts: Dict[tuple, float] = {}  # (camera_id, plate) -> epoch

    def should_emit(
        self,
        camera_id: str,
        track_id: Any,
        plate_number: Optional[str] = None,
        timestamp: Any = None,
    ) -> bool:
        key = (str(camera_id), str(track_id))
        if key in self._emitted:
            return False

        readable = (
            plate_number
            and plate_number != "UNKNOWN"
            and not str(plate_number).startswith("UNPLATED_TRACK_")
        )
        if readable:
            pkey = (str(camera_id), str(plate_number))
            ts = _to_epoch(timestamp)
            last = self._recent_plate_ts.get(pkey)
            if last is not None and ts is not None and abs(ts - last) < self.replay_window_seconds:
                self._emitted.add(key)          # remember so we never re-check it
                return False
            if ts is not None:
                self._recent_plate_ts[pkey] = ts

        self._emitted.add(key)
        return True

    def build_event(
        self,
        track: Dict[str, Any],
        camera_id: str,
        plate_info: Optional[Dict[str, Any]] = None,
        timestamp: Any = None,
        location: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Assemble the single consolidated event payload for a finished track."""
        plate_info = plate_info or {}
        plate_number = plate_info.get("plate_number", f"UNPLATED_TRACK_{track.get('track_id')}")
        plate_detected = bool(
            plate_number != "UNKNOWN" and not str(plate_number).startswith("UNPLATED_TRACK_")
        )
        return {
            "event_id": f"trk_{uuid.uuid4().hex[:12]}",
            "camera_id": camera_id,
            "location": location,
            "timestamp": timestamp,
            "track_id": track.get("track_id"),
            "vehicle": {
                "type": track.get("class"),
                "class": track.get("class"),
                "bbox": track.get("bbox"),
                "confidence": track.get("best_score", track.get("score")),
            },
            "license_plate": {
                "plate_detected": plate_detected,
                "plate_number": plate_number,
                "text": plate_number,
                "confidence": float(plate_info.get("confidence", 0.0)) if plate_detected else 0.0,
                "iou": plate_info.get("iou"),
            },
            "track_stats": {
                "frames_tracked": track.get("hits"),
                "start_frame": track.get("start_frame"),
                "end_frame": track.get("frame_id"),
            },
        }

    def reset(self) -> None:
        self._emitted.clear()
        self._recent_plate_ts.clear()
