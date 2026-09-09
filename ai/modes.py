"""
ai/modes.py

Phase 17 Step 4 -- explicit AI processing modes.

The pipeline already does detection -> tracking -> ANPR/OCR in one call
(``ai.pipeline.AIPipeline.process_frame``) with OCR throttled by
consensus stability (``ocr_throttle_frames``). This module makes the
*intent* explicit and independently configurable per camera, without
rewriting that pipeline: a mode is just a named bundle of
(run_tracking, run_ocr, ocr_priority_boost) flags that
``AIPipeline.process_frame`` (and the scheduled consumer) read to decide
how much work to do for a given camera.

  DETECTION  -- YOLO vehicle detection only, no tracking, no OCR. Cheapest;
                answers "is something there" without per-vehicle identity.
  TRACKING   -- detection + ByteTrack persistent IDs, still no OCR.
  ANPR       -- detection + tracking + plate localization + OCR + temporal
                fusion (the full pipeline as it exists today).
  ALERT      -- same work as ANPR, but flagged so the fair scheduler /
                adaptive sampler treat this camera's frames as CRITICAL
                priority (watchlist-hit or anomaly-triggered cameras).

Only ANPR and ALERT actually invoke the OCR engine -- Step 4's principle
("ANPR/OCR must not block the entire camera processing pipeline") is
enforced by keeping OCR itself off entirely for DETECTION/TRACKING-mode
cameras, and by ``ai.ocr_executor.OCRExecutor`` bounding/async-ing OCR
attempts for ANPR/ALERT-mode cameras (see that module).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from ai.scheduler import CameraPriority


class ProcessingMode:
    DETECTION = "DETECTION"
    TRACKING = "TRACKING"
    ANPR = "ANPR"
    ALERT = "ALERT"

    ALL = (DETECTION, TRACKING, ANPR, ALERT)


@dataclass(frozen=True)
class ModeFlags:
    run_tracking: bool
    run_ocr: bool
    default_priority: str


_MODE_FLAGS: Dict[str, ModeFlags] = {
    ProcessingMode.DETECTION: ModeFlags(run_tracking=False, run_ocr=False, default_priority=CameraPriority.BACKGROUND),
    ProcessingMode.TRACKING: ModeFlags(run_tracking=True, run_ocr=False, default_priority=CameraPriority.NORMAL),
    ProcessingMode.ANPR: ModeFlags(run_tracking=True, run_ocr=True, default_priority=CameraPriority.NORMAL),
    ProcessingMode.ALERT: ModeFlags(run_tracking=True, run_ocr=True, default_priority=CameraPriority.CRITICAL),
}


def mode_flags(mode: str) -> ModeFlags:
    if mode not in _MODE_FLAGS:
        raise ValueError(f"unknown processing mode {mode!r}, expected one of {ProcessingMode.ALL}")
    return _MODE_FLAGS[mode]


class ModeRegistry:
    """Per-camera processing-mode assignment. Defaults every camera to
    ``ANPR`` (byte-for-byte today's actual pipeline behavior: detection +
    tracking + OCR, unconditionally) -- so a caller that never touches this
    registry gets the exact pre-Phase-17 behavior."""

    def __init__(self, default_mode: str = ProcessingMode.ANPR) -> None:
        if default_mode not in ProcessingMode.ALL:
            raise ValueError(f"unknown default mode {default_mode!r}")
        self._default_mode = default_mode
        self._modes: Dict[str, str] = {}

    def set_mode(self, camera_id: str, mode: str) -> None:
        if mode not in ProcessingMode.ALL:
            raise ValueError(f"unknown processing mode {mode!r}")
        self._modes[camera_id] = mode

    def get_mode(self, camera_id: str) -> str:
        return self._modes.get(camera_id, self._default_mode)

    def get_flags(self, camera_id: str) -> ModeFlags:
        return mode_flags(self.get_mode(camera_id))

    def snapshot(self) -> Dict[str, str]:
        return dict(self._modes)
