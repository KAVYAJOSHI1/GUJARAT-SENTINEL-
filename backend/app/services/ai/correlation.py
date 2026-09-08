"""
Advanced Cross-Camera Correlation (Phase 14 §2).

An explainable intelligence layer OVER the existing journey system (it does
not replace `_build_transitions`). For a candidate hop between two sightings
it combines eight signals into a weighted, explained score:

    plate_score        exact / normalised / fuzzy plate agreement
    appearance_score   visual embedding cosine (Phase 14 §1)
    type_score         vehicle-type agreement
    color_score        vehicle-colour agreement
    temporal_score     is the observed gap feasible vs the historical /
                       distance-model travel band (Phase 14 §3)
    geographic_score   are the cameras plausibly connected (distance)
    ----------------------------------------------------------------
    overall_score      sum(weight_i * score_i) / sum(weight_i present)
    confidence         HIGH only with an exact plate match AND a feasible
                       time; else MEDIUM / LOW / INSUFFICIENT by overall
    verdict            CONFIRMED  (exact plate + feasible)  |  INFERRED

`match_method` and every sub-score are returned so the UI can show the
breakdown. Inference is never silently promoted to fact.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session

from app.config import settings
from app.models.base import ConfidenceLevel
from app.models.vehicle_event import VehicleEvent
from app.services.ai.camera_transitions import CameraTransitionService
from app.services.ai.reid import VehicleReIDService, cosine_similarity

_UNKNOWN = "UNKNOWN"


def _edit_distance_le_1(a: str, b: str) -> bool:
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(x != y for x, y in zip(a, b)) == 1
    # one insertion/deletion
    short, lng = (a, b) if la < lb else (b, a)
    i = j = 0
    skipped = False
    while i < len(short) and j < len(lng):
        if short[i] == lng[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            skipped = True
            j += 1
    return True


class VehicleCorrelationService:
    def __init__(self, db: Session):
        self.db = db
        self.reid = VehicleReIDService(db)
        self.transitions = CameraTransitionService(db)

    # ------------------------------------------------------------------ #
    def _event(self, event_id: str) -> Optional[VehicleEvent]:
        return self.db.get(VehicleEvent, event_id)

    # ---- individual signals ------------------------------------------ #
    @staticmethod
    def _plate_score(a: str, b: str) -> tuple[float, str]:
        a = (a or "").upper()
        b = (b or "").upper()
        if a == _UNKNOWN or b == _UNKNOWN or not a or not b:
            return 0.35, "one or both plates UNKNOWN"
        if a == b:
            return 1.0, "exact normalised plate match"
        if _edit_distance_le_1(a, b):
            return 0.82, "plate differs by one character (possible OCR error)"
        return 0.0, "plates are different"

    @staticmethod
    def _type_score(a: Optional[str], b: Optional[str]) -> tuple[float, str]:
        if not a or not b:
            return 0.5, "vehicle type missing on one sighting"
        if a == b:
            return 1.0, f"both '{a}'"
        return 0.0, f"'{a}' vs '{b}'"

    @staticmethod
    def _color_score(a: Optional[str], b: Optional[str]) -> tuple[float, str]:
        if not a or not b:
            return 0.6, "vehicle colour missing on one sighting"
        if a.lower() == b.lower():
            return 1.0, f"both '{a}'"
        return 0.2, f"'{a}' vs '{b}' (colour reads are noisy)"

    def _appearance_score(self, id_a: str, id_b: str) -> tuple[float, str]:
        ra = self.reid._ensure_row(id_a)
        rb = self.reid._ensure_row(id_b)
        if not ra or not rb:
            return 0.5, "no embedding available"
        sim = cosine_similarity(ra.embedding, rb.embedding)
        return round(sim, 3), f"appearance cosine {sim:.2f} ({ra.model_name})"

    def _temporal_score(self, from_cam: str, to_cam: str, dt: int) -> tuple[float, str, dict]:
        cls = self.transitions.classify(from_cam, to_cam, dt)
        verdict = cls["classification"]
        mapping = {
            "PLAUSIBLE": 1.0, "SLOW": 0.55, "FAST": 0.45,
            "IMPOSSIBLE": 0.05, "UNKNOWN": 0.5,
        }
        band = cls["expected"]
        return mapping[verdict], f"{verdict} vs {band['source']} band", cls

    def _geographic_score(self, band: dict) -> tuple[float, str]:
        dist = band.get("distance_meters")
        if dist is None:
            return 0.5, "camera geometry unavailable"
        if dist <= settings.CORRELATION_GEO_NEAR_M:
            return 1.0, f"cameras {int(dist)} m apart"
        if dist <= settings.CORRELATION_GEO_FAR_M:
            frac = (dist - settings.CORRELATION_GEO_NEAR_M) / (
                settings.CORRELATION_GEO_FAR_M - settings.CORRELATION_GEO_NEAR_M
            )
            return round(1.0 - 0.6 * frac, 3), f"cameras {int(dist)} m apart"
        return 0.3, f"cameras {int(dist/1000)} km apart (weak geographic link)"

    # ------------------------------------------------------------------ #
    def analyze_pair(self, event_id_a: str, event_id_b: str) -> Optional[dict]:
        a = self._event(event_id_a)
        b = self._event(event_id_b)
        if not a or not b:
            return None
        # order chronologically
        if a.timestamp > b.timestamp:
            a, b = b, a
            event_id_a, event_id_b = event_id_b, event_id_a

        dt = int((b.timestamp - a.timestamp).total_seconds())

        plate_s, plate_note = self._plate_score(a.plate_number_normalized, b.plate_number_normalized)
        appr_s, appr_note = self._appearance_score(a.id, b.id)
        type_s, type_note = self._type_score(a.vehicle_type, b.vehicle_type)
        color_s, color_note = self._color_score(a.vehicle_color, b.vehicle_color)
        temporal_s, temporal_note, temporal_detail = self._temporal_score(
            a.camera_id, b.camera_id, dt
        )
        geo_s, geo_note = self._geographic_score(temporal_detail["expected"])

        w = settings
        components = [
            ("plate", plate_s, w.CORRELATION_W_PLATE, plate_note),
            ("appearance", appr_s, w.CORRELATION_W_APPEARANCE, appr_note),
            ("vehicle_type", type_s, w.CORRELATION_W_TYPE, type_note),
            ("color", color_s, w.CORRELATION_W_COLOR, color_note),
            ("temporal", temporal_s, w.CORRELATION_W_TEMPORAL, temporal_note),
            ("geographic", geo_s, w.CORRELATION_W_GEOGRAPHIC, geo_note),
        ]
        wsum = sum(weight for _, _, weight, _ in components)
        overall = sum(score * weight for _, score, weight, _ in components) / wsum

        exact_plate = plate_s >= 1.0
        feasible = temporal_detail["classification"] in ("PLAUSIBLE", "SLOW", "UNKNOWN")
        impossible = temporal_detail["classification"] == "IMPOSSIBLE"

        if exact_plate and feasible:
            level = ConfidenceLevel.HIGH
            verdict = "CONFIRMED"
        elif exact_plate and impossible:
            level = ConfidenceLevel.LOW
            verdict = "INFERRED"
        elif overall >= settings.CORRELATION_CONF_MEDIUM:
            level = ConfidenceLevel.MEDIUM
            verdict = "INFERRED"
        elif overall >= settings.CORRELATION_CONF_LOW:
            level = ConfidenceLevel.LOW
            verdict = "INFERRED"
        else:
            level = ConfidenceLevel.INSUFFICIENT
            verdict = "INFERRED"

        if exact_plate:
            method = "exact plate match + temporal/geographic feasibility check"
        elif plate_s >= 0.8:
            method = "near-plate (1-char) match corroborated by appearance/time/geo"
        else:
            method = "multi-signal appearance + type + colour + temporal + geographic correlation"

        return {
            "event_id_a": event_id_a,
            "event_id_b": event_id_b,
            "from_camera_id": a.camera_id,
            "from_camera_code": a.camera_code,
            "to_camera_id": b.camera_id,
            "to_camera_code": b.camera_code,
            "time_diff_seconds": dt,
            "scores": {
                "plate_score": round(plate_s, 3),
                "appearance_score": round(appr_s, 3),
                "type_score": round(type_s, 3),
                "color_score": round(color_s, 3),
                "temporal_score": round(temporal_s, 3),
                "geographic_score": round(geo_s, 3),
            },
            "explanations": {name: note for name, _, _, note in components},
            "weights": {name: weight for name, _, weight, _ in components},
            "overall_score": round(overall, 3),
            "confidence_level": level.value,
            "verdict": verdict,
            "match_method": method,
            "transition_classification": temporal_detail["classification"],
            "expected_travel": temporal_detail["expected"],
            "disclaimer": (
                "CONFIRMED requires an exact plate match with a feasible travel "
                "time. Otherwise this is an INFERRED correlation -- a lead, not "
                "a fact."
            ),
        }

    def analyze_plate_journey(self, plate_normalized: str, *, limit: int = 50) -> dict:
        """Analyse every consecutive hop for one plate's sightings."""
        from sqlalchemy import select

        rows = self.db.execute(
            select(VehicleEvent)
            .where(VehicleEvent.plate_number_normalized == plate_normalized.upper())
            .order_by(VehicleEvent.timestamp.asc())
            .limit(min(limit, settings.AI_MAX_RESULTS))
        ).scalars().all()
        hops = []
        for a, b in zip(rows, rows[1:]):
            if a.camera_id == b.camera_id:
                continue
            res = self.analyze_pair(a.id, b.id)
            if res:
                hops.append(res)
        confirmed = sum(1 for h in hops if h["verdict"] == "CONFIRMED")
        return {
            "plate": plate_normalized.upper(),
            "sightings": len(rows),
            "hops_analyzed": len(hops),
            "confirmed": confirmed,
            "inferred": len(hops) - confirmed,
            "hops": hops,
        }
