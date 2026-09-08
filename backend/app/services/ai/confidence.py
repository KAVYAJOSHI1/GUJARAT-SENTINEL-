"""
Confidence / explainability helpers (phase brief §5).

Every AI-derived result must distinguish FACT from AI INFERENCE and carry a
confidence level. These functions produce ONE consistent mapping used by
the Copilot, NL search and the anomaly detector.
"""
from __future__ import annotations

from app.models.base import ConfidenceLevel


def level_from_score(score: float) -> ConfidenceLevel:
    if score >= 0.8:
        return ConfidenceLevel.HIGH
    if score >= 0.55:
        return ConfidenceLevel.MEDIUM
    if score > 0.0:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.INSUFFICIENT


def vehicle_match_confidence(sighting_count: int, distinct_cameras: int, exact_plate: bool):
    """Confidence that a set of sightings really is the queried vehicle.

    FACT part: the sightings are exact `plate_number_normalized` matches
    from `vehicle_events`. The INFERENCE is only "these belong to one
    continuous vehicle movement" -- more sightings across more cameras with
    an exact plate raises it."""
    if sighting_count == 0:
        return 0.0, ConfidenceLevel.INSUFFICIENT, "no matching sightings in recorded data"
    base = 0.55 if exact_plate else 0.35
    base += min(0.25, 0.05 * sighting_count)
    base += min(0.20, 0.07 * max(0, distinct_cameras - 1))
    score = round(min(0.98, base), 2)
    method = (
        f"exact plate match on {sighting_count} sighting(s) across "
        f"{distinct_cameras} camera(s)" if exact_plate
        else f"partial plate match on {sighting_count} sighting(s)"
    )
    return score, level_from_score(score), method


def anomaly_confidence(duration_s: float, count: int, displacement_m: float | None,
                       min_s: float, min_count: int, max_disp: float):
    """Confidence that a track is really a STOPPED vehicle (vs a slow /
    congested pass). Higher for longer dwell, more detections, smaller
    displacement."""
    dur_factor = min(1.0, duration_s / (min_s * 2.5))
    cnt_factor = min(1.0, count / (min_count * 2.0))
    if displacement_m is None:
        disp_factor = 0.6  # no geo -> can't confirm it didn't move
    else:
        disp_factor = max(0.0, 1.0 - (displacement_m / max_disp))
    score = round(0.25 + 0.35 * dur_factor + 0.20 * cnt_factor + 0.20 * disp_factor, 2)
    score = min(0.95, score)
    reason = (
        f"track held at one camera for {int(duration_s)}s across {count} detections"
        + (f"; max displacement {displacement_m:.0f} m" if displacement_m is not None
           else "; no per-event GPS to confirm displacement")
    )
    return score, level_from_score(score), reason
