"""
ai/sampling.py

Phase 17 Step 3 -- adaptive per-camera frame sampling.

Not every incoming frame needs to go through the expensive AI pipeline.
This module decides, per camera and per incoming frame, whether to ACCEPT
it for AI processing or reject it -- and if rejected, WHY (never a silent
drop; see ``ai.scheduler.DropReason``).

Three independent inputs feed the decision, all optional and all off by
default (so importing/using this module with defaults is a no-op that
accepts every frame -- existing default behavior is unaffected until a
caller actually configures target FPS below source FPS):

  1. Per-camera target/min/max FPS.
  2. Camera priority (``ai.scheduler.CameraPriority``) -- shifts the
     effective target within [min_fps, max_fps] toward the max for
     CRITICAL/HIGH, toward the min for BACKGROUND.
  3. System load state (``ai.degradation.SystemLoadState``) -- under
     DEGRADED/OVERLOADED, BACKGROUND (then NORMAL) cameras get their
     effective target reduced first; CRITICAL is the last to be touched
     and only degrades under OVERLOADED, never below its own min_fps.

A cheap, OPT-IN motion/scene-activity signal (``MotionActivityEstimator``)
can additionally boost a camera's effective sampling rate when recent
frames show real motion -- capped at max_fps, never used to exceed it.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from ai.scheduler import CameraPriority, DropReason

# One "notch" of priority above/below NORMAL shifts the target this far
# toward max_fps (CRITICAL/HIGH) or min_fps (BACKGROUND) -- a documented,
# simple linear interpolation, not a magic number pulled from nowhere.
_PRIORITY_FRACTION: Dict[str, float] = {
    CameraPriority.CRITICAL: 1.0,   # always at max_fps (subject to load-shedding floor)
    CameraPriority.HIGH: 0.75,
    CameraPriority.NORMAL: 0.5,
    CameraPriority.BACKGROUND: 0.15,
}

# Under load, which priorities have their effective fraction pulled toward
# min_fps first. CRITICAL is deliberately absent from DEGRADED -- Step 7 of
# the brief: "preserve CRITICAL cameras" even while degraded, only touched
# once OVERLOADED (and even then floored at 50% of its own fraction, never
# below min_fps).
_DEGRADED_MULTIPLIER: Dict[str, float] = {
    CameraPriority.CRITICAL: 1.0,
    CameraPriority.HIGH: 0.85,
    CameraPriority.NORMAL: 0.6,
    CameraPriority.BACKGROUND: 0.3,
}
_OVERLOADED_MULTIPLIER: Dict[str, float] = {
    CameraPriority.CRITICAL: 0.7,
    CameraPriority.HIGH: 0.5,
    CameraPriority.NORMAL: 0.25,
    CameraPriority.BACKGROUND: 0.1,
}


@dataclass
class SamplingConfig:
    target_fps: Optional[float] = None   # None = uncapped (accept every frame)
    min_fps: float = 0.5
    max_fps: float = 15.0
    motion_influence: bool = False
    motion_boost_factor: float = 1.5     # effective fps multiplier when activity is high


@dataclass
class SamplingDecision:
    accept: bool
    reason: Optional[str] = None
    effective_fps: Optional[float] = None


class AdaptiveFrameSampler:
    """One instance shared across cameras; per-camera config + per-camera
    last-accepted timestamp is kept internally (bounded by camera count,
    which is bounded by the registry -- never by frame arrival rate)."""

    def __init__(self) -> None:
        self._config: Dict[str, SamplingConfig] = {}
        self._last_accept_mono: Dict[str, float] = {}
        self._priority: Dict[str, str] = {}

    def configure(self, camera_id: str, config: SamplingConfig) -> None:
        self._config[camera_id] = config

    def set_priority(self, camera_id: str, priority: str) -> None:
        self._priority[camera_id] = priority

    def _effective_target_fps(
        self, camera_id: str, config: SamplingConfig, load_state: Optional[str], activity_score: Optional[float],
    ) -> float:
        priority = self._priority.get(camera_id, CameraPriority.NORMAL)
        fraction = _PRIORITY_FRACTION.get(priority, 0.5)

        if load_state == "DEGRADED":
            fraction *= _DEGRADED_MULTIPLIER.get(priority, 0.5)
        elif load_state == "OVERLOADED":
            fraction *= _OVERLOADED_MULTIPLIER.get(priority, 0.25)

        base = config.min_fps + fraction * (config.max_fps - config.min_fps)

        if config.motion_influence and activity_score is not None and activity_score > 0.5:
            base *= config.motion_boost_factor

        return max(config.min_fps, min(config.max_fps, base))

    def should_process(
        self,
        camera_id: str,
        *,
        now: Optional[float] = None,
        load_state: Optional[str] = None,
        activity_score: Optional[float] = None,
        paused: bool = False,
    ) -> SamplingDecision:
        """Decide whether the frame arriving right now for ``camera_id``
        should be handed to the AI pipeline. Never raises."""
        now = time.monotonic() if now is None else now

        if paused:
            return SamplingDecision(accept=False, reason=DropReason.CAMERA_PAUSED)

        config = self._config.get(camera_id)
        if config is None or config.target_fps is None:
            # No sampling configured for this camera -- accept everything
            # (byte-for-byte the pre-Phase-17 default behavior).
            return SamplingDecision(accept=True, effective_fps=None)

        effective_fps = self._effective_target_fps(camera_id, config, load_state, activity_score)
        min_interval = 1.0 / effective_fps if effective_fps > 0 else 0.0

        last = self._last_accept_mono.get(camera_id)
        if last is not None and (now - last) < min_interval:
            return SamplingDecision(accept=False, reason=DropReason.RATE_LIMIT, effective_fps=effective_fps)

        self._last_accept_mono[camera_id] = now
        return SamplingDecision(accept=True, effective_fps=effective_fps)


class MotionActivityEstimator:
    """Optional, cheap frame-difference activity score in [0, 1]. Downsizes
    to a small fixed size before diffing so cost stays roughly constant
    regardless of source resolution -- this must never itself become a
    pipeline bottleneck. Off unless a caller explicitly calls score()."""

    def __init__(self, size: Tuple[int, int] = (64, 48)) -> None:
        self._size = size
        self._prev_gray: Dict[str, "object"] = {}

    def score(self, camera_id: str, frame) -> Optional[float]:
        try:
            import cv2
            import numpy as np
        except Exception:  # noqa: BLE001 -- optional dependency at call time
            return None
        if frame is None:
            return None
        try:
            small = cv2.resize(frame, self._size, interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
            prev = self._prev_gray.get(camera_id)
            self._prev_gray[camera_id] = gray
            if prev is None:
                return None
            diff = cv2.absdiff(gray, prev)
            return float(min(1.0, (float(np.mean(diff)) / 255.0) * 8.0))
        except Exception:  # noqa: BLE001 -- activity scoring is best-effort
            return None
