"""
Investigation Copilot service (phase brief §1).

    natural-language question
        -> deterministic parse (intent + entities)
        -> pick a validated tool
        -> run it against the EXISTING indexed DB paths
        -> aggregate (results + timeline + map + related records)
        -> confidence + limitations
        -> grounded answer (optionally re-worded by an LLM)

Never invents a result. Every number in the answer comes from a tool call.
"""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from app.models.base import ConfidenceLevel
from app.schemas.ai import (
    CopilotResponse,
    MapPoint,
    ParsedQuery,
    RelatedRef,
    TimelineItem,
)
from app.services.ai.confidence import level_from_score, vehicle_match_confidence
from app.services.ai.llm import get_llm_provider
from app.services.ai.nlq import parse_query
from app.services.ai.tools import InvestigationTools

_INTENT_TOOL = {
    "VEHICLE_SEARCH": "search_vehicle",
    "VEHICLE_LAST_SEEN": "search_vehicle",
    "VEHICLE_JOURNEY": "get_vehicle_journey",
    "CAMERA_SEARCH": "search_cameras",
    "TIME_RANGE_SEARCH": "search_detections",
    "WATCHLIST_SEARCH": "watchlist_detections",
    "ALERT_SEARCH": "search_alerts",
    "INCIDENT_SEARCH": "search_incidents",
    "CASE_SEARCH": "search_cases",
    "EVIDENCE_SEARCH": "search_evidence",
}


def _fmt_dt(v) -> str:
    if not v:
        return "unknown time"
    if isinstance(v, str):
        return v
    return v.strftime("%d %b %H:%M")


class InvestigationCopilotService:
    def __init__(self, db: Session):
        self.db = db
        self.tools = InvestigationTools(db)
        self.provider = get_llm_provider()

    def investigate(self, query: str, *, context_plate: str | None = None) -> CopilotResponse:
        parsed = parse_query(query, context_plate=context_plate)
        tool_name = _INTENT_TOOL.get(parsed.intent, "search_detections")
        tool_calls: list[dict] = []
        limitations: list[str] = list(parsed.notes)

        results: list[dict] = []
        timeline: list[TimelineItem] = []
        map_points: list[MapPoint] = []
        related: list[RelatedRef] = []
        confidence_score = 0.0
        confidence_level = ConfidenceLevel.INSUFFICIENT
        match_method = None

        # ---------- dispatch ----------
        if tool_name in ("search_vehicle", "get_vehicle_journey", "search_cameras") and not parsed.plate:
            answer = (
                f"To answer a “{parsed.intent.replace('_', ' ').lower()}” question I need a "
                f"registration plate, and none was found in the query."
            )
            limitations.append("no plate in query")
            return self._response(query, parsed, tool_calls, answer, results, timeline,
                                  map_points, related, 0.0, ConfidenceLevel.INSUFFICIENT, None,
                                  limitations)

        if tool_name == "search_vehicle":
            params = {"plate": parsed.plate}
            data = self.tools.search_vehicle(parsed.plate)
            tool_calls.append({"tool": tool_name, "params": params})
            sightings = data["sightings"]
            results = sightings
            timeline, map_points = self._from_sightings(sightings)
            distinct = len({s["camera_code"] or s["camera_id"] for s in sightings})
            confidence_score, confidence_level, match_method = vehicle_match_confidence(
                len(sightings), distinct, exact_plate=True
            )
            if not sightings:
                answer = f"{parsed.plate} — not available in recorded evidence. No sightings on file."
            else:
                first, last = sightings[0], sightings[-1]
                wl = " It is on the active watchlist." if data["is_watchlisted"] else ""
                if parsed.intent == "VEHICLE_LAST_SEEN":
                    answer = (
                        f"{parsed.plate} was last seen at {last['camera_code'] or last['camera_id']}"
                        f" ({last['location_desc'] or 'location on file'}) at {_fmt_dt(last['timestamp'])}."
                        f"{wl}"
                    )
                else:
                    answer = (
                        f"{parsed.plate} was detected {len(sightings)} time(s) across {distinct} camera(s) "
                        f"between {_fmt_dt(first['timestamp'])} and {_fmt_dt(last['timestamp'])}.{wl}"
                    )
            related = self._related_for_plate(parsed.plate)

        elif tool_name == "get_vehicle_journey":
            params = {"plate": parsed.plate, "date_from": parsed.date_from, "date_to": parsed.date_to}
            data = self.tools.get_vehicle_journey(parsed.plate, parsed.date_from, parsed.date_to)
            tool_calls.append({"tool": tool_name, "params": params})
            sightings = data["sightings"]
            results = sightings
            timeline, map_points = self._from_sightings(sightings)
            confidence_score, confidence_level, match_method = vehicle_match_confidence(
                len(sightings), data["distinct_cameras"], exact_plate=True
            )
            if not sightings:
                answer = (
                    f"No journey available for {parsed.plate}"
                    + (f" in {parsed.relative_window}" if parsed.relative_window else "")
                    + " — not available in recorded evidence."
                )
            else:
                chain = " → ".join(
                    dict.fromkeys(s["camera_code"] or s["camera_id"] for s in sightings)
                )
                answer = (
                    f"Journey of {parsed.plate}"
                    + (f" ({parsed.relative_window})" if parsed.relative_window else "")
                    + f": {chain}. {len(sightings)} sighting(s) between "
                    f"{_fmt_dt(data['first_seen'])} and {_fmt_dt(data['last_seen'])}"
                    f" (span {data['span_seconds'] // 60} min)."
                )
                if not data["has_journey"]:
                    limitations.append(
                        "fewer than 2 geolocated cameras — the trail cannot be plotted on the map"
                    )
            related = self._related_for_plate(parsed.plate)

        elif tool_name == "search_cameras":
            params = {"plate": parsed.plate, "date_from": parsed.date_from}
            data = self.tools.search_cameras(plate=parsed.plate, date_from=parsed.date_from)
            tool_calls.append({"tool": tool_name, "params": params})
            cams = data["cameras"]
            results = cams
            for c in cams:
                if c.get("latitude") is not None:
                    map_points.append(MapPoint(
                        latitude=c["latitude"], longitude=c["longitude"],
                        label=f"{c['camera_code']} · {c['detections']} detection(s)",
                        camera_code=c["camera_code"], timestamp=c.get("first_seen"),
                    ))
            confidence_score, confidence_level, match_method = vehicle_match_confidence(
                sum(c["detections"] for c in cams), len(cams), exact_plate=True
            )
            if not cams:
                answer = f"No camera detected {parsed.plate} — not available in recorded evidence."
            else:
                answer = (
                    f"{parsed.plate} was detected by {len(cams)} camera(s): "
                    + ", ".join(f"{c['camera_code']} ({c['detections']})" for c in cams) + "."
                )
            related = self._related_for_plate(parsed.plate)

        elif tool_name == "watchlist_detections":
            params = {"date_from": parsed.date_from}
            data = self.tools.watchlist_detections(date_from=parsed.date_from)
            tool_calls.append({"tool": tool_name, "params": params})
            matches = data["matches"]
            results = matches
            for m in matches:
                related.append(RelatedRef(kind="ALERT", id=m["alert_id"],
                                          label=f"{m['plate']} @ {m['camera_code']}",
                                          href=f"/alerts?focus={m['alert_id']}"))
            confidence_score = 0.95 if matches else 0.0
            confidence_level = level_from_score(confidence_score)
            match_method = "watchlist-engine alerts (confirmed matches)"
            window = parsed.relative_window or "on record"
            answer = (
                f"{len(matches)} watchlist vehicle detection(s) {window}."
                if matches else
                f"No watchlist vehicle detections {window} — not available in recorded evidence."
            )

        elif tool_name in ("search_alerts", "search_incidents", "search_cases", "search_evidence"):
            fn = getattr(self.tools, tool_name)
            params = {"plate": parsed.plate}
            data = fn(plate=parsed.plate)
            tool_calls.append({"tool": tool_name, "params": params})
            key = tool_name.split("_", 1)[1]  # alerts/incidents/cases/evidence
            items = data.get(key, data.get("evidence", []))
            results = items
            confidence_score = 0.95 if items else 0.0
            confidence_level = level_from_score(confidence_score)
            match_method = "direct foreign-key lookup"
            subj = f" for {parsed.plate}" if parsed.plate else ""
            answer = (
                f"{len(items)} {key.rstrip('s')}{'s' if len(items) != 1 else ''}{subj} on record."
                if items else
                f"No {key}{subj} — not available in recorded evidence."
            )
            for it in items[:20]:
                if tool_name == "search_incidents":
                    related.append(RelatedRef(kind="INCIDENT", id=it["id"], label=it["incident_number"],
                                              href=f"/incidents/{it['id']}"))
                elif tool_name == "search_cases":
                    related.append(RelatedRef(kind="CASE", id=it["id"], label=it["case_number"],
                                              href=f"/cases/{it['id']}"))
                elif tool_name == "search_alerts":
                    related.append(RelatedRef(kind="ALERT", id=it["id"],
                                              label=f"{it['plate']} · {it['status']}",
                                              href=f"/alerts?focus={it['id']}"))

        else:  # search_detections / TIME_RANGE_SEARCH
            adv = self._detections_params(parsed)
            data = self.tools.search_detections(**adv)
            tool_calls.append({"tool": "search_detections", "params": adv})
            items = data["items"]
            results = items
            timeline, map_points = self._from_search_rows(items)
            confidence_score = 0.9 if items else 0.0
            confidence_level = level_from_score(confidence_score)
            match_method = "advanced search over vehicle_events (exact filters)"
            desc = self._describe_filters(parsed)
            answer = (
                f"{data['total']} detection(s) match {desc}"
                + (f" (showing {data['returned']})." if data["total"] > data["returned"] else ".")
                if items else
                f"No detections match {desc} — not available in recorded evidence."
            )

        answer = self.provider.narrate(query, {"facts": results[:15], "intent": parsed.intent}, answer)

        return self._response(query, parsed, tool_calls, answer, results, timeline, map_points,
                              related, confidence_score, confidence_level, match_method, limitations)

    # ------------------------------------------------------------------ #
    def _detections_params(self, p: ParsedQuery) -> dict:
        return dict(
            plate=p.plate, camera_codes=p.camera_codes or None, vehicle_type=p.vehicle_type,
            vehicle_color=p.vehicle_color, date_from=p.date_from, date_to=p.date_to,
            time_from=p.time_from, time_to=p.time_to, unknown_only=p.unknown_only,
            min_duration_seconds=p.min_duration_seconds,
        )

    @staticmethod
    def _describe_filters(p: ParsedQuery) -> str:
        bits = []
        if p.vehicle_color:
            bits.append(p.vehicle_color)
        if p.vehicle_type:
            bits.append(p.vehicle_type + "s")
        elif not p.vehicle_color:
            bits.append("vehicles")
        else:
            bits.append("vehicles")
        if p.unknown_only:
            bits.append("with unknown plates")
        if p.camera_codes:
            bits.append("near " + "/".join(p.camera_codes))
        if p.relative_window:
            bits.append(p.relative_window)
        if p.time_from and p.time_to:
            bits.append(f"between {p.time_from} and {p.time_to}")
        elif p.time_from:
            bits.append(f"after {p.time_from}")
        elif p.time_to:
            bits.append(f"before {p.time_to}")
        if p.min_duration_seconds:
            bits.append(f"present for ≥ {p.min_duration_seconds // 60} min")
        return " ".join(bits)

    @staticmethod
    def _from_sightings(sightings: list[dict]):
        tl, mp = [], []
        for s in sightings:
            tl.append(TimelineItem(
                timestamp=s["timestamp"],
                label=f"{s['plate']} at {s['camera_code'] or s['camera_id']}",
                camera_code=s["camera_code"], latitude=s.get("latitude"),
                longitude=s.get("longitude"), ref_kind="vehicle_event", ref_id=s["event_id"],
            ))
            if s.get("has_location"):
                mp.append(MapPoint(
                    latitude=s["latitude"], longitude=s["longitude"],
                    label=f"{s['plate']} · {_fmt_dt(s['timestamp'])}",
                    camera_code=s["camera_code"], timestamp=s["timestamp"],
                ))
        return tl, mp

    @staticmethod
    def _from_search_rows(rows: list[dict]):
        tl, mp = [], []
        for r in rows:
            tl.append(TimelineItem(
                timestamp=r["timestamp"],
                label=f"{r['plate_number_normalized']} at {r.get('camera_code') or r.get('camera_id')}",
                camera_code=r.get("camera_code"), latitude=r.get("latitude"),
                longitude=r.get("longitude"), ref_kind="vehicle_event", ref_id=r["event_id"],
            ))
            if r.get("latitude") is not None and r.get("longitude") is not None:
                mp.append(MapPoint(latitude=r["latitude"], longitude=r["longitude"],
                                   label=f"{r['plate_number_normalized']} · {_fmt_dt(r['timestamp'])}",
                                   camera_code=r.get("camera_code"), timestamp=r["timestamp"]))
        return tl, mp

    def _related_for_plate(self, plate: str) -> list[RelatedRef]:
        out: list[RelatedRef] = []
        for a in self.tools.search_alerts(plate=plate)["alerts"][:10]:
            out.append(RelatedRef(kind="ALERT", id=a["id"], label=f"{a['plate']} · {a['status']}",
                                  href=f"/alerts?focus={a['id']}"))
        for i in self.tools.search_incidents(plate=plate)["incidents"][:10]:
            out.append(RelatedRef(kind="INCIDENT", id=i["id"], label=i["incident_number"],
                                  href=f"/incidents/{i['id']}"))
        for c in self.tools.search_cases(plate=plate)["cases"][:10]:
            out.append(RelatedRef(kind="CASE", id=c["id"], label=c["case_number"],
                                  href=f"/cases/{c['id']}"))
        return out

    def _response(self, query, parsed, tool_calls, answer, results, timeline, map_points,
                  related, score, level, method, limitations) -> CopilotResponse:
        if not results and "not available in recorded evidence" not in answer.lower():
            limitations.append("no matching records — the answer reflects an empty result set")
        return CopilotResponse(
            query=query, provider=self.provider.name, intent=parsed.intent, parsed=parsed,
            tool_calls=tool_calls, answer=answer, result_count=len(results),
            results=results[:50], timeline=sorted(timeline, key=lambda t: t.timestamp),
            map_points=map_points, related=related,
            confidence_score=round(score, 2), confidence_level=level, match_method=method,
            limitations=list(dict.fromkeys(limitations)),
            generated_at=datetime.utcnow(),
        )
