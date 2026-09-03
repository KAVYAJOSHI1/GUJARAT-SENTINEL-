"""
ai/tracking/track_association.py

Intersection-over-Union geometry helpers and the Track <-> Plate associator.

The tracking engine (Prajin) receives, per frame:
  * vehicle bounding boxes tagged with a persistent ``track_id`` (produced by
    ``ai.tracking.tracker.ByteTrackTracker``)
  * license-plate region bounding boxes + candidate OCR strings (produced by
    Kavya's ANPR module, in full-frame pixel coordinates)

``associate_plates_to_tracks`` binds each plate string to the vehicle track whose
box best overlaps / contains it, solving the assignment with the Hungarian
algorithm (``scipy.optimize.linear_sum_assignment``).  Tracks that never receive a
plate are given a stable temporary identity ``UNPLATED_TRACK_{id}`` so the pipeline
never crashes on unplated vehicles (DEVELOPER_README section 15).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

logger = logging.getLogger("TrackAssociation")

Box = Sequence[float]  # [x1, y1, x2, y2]


def _as_xyxy(box: Box) -> np.ndarray:
    arr = np.asarray(box, dtype=np.float64).reshape(-1)[:4]
    x1, y1, x2, y2 = arr
    return np.array([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)], dtype=np.float64)


def iou(box_a: Box, box_b: Box) -> float:
    """Standard Intersection-over-Union of two ``[x1, y1, x2, y2]`` boxes."""
    a = _as_xyxy(box_a)
    b = _as_xyxy(box_b)
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return float(inter / union) if union > 0 else 0.0


def containment(inner: Box, outer: Box) -> float:
    """Fraction of ``inner``'s area that lies inside ``outer`` (inter / area(inner)).

    A license-plate box is tiny relative to its parent vehicle box, so raw IoU is
    always near-zero even for a perfect match; containment is the meaningful
    signal for plate -> vehicle binding.
    """
    a = _as_xyxy(inner)
    b = _as_xyxy(outer)
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_inner = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    return float(inter / area_inner) if area_inner > 0 else 0.0


def iou_matrix(boxes_a: Sequence[Box], boxes_b: Sequence[Box]) -> np.ndarray:
    """Vectorised pairwise IoU. Returns an ``(len(a), len(b))`` matrix (0.0 padded)."""
    a = np.asarray([_as_xyxy(x) for x in boxes_a], dtype=np.float64).reshape(-1, 4)
    b = np.asarray([_as_xyxy(x) for x in boxes_b], dtype=np.float64).reshape(-1, 4)
    if a.shape[0] == 0 or b.shape[0] == 0:
        return np.zeros((a.shape[0], b.shape[0]), dtype=np.float64)

    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    ix1 = np.maximum(a[:, None, 0], b[None, :, 0])
    iy1 = np.maximum(a[:, None, 1], b[None, :, 1])
    ix2 = np.minimum(a[:, None, 2], b[None, :, 2])
    iy2 = np.minimum(a[:, None, 3], b[None, :, 3])
    iw = np.clip(ix2 - ix1, 0.0, None)
    ih = np.clip(iy2 - iy1, 0.0, None)
    inter = iw * ih
    union = area_a[:, None] + area_b[None, :] - inter
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(union > 0.0, inter / union, 0.0)
    return out.astype(np.float64)


def associate_plates_to_tracks(
    tracks: Sequence[Dict[str, Any]],
    plates: Sequence[Dict[str, Any]],
    affinity_threshold: float = 0.10,
    min_containment: float = 0.30,
) -> Dict[Any, Dict[str, Any]]:
    """Bind plate OCR strings to vehicle track IDs via IoU / containment + Hungarian.

    :param tracks:  list of ``{"track_id": int, "bbox": [x1,y1,x2,y2], ...}``
    :param plates:  list of ``{"bbox": [x1,y1,x2,y2], "plate_number"/"text": str,
                    "confidence": float}`` in full-frame pixel coordinates
    :param affinity_threshold: minimum overlap score to accept a match
    :param min_containment: containment below this is ignored (noise guard)
    :return: ``{track_id: {"plate_number", "confidence", "iou", "containment",
             "plate_bbox", "matched"}}`` for **every** input track; unmatched tracks
             get ``plate_number = "UNPLATED_TRACK_{track_id}"``.
    """
    result: Dict[Any, Dict[str, Any]] = {}
    track_boxes = [t["bbox"] for t in tracks]
    plate_boxes = [p["bbox"] for p in plates]

    ious = iou_matrix(track_boxes, plate_boxes)
    affinity = np.zeros_like(ious)
    for i, tb in enumerate(track_boxes):
        for j, pb in enumerate(plate_boxes):
            c = containment(pb, tb)
            affinity[i, j] = max(ious[i, j], c if c >= min_containment else 0.0)

    plate_for_track: Dict[int, int] = {}
    if affinity.size:
        row_ind, col_ind = linear_sum_assignment(1.0 - affinity)
        for r, cidx in zip(row_ind, col_ind):
            if affinity[r, cidx] >= affinity_threshold:
                plate_for_track[int(r)] = int(cidx)

    for i, tr in enumerate(tracks):
        tid = tr.get("track_id", i)
        if i in plate_for_track:
            p = plates[plate_for_track[i]]
            plate_text = p.get("plate_number") or p.get("text") or "UNKNOWN"
            result[tid] = {
                "track_id": tid,
                "plate_number": plate_text,
                "confidence": float(p.get("confidence", 0.0)),
                "iou": round(float(ious[i, plate_for_track[i]]), 4),
                "containment": round(containment(p["bbox"], tr["bbox"]), 4),
                "plate_bbox": [float(v) for v in p["bbox"]],
                "matched": True,
            }
        else:
            result[tid] = {
                "track_id": tid,
                "plate_number": f"UNPLATED_TRACK_{tid}",
                "confidence": 0.0,
                "iou": 0.0,
                "containment": 0.0,
                "plate_bbox": None,
                "matched": False,
            }
    return result
