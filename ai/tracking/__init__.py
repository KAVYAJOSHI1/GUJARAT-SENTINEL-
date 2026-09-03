"""
SENTINEL Vehicle Tracking & Cross-Camera Correlation engine (Prajin).

  tracker.py            - ByteTrack multi-object tracker (NumPy/SciPy),
                          Kalman occlusion bridging, per-camera persistent IDs,
                          and local event deduplication.
  track_association.py  - IoU / containment geometry + plate -> track binder.
  correlation.py        - cross-camera chronological trajectory builder.
"""
from ai.tracking.correlation import CrossCameraCorrelator, normalize_plate, parse_timestamp
from ai.tracking.track_association import (
    associate_plates_to_tracks,
    containment,
    iou,
    iou_matrix,
)
from ai.tracking.tracker import (
    ByteTrackTracker,
    KalmanFilter,
    Track,
    TrackEventDeduplicator,
    TrackState,
)

__all__ = [
    "ByteTrackTracker",
    "Track",
    "TrackState",
    "KalmanFilter",
    "TrackEventDeduplicator",
    "iou",
    "iou_matrix",
    "containment",
    "associate_plates_to_tracks",
    "CrossCameraCorrelator",
    "normalize_plate",
    "parse_timestamp",
]
