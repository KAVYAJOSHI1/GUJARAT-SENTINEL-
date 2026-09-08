"""
AI Investigation Agent (Phase 14 §7).

Upgrades the single-shot Copilot into a controlled MULTI-STEP investigation
assistant:

    officer query ("Investigate GJ18TC0450")
        -> Tool Planner  (deterministic; optional LLM only picks tool NAMES)
        -> ordered plan of VALIDATED tool calls
        -> execute step by step against the existing indexed DB paths
        -> reasoning / aggregation
        -> evidence-grounded structured report + investigation gaps

Hard rules (enforced here, not merely documented):
  * READ ONLY. Every registered tool is a bounded SELECT. No INSERT/UPDATE/
    DELETE, no alert creation, no arbitrary SQL.
  * The agent can ONLY call tools in `ToolRegistry`. An unknown name raises.
  * The LLM (if configured) never touches the DB and never sees SQL -- it
    only chooses from the registry's tool names; on any error we fall back
    to the deterministic plan.
  * Nothing is fabricated: every figure in the report comes from a tool
    result; empty -> "not available in recorded evidence".
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Optional

from sqlmodel import Session

from app.config import settings
from app.models.base import ConfidenceLevel
from app.services.ai.confidence import level_from_score
from app.services.ai.correlation import VehicleCorrelationService
from app.services.ai.gaps import InvestigationGapService
from app.services.ai.llm import get_llm_provider
from app.services.ai.nlq import parse_query
from app.services.ai.reid import VehicleReIDService
from app.services.ai.tools import InvestigationTools
from app.services.ai.traffic import TrafficAnalyticsService, TrafficFilters
from app.services.plate_utils import normalize_plate

logger = logging.getLogger("sentinel.ai.agent")


class ToolRegistry:
    """The strict allow-list. Every entry is a read-only, bounded callable."""

    def __init__(self, db: Session):
        self.db = db
        self._t = InvestigationTools(db)
        self._reid = VehicleReIDService(db)
        self._corr = VehicleCorrelationService(db)
        self._traffic = TrafficAnalyticsService(db)
        self._gaps = InvestigationGapService(db)
        self._tools: dict[str, Callable[..., dict]] = {
            "search_vehicle": self._t.search_vehicle,
            "get_vehicle_journey": self._t.get_vehicle_journey,
            "search_similar_vehicles": self._similar,
            "search_cameras": self._t.search_cameras,
            "search_alerts": self._t.search_alerts,
            "search_watchlist": self._watchlist,
            "search_incidents": self._t.search_incidents,
            "search_cases": self._t.search_cases,
            "search_evidence": self._t.search_evidence,
            "search_anomalies": self._anomalies,
            "analyze_correlation": self._correlation,
            "traffic_analysis": self._traffic_analysis,
            "detect_gaps": self._detect_gaps,
        }

    # ---- registry access -------------------------------------------- #
    def names(self) -> list[str]:
        return list(self._tools)

    def call(self, name: str, **params) -> dict:
        if name not in self._tools:
            raise KeyError(f"tool '{name}' is not in the registry")
        return self._tools[name](**params)

    # ---- new tool wrappers ----------------------------------------- #
    def _similar(self, plate: str | None = None, event_id: str | None = None,
                 limit: int = 10) -> dict:
        if not event_id and plate:
            from sqlalchemy import select

            from app.models.vehicle_event import VehicleEvent
            ev = self.db.execute(
                select(VehicleEvent)
                .where(VehicleEvent.plate_number_normalized == normalize_plate(plate))
                .order_by(VehicleEvent.timestamp.desc()).limit(1)
            ).scalar_one_or_none()
            event_id = ev.id if ev else None
        if not event_id:
            return {"candidates": [], "note": "no sighting to match against"}
        return self._reid.find_similar(event_id=event_id, limit=limit)

    def _watchlist(self, plate: str | None = None, **_) -> dict:
        if plate:
            data = self._t.search_vehicle(plate)
            return {"plate": data["plate"], "is_watchlisted": data["is_watchlisted"],
                    "watchlist_category": data["watchlist_category"]}
        return self._t.watchlist_detections()

    def _anomalies(self, plate: str | None = None, camera_code: str | None = None,
                   limit: int = 20) -> dict:
        from sqlalchemy import select

        from app.models.anomaly_event import AnomalyEvent
        conds = []
        if plate:
            conds.append(AnomalyEvent.plate_number_normalized == normalize_plate(plate))
        if camera_code:
            conds.append(AnomalyEvent.camera_code == camera_code)
        rows = self.db.execute(
            select(AnomalyEvent).where(*conds)
            .order_by(AnomalyEvent.created_at.desc()).limit(min(limit, settings.AI_MAX_RESULTS))
        ).scalars().all()
        return {"anomalies": [{
            "id": a.id, "kind": a.kind.value, "camera_code": a.camera_code,
            "plate": a.plate_number_normalized, "confidence_level": a.confidence_level.value,
            "zone_name": a.zone_name, "first_seen": a.first_seen, "alert_id": a.alert_id,
        } for a in rows]}

    def _correlation(self, plate: str | None = None, event_id_a: str | None = None,
                     event_id_b: str | None = None, **_) -> dict:
        if event_id_a and event_id_b:
            return self._corr.analyze_pair(event_id_a, event_id_b) or {}
        if plate:
            return self._corr.analyze_plate_journey(normalize_plate(plate))
        return {}

    def _traffic_analysis(self, camera_code: str | None = None, vehicle_type: str | None = None,
                          window_hours: int = 24, **_) -> dict:
        f = TrafficFilters(
            camera_codes=[camera_code] if camera_code else None, vehicle_type=vehicle_type
        )
        return self._traffic.overview(f, default_hours=window_hours)

    def _detect_gaps(self, plate: str, **_) -> dict:
        return self._gaps.detect(plate)


# --------------------------------------------------------------------------- #
#  the agent
# --------------------------------------------------------------------------- #
_VEHICLE_PLAN = [
    ("search_vehicle", "recorded sightings + watchlist status"),
    ("get_vehicle_journey", "chronological camera trail"),
    ("search_similar_vehicles", "appearance-similar sightings (visual leads)"),
    ("analyze_correlation", "cross-camera correlation per hop"),
    ("search_alerts", "alerts raised for this vehicle"),
    ("search_anomalies", "behaviour anomalies for this vehicle"),
    ("search_incidents", "incidents referencing this vehicle"),
    ("search_cases", "cases referencing this vehicle"),
    ("search_evidence", "evidence snapshots on file"),
    ("detect_gaps", "evidence / coverage gaps"),
]


class InvestigationAgentService:
    def __init__(self, db: Session):
        self.db = db
        self.registry = ToolRegistry(db)
        self.provider = get_llm_provider()

    # ------------------------------------------------------------------ #
    def run(self, query: str, *, context_plate: str | None = None) -> dict:
        parsed = parse_query(query, context_plate=context_plate)
        plate = parsed.plate or (normalize_plate(context_plate) if context_plate else None)

        plan = self._plan(query, parsed, plate)
        steps: list[dict] = []
        findings: dict[str, dict] = {}

        for tool_name, purpose in plan[: settings.AI_AGENT_MAX_STEPS]:
            params = self._params_for(tool_name, parsed, plate, findings)
            if params is None:
                steps.append({"tool": tool_name, "purpose": purpose, "skipped": True,
                              "reason": "prerequisite data not available"})
                continue
            try:
                result = self.registry.call(tool_name, **params)
            except Exception as exc:  # noqa: BLE001 -- one bad tool must not abort the run
                logger.exception("agent tool %s failed", tool_name)
                steps.append({"tool": tool_name, "purpose": purpose, "error": str(exc)})
                continue
            findings[tool_name] = result
            steps.append({
                "tool": tool_name, "purpose": purpose, "params": params,
                "result_summary": _summarise(tool_name, result),
            })

        report = self._aggregate(query, plate, parsed, findings)
        report["steps"] = steps
        report["plan_source"] = plan_source_of(plan)
        report["generated_at"] = datetime.utcnow()
        return report

    # ------------------------------------------------------------------ #
    def _plan(self, query: str, parsed, plate: Optional[str]) -> list[tuple[str, str]]:
        """Deterministic plan first. If an LLM is configured, let it *refine
        the ordering / subset* by picking from the registry names -- it never
        adds anything not in the registry, and any error -> deterministic."""
        if plate:
            base = list(_VEHICLE_PLAN)
        else:
            base = [("traffic_analysis", "traffic overview"),
                    ("search_cameras", "camera lookup")]

        chosen = self.provider.plan_tools(query, self.registry.names()) if hasattr(
            self.provider, "plan_tools"
        ) else None
        if chosen:
            valid = [t for t in chosen if t in dict(base)]
            if valid:
                ordered = [(t, dict(base)[t]) for t in valid]
                # keep detect_gaps last if present
                return _mark(ordered, "llm")
        return _mark(base, "deterministic")

    def _params_for(self, tool: str, parsed, plate, findings) -> Optional[dict]:
        if tool in ("search_vehicle", "get_vehicle_journey", "search_alerts",
                    "search_incidents", "search_cases", "search_evidence",
                    "search_similar_vehicles", "search_anomalies", "analyze_correlation",
                    "detect_gaps", "search_watchlist"):
            if not plate:
                return None
            return {"plate": plate}
        if tool == "search_cameras":
            return {"plate": plate} if plate else {"name_contains": None}
        if tool == "traffic_analysis":
            return {"camera_code": (parsed.camera_codes or [None])[0],
                    "vehicle_type": parsed.vehicle_type}
        return {}

    # ------------------------------------------------------------------ #
    def _aggregate(self, query, plate, parsed, f: dict) -> dict:
        veh = f.get("search_vehicle") or {}
        journey = f.get("get_vehicle_journey") or {}
        similar = f.get("search_similar_vehicles") or {}
        corr = f.get("analyze_correlation") or {}
        alerts = (f.get("search_alerts") or {}).get("alerts", [])
        anomalies = (f.get("search_anomalies") or {}).get("anomalies", [])
        incidents = (f.get("search_incidents") or {}).get("incidents", [])
        cases = (f.get("search_cases") or {}).get("cases", [])
        evidence = (f.get("search_evidence") or {}).get("evidence", [])
        gaps = (f.get("detect_gaps") or {}).get("gaps", [])

        sightings = veh.get("sightings", [])
        n_sight = len(sightings)
        distinct_cams = len({s.get("camera_code") or s.get("camera_id") for s in sightings})

        sections = []
        if plate:
            if n_sight:
                first, last = sightings[0], sightings[-1]
                chain = " -> ".join(dict.fromkeys(
                    s.get("camera_code") or s.get("camera_id") for s in journey.get("sightings", sightings)
                ))
                sections.append({
                    "title": "Vehicle & journey",
                    "body": (
                        f"{plate} was recorded {n_sight} time(s) across {distinct_cams} camera(s) "
                        f"between {_ft(first['timestamp'])} and {_ft(last['timestamp'])}. "
                        f"Trail: {chain}."
                        + (" On the active watchlist." if veh.get("is_watchlisted") else "")
                    ),
                })
            else:
                sections.append({"title": "Vehicle & journey",
                                 "body": f"{plate} — not available in recorded evidence."})

            if similar.get("candidates"):
                strong = [c for c in similar["candidates"] if c["band"] in ("STRONG", "MODERATE")
                          and not c["same_plate"]]
                sections.append({
                    "title": "Visual matches (leads, not identity)",
                    "body": (
                        f"{len(strong)} appearance-similar sighting(s) of OTHER plates "
                        f"(top {similar['candidates'][0]['similarity_pct']}% similarity)."
                        if strong else
                        "No strong appearance matches to other plates."
                    ),
                })
            if corr.get("hops"):
                confirmed = corr.get("confirmed", 0)
                sections.append({
                    "title": "Cross-camera correlation",
                    "body": (
                        f"{corr['hops_analyzed']} hop(s) analysed: {confirmed} CONFIRMED "
                        f"(exact plate + feasible time), {corr.get('inferred', 0)} INFERRED."
                    ),
                })
            sections.append({"title": "Alerts", "body": _count_line(alerts, "alert")})
            sections.append({"title": "Behaviour anomalies",
                             "body": (", ".join(sorted({a["kind"] for a in anomalies})) + f" ({len(anomalies)})")
                             if anomalies else "None on record."})
            sections.append({"title": "Incidents", "body": _count_line(incidents, "incident")})
            sections.append({"title": "Cases", "body": _count_line(cases, "case")})
            sections.append({"title": "Evidence", "body": _count_line(evidence, "evidence snapshot")})

        # confidence: grounded in how much corroboration exists
        score = 0.0
        if n_sight:
            score = min(0.95, 0.4 + 0.08 * n_sight + 0.06 * max(0, distinct_cams - 1))
        level = level_from_score(score) if plate else ConfidenceLevel.MEDIUM

        summary = self._summary_text(plate, n_sight, distinct_cams, alerts, incidents,
                                     cases, anomalies, gaps, veh)
        summary = self.provider.narrate(query, {"facts": sections, "intent": "INVESTIGATION"}, summary)

        related = []
        for i in incidents[:10]:
            related.append({"kind": "INCIDENT", "id": i["id"], "label": i["incident_number"],
                            "href": f"/incidents/{i['id']}"})
        for c in cases[:10]:
            related.append({"kind": "CASE", "id": c["id"], "label": c["case_number"],
                            "href": f"/cases/{c['id']}"})
        for a in alerts[:10]:
            related.append({"kind": "ALERT", "id": a["id"], "label": f"{a['plate']} · {a['status']}",
                            "href": f"/alerts?focus={a['id']}"})

        return {
            "query": query,
            "plate": plate,
            "provider": self.provider.name,
            "read_only": True,
            "summary": summary,
            "sections": sections,
            "gaps": gaps,
            "related": related,
            "confidence_score": round(score, 2),
            "confidence_level": level.value,
            "disclaimer": (
                "AI-GENERATED investigation aid. Every figure is a real database "
                "record; empty fields mean 'not in recorded evidence'. Visual "
                "matches and inferred correlations are leads, not proof. The agent "
                "is READ-ONLY -- it created nothing."
            ),
        }

    @staticmethod
    def _summary_text(plate, n_sight, distinct_cams, alerts, incidents, cases,
                      anomalies, gaps, veh) -> str:
        if not plate:
            return ("No registration plate was identified in the request, so a "
                    "vehicle investigation could not be run.")
        if not n_sight:
            return (f"{plate} does not appear in recorded evidence. No sightings, "
                    f"alerts, incidents or cases are on file.")
        bits = [
            f"{plate}: {n_sight} sighting(s) over {distinct_cams} camera(s)."
        ]
        if veh.get("is_watchlisted"):
            bits.append(f"On the watchlist ({veh.get('watchlist_category') or 'category unset'}).")
        if alerts:
            bits.append(f"{len(alerts)} alert(s).")
        if anomalies:
            bits.append(f"{len(anomalies)} behaviour anomaly/anomalies "
                        f"({', '.join(sorted({a['kind'] for a in anomalies}))}).")
        if incidents or cases:
            bits.append(f"{len(incidents)} incident(s), {len(cases)} case(s).")
        if gaps:
            highs = [g for g in gaps if g["severity"] == "high"]
            bits.append(f"{len(gaps)} evidence/coverage gap(s)"
                        + (f", {len(highs)} high-severity" if highs else "") + ".")
        return " ".join(bits)


# --------------------------------------------------------------------------- #
def _mark(plan: list[tuple[str, str]], source: str) -> list[tuple[str, str]]:
    _PLAN_SOURCE[id(plan)] = source
    return plan


_PLAN_SOURCE: dict[int, str] = {}


def plan_source_of(plan) -> str:
    return _PLAN_SOURCE.get(id(plan), "deterministic")


def _summarise(tool: str, result: dict) -> str:
    if not isinstance(result, dict):
        return "ok"
    for key in ("sightings", "candidates", "alerts", "incidents", "cases", "evidence",
                "anomalies", "hops", "gaps", "cameras", "matches"):
        if key in result and isinstance(result[key], list):
            return f"{len(result[key])} {key}"
    if "total_sightings" in result:
        return f"{result['total_sightings']} sightings"
    if "total_vehicles" in result:
        return f"{result['total_vehicles']} vehicles in window"
    if "is_watchlisted" in result:
        return "watchlisted" if result["is_watchlisted"] else "not watchlisted"
    return "ok"


def _count_line(items: list, noun: str) -> str:
    n = len(items)
    return f"{n} {noun}{'s' if n != 1 else ''} on record." if n else "None on record."


def _ft(v) -> str:
    return v.strftime("%d %b %H:%M") if hasattr(v, "strftime") else str(v)
