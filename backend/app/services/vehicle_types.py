"""
Canonical vehicle-type handling.

The AI pipeline classifies vehicles with a COCO-pretrained YOLOv8n whose
relevant classes are exactly: **car, motorcycle, bus, truck**
(`ai/detection/vehicle_detector.py::DEFAULT_VEHICLE_CLASSES`). Events also
carry a flat-form `vehicle_type` fallback from older callers.

`canonical_vehicle_type()` produces ONE consistent spelling for storage,
API responses, and the UI:
  * lower-cased, trimmed
  * a few well-known synonyms folded onto the canonical class
  * `None` in -> `None` out  (never invent a type)
  * an unrecognised but non-empty string is kept as-is (lower-cased) --
    we don't drop real classifier output just because it isn't in our set,
    but we also don't upgrade it to a real class.

This is deliberately NOT a hard enum: keeping an unexpected value visible
is more honest than silently mapping it to "car".
"""
from __future__ import annotations

from typing import Optional

# The classes the current detector can actually emit, plus a couple of
# Indian-traffic classes that a future fine-tuned model would add.
CANONICAL_VEHICLE_TYPES = (
    "car",
    "motorcycle",
    "bus",
    "truck",
    "bicycle",
    "auto-rickshaw",
)

_SYNONYMS = {
    "motorbike": "motorcycle",
    "motor cycle": "motorcycle",
    "bike": "motorcycle",
    "scooter": "motorcycle",
    "lorry": "truck",
    "hgv": "truck",
    "van": "truck",
    "pickup": "truck",
    "minibus": "bus",
    "coach": "bus",
    "sedan": "car",
    "hatchback": "car",
    "suv": "car",
    "taxi": "car",
    "cab": "car",
    "cycle": "bicycle",
    "rickshaw": "auto-rickshaw",
    "auto": "auto-rickshaw",
    "autorickshaw": "auto-rickshaw",
    "tuk-tuk": "auto-rickshaw",
    "three wheeler": "auto-rickshaw",
    "3-wheeler": "auto-rickshaw",
}


def canonical_vehicle_type(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    v = str(raw).strip().lower()
    if not v:
        return None
    if v in CANONICAL_VEHICLE_TYPES:
        return v
    return _SYNONYMS.get(v, v)
