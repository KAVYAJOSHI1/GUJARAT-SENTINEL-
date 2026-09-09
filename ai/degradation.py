"""
ai/degradation.py

Phase 17 Step 7 -- explicit system load states with measurable thresholds,
and graceful, explainable degradation.

Three states:

  HEALTHY     -- normal operation, no sampling reduction.
  DEGRADED    -- one or more measurable thresholds exceeded; BACKGROUND
                 then NORMAL cameras get reduced sampling (see
                 ai.sampling's _DEGRADED_MULTIPLIER); CRITICAL/HIGH and
                 ANPR/ALERT-mode cameras are unaffected.
  OVERLOADED  -- a higher threshold exceeded; every non-CRITICAL priority
                 is reduced further and ANPR sampling frequency drops too;
                 CRITICAL cameras are the last to be touched.

Thresholds are plain numbers on inputs the process can actually measure
(CPU%, event-queue backpressure ratio, OCR-queue backpressure ratio,
scheduler starvation-event rate) -- nothing here is invented; a caller
that supplies fewer inputs just gets a decision based on what it did
supply (missing inputs are treated as "not overloaded on this axis", never
fabricated as a number).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


class SystemLoadState:
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OVERLOADED = "OVERLOADED"

    ALL = (HEALTHY, DEGRADED, OVERLOADED)


@dataclass(frozen=True)
class DegradationThresholds:
    """Every threshold is a plain, documented number -- change these to
    retune, but they are never silently overridden per-request."""
    cpu_degraded_pct: float = 70.0
    cpu_overloaded_pct: float = 90.0
    queue_ratio_degraded: float = 0.5     # event/OCR queue depth / maxsize
    queue_ratio_overloaded: float = 0.85
    starvation_rate_degraded: float = 0.05   # starvation events / total processed, per sample window
    starvation_rate_overloaded: float = 0.2


@dataclass
class DegradationInputs:
    cpu_percent: Optional[float] = None
    event_queue_depth: Optional[int] = None
    event_queue_maxsize: Optional[int] = None
    ocr_queue_depth: Optional[int] = None
    ocr_queue_maxsize: Optional[int] = None
    starvation_events: int = 0
    frames_processed: int = 0


@dataclass
class DegradationReport:
    state: str
    reasons: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)

    def explain(self) -> str:
        lines = [f"SYSTEM: {self.state}"]
        if self.reasons:
            lines.append("Reason: " + "; ".join(self.reasons))
        for a in self.actions:
            lines.append(a)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {"state": self.state, "reasons": list(self.reasons), "actions": list(self.actions)}


class SystemLoadMonitor:
    def __init__(self, thresholds: Optional[DegradationThresholds] = None) -> None:
        self.thresholds = thresholds or DegradationThresholds()

    @staticmethod
    def _ratio(depth: Optional[int], maxsize: Optional[int]) -> Optional[float]:
        if depth is None or not maxsize:
            return None
        return depth / maxsize

    def evaluate(self, inputs: DegradationInputs) -> DegradationReport:
        t = self.thresholds
        reasons_degraded: List[str] = []
        reasons_overloaded: List[str] = []

        if inputs.cpu_percent is not None:
            if inputs.cpu_percent >= t.cpu_overloaded_pct:
                reasons_overloaded.append(f"CPU {inputs.cpu_percent:.0f}% >= overloaded threshold {t.cpu_overloaded_pct:.0f}%")
            elif inputs.cpu_percent >= t.cpu_degraded_pct:
                reasons_degraded.append(f"CPU {inputs.cpu_percent:.0f}% >= degraded threshold {t.cpu_degraded_pct:.0f}%")

        eq_ratio = self._ratio(inputs.event_queue_depth, inputs.event_queue_maxsize)
        if eq_ratio is not None:
            if eq_ratio >= t.queue_ratio_overloaded:
                reasons_overloaded.append(f"event queue {eq_ratio:.0%} full >= overloaded threshold {t.queue_ratio_overloaded:.0%}")
            elif eq_ratio >= t.queue_ratio_degraded:
                reasons_degraded.append(f"event queue {eq_ratio:.0%} full >= degraded threshold {t.queue_ratio_degraded:.0%}")

        oq_ratio = self._ratio(inputs.ocr_queue_depth, inputs.ocr_queue_maxsize)
        if oq_ratio is not None:
            if oq_ratio >= t.queue_ratio_overloaded:
                reasons_overloaded.append(f"OCR queue {oq_ratio:.0%} full >= overloaded threshold {t.queue_ratio_overloaded:.0%}")
            elif oq_ratio >= t.queue_ratio_degraded:
                reasons_degraded.append(f"OCR queue {oq_ratio:.0%} full >= degraded threshold {t.queue_ratio_degraded:.0%}")

        if inputs.frames_processed > 0:
            rate = inputs.starvation_events / inputs.frames_processed
            if rate >= t.starvation_rate_overloaded:
                reasons_overloaded.append(f"starvation rate {rate:.1%} >= overloaded threshold {t.starvation_rate_overloaded:.0%}")
            elif rate >= t.starvation_rate_degraded:
                reasons_degraded.append(f"starvation rate {rate:.1%} >= degraded threshold {t.starvation_rate_degraded:.0%}")

        if reasons_overloaded:
            actions = [
                "Background sampling reduced (10% of max)",
                "Normal-priority sampling reduced (25% of max)",
                "High-priority sampling reduced (50% of max)",
                "ANPR/OCR sampling frequency reduced",
                "Critical/alert cameras preserved at full target FPS (reduced only as a last resort)",
            ]
            return DegradationReport(state=SystemLoadState.OVERLOADED, reasons=reasons_overloaded, actions=actions)

        if reasons_degraded:
            actions = [
                "Background sampling reduced (30% of max)",
                "Normal-priority sampling reduced (60% of max)",
                "Critical and high-priority cameras preserved at full target FPS",
            ]
            return DegradationReport(state=SystemLoadState.DEGRADED, reasons=reasons_degraded, actions=actions)

        return DegradationReport(state=SystemLoadState.HEALTHY, reasons=[], actions=["No sampling reduction in effect"])
