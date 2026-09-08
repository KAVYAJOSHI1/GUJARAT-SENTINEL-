"""
Investigation Graph (Phase 14 §12 -- the previously deferred graph).

Built ENTIRELY from persisted relational rows -- no Neo4j, no inference.
Deterministic: the same DB state always yields the same nodes + edges.

    Vehicle ─► Detection ─► Camera ─► Location
                  │            │
                  │            └─► CameraTransition ─► Camera
                  ▼
                Alert ─► Incident ─► Evidence
                  │          │
                  │          └─► Case
                  ▼
             AnomalyEvent
    Vehicle ─► VisualMatch (Re-ID)      Vehicle ─► Watchlist

Every node carries an `href` to the existing Sentinel entity page so the
frontend can open it. Bounded by GRAPH_MAX_NODES / GRAPH_MAX_EDGES.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import or_, select
from sqlmodel import Session

from app.config import settings
from app.models.alert import Alert
from app.models.anomaly_event import AnomalyEvent
from app.models.camera import Camera
from app.models.camera_transition_stat import CameraTransitionStat
from app.models.case import Case, CaseEvidence, CaseIncident
from app.models.incident import Incident, IncidentEvidence
from app.models.vehicle_event import VehicleEvent
from app.models.watchlist import Watchlist
from app.services.ai.reid import VehicleReIDService
from app.services.plate_utils import normalize_plate
from app.services.watchlist_engine import active_watchlist_clause


class InvestigationGraphService:
    def __init__(self, db: Session):
        self.db = db
        self._nodes: dict[str, dict] = {}
        self._edges: list[dict] = []

    # ------------------------------------------------------------------ #
    def _node(self, nid: str, ntype: str, label: str, href: str | None = None, **meta):
        if nid not in self._nodes and len(self._nodes) < settings.GRAPH_MAX_NODES:
            self._nodes[nid] = {"id": nid, "type": ntype, "label": label,
                                "href": href, "meta": meta}

    def _edge(self, src: str, dst: str, kind: str, label: str | None = None):
        if (src in self._nodes and dst in self._nodes
                and len(self._edges) < settings.GRAPH_MAX_EDGES):
            self._edges.append({"source": src, "target": dst, "kind": kind, "label": label})

    # ------------------------------------------------------------------ #
    def build_for_plate(self, plate: str) -> dict:
        norm = normalize_plate(plate)
        self._nodes, self._edges = {}, []

        v_id = f"vehicle:{norm}"
        self._node(v_id, "vehicle", norm, href=f"/investigation?plate={norm}")

        # --- watchlist ---
        wl = self.db.execute(
            select(Watchlist).where(Watchlist.plate_number_normalized == norm)
            .where(active_watchlist_clause()).limit(1)
        ).scalar_one_or_none()
        if wl:
            w_id = f"watchlist:{wl.id}"
            self._node(w_id, "watchlist", f"{wl.offense_category or 'WATCHLIST'}",
                       href=f"/watchlists?q={norm}", priority=wl.priority_level.value)
            self._edge(v_id, w_id, "on_watchlist")

        # --- detections -> cameras -> locations ---
        rows = self.db.execute(
            select(VehicleEvent, Camera.code, Camera.name, Camera.location_desc)
            .join(Camera, Camera.id == VehicleEvent.camera_id, isouter=True)
            .where(VehicleEvent.plate_number_normalized == norm)
            .order_by(VehicleEvent.timestamp.asc())
            .limit(settings.GRAPH_MAX_DETECTIONS)
        ).all()
        cam_ids_seen: list[str] = []
        for ev, code, name, loc in rows:
            d_id = f"detection:{ev.id}"
            self._node(d_id, "detection", f"{code or ev.camera_code} · {ev.timestamp:%d %b %H:%M}",
                       href=f"/investigation?plate={norm}", timestamp=str(ev.timestamp),
                       confidence=ev.confidence_score, track_id=ev.track_id)
            self._edge(v_id, d_id, "detected_as")

            c_id = f"camera:{ev.camera_id}"
            self._node(c_id, "camera", code or ev.camera_code or "camera",
                       href="/cameras/manage", name=name)
            self._edge(d_id, c_id, "at_camera")
            if ev.camera_id not in cam_ids_seen:
                cam_ids_seen.append(ev.camera_id)

            if ev.latitude is not None and ev.longitude is not None:
                l_id = f"location:{round(ev.latitude, 4)},{round(ev.longitude, 4)}"
                self._node(l_id, "location", loc or f"{ev.latitude:.4f},{ev.longitude:.4f}",
                           href="/map", latitude=ev.latitude, longitude=ev.longitude)
                self._edge(c_id, l_id, "located_at")

        # --- camera transitions between the cameras this vehicle used ---
        if len(cam_ids_seen) >= 2:
            trs = self.db.execute(
                select(CameraTransitionStat).where(
                    CameraTransitionStat.from_camera_id.in_(cam_ids_seen),
                    CameraTransitionStat.to_camera_id.in_(cam_ids_seen),
                )
            ).scalars().all()
            for t in trs:
                self._edge(f"camera:{t.from_camera_id}", f"camera:{t.to_camera_id}",
                           "transition",
                           label=(f"~{t.median_seconds // 60} min ({t.sample_count} obs)"
                                  if t.median_seconds else None))

        # --- visual matches (Re-ID) ---
        if rows:
            sim = VehicleReIDService(self.db).find_similar(
                event_id=rows[-1][0].id, limit=settings.GRAPH_MAX_VISUAL_MATCHES,
                exclude_same_plate=True,
            )
            for cand in sim.get("candidates", []):
                if cand["band"] not in ("STRONG", "MODERATE"):
                    continue
                m_id = f"vehicle:{cand['plate_number_normalized']}"
                self._node(m_id, "vehicle", cand["plate_number_normalized"],
                           href=f"/investigation?plate={cand['plate_number_normalized']}")
                self._edge(v_id, m_id, "visual_match",
                           label=f"{cand['similarity_pct']}% ({cand['band']})")

        # --- alerts -> incidents -> evidence / cases ---
        alerts = self.db.execute(
            select(Alert).where(Alert.plate_number_normalized == norm)
            .order_by(Alert.created_at.desc()).limit(settings.GRAPH_MAX_BRANCH)
        ).scalars().all()
        for a in alerts:
            a_id = f"alert:{a.id}"
            self._node(a_id, "alert", f"{a.source.value} · {a.status.value}",
                       href=f"/alerts?focus={a.id}", priority=a.priority_level.value)
            self._edge(v_id, a_id, "raised_alert")
            if a.vehicle_event_id and f"detection:{a.vehicle_event_id}" in self._nodes:
                self._edge(f"detection:{a.vehicle_event_id}", a_id, "triggered")
            if a.anomaly_event_id:
                an = self.db.get(AnomalyEvent, a.anomaly_event_id)
                if an:
                    an_id = f"anomaly:{an.id}"
                    self._node(an_id, "anomaly", an.kind.value,
                               href="/anomalies", confidence=an.confidence_level.value)
                    self._edge(a_id, an_id, "from_anomaly")

        # anomalies not linked via an alert
        for an in self.db.execute(
            select(AnomalyEvent).where(AnomalyEvent.plate_number_normalized == norm)
            .limit(settings.GRAPH_MAX_BRANCH)
        ).scalars().all():
            an_id = f"anomaly:{an.id}"
            self._node(an_id, "anomaly", an.kind.value, href="/anomalies",
                       confidence=an.confidence_level.value)
            self._edge(v_id, an_id, "flagged_anomaly")

        incidents = self.db.execute(
            select(Incident).where(
                or_(Incident.plate_number_normalized == norm,
                    Incident.alert_id.in_([a.id for a in alerts] or ["-"]))
            ).limit(settings.GRAPH_MAX_BRANCH)
        ).scalars().all()
        inc_ids = []
        for inc in incidents:
            i_id = f"incident:{inc.id}"
            inc_ids.append(inc.id)
            self._node(i_id, "incident", inc.incident_number,
                       href=f"/incidents/{inc.id}", status=inc.status.value)
            if inc.alert_id and f"alert:{inc.alert_id}" in self._nodes:
                self._edge(f"alert:{inc.alert_id}", i_id, "promoted_to")
            else:
                self._edge(v_id, i_id, "subject_of")
            for (ev_id,) in self.db.execute(
                select(IncidentEvidence.vehicle_event_id)
                .where(IncidentEvidence.incident_id == inc.id)
            ).all():
                e_id = f"evidence:{ev_id}"
                self._node(e_id, "evidence", "snapshot",
                           href=f"/investigation?plate={norm}")
                self._edge(i_id, e_id, "has_evidence")
                if f"detection:{ev_id}" in self._nodes:
                    self._edge(f"detection:{ev_id}", e_id, "is_evidence")

        cases = self.db.execute(
            select(Case).where(
                or_(Case.primary_plate_normalized == norm,
                    Case.id.in_(
                        select(CaseIncident.case_id).where(CaseIncident.incident_id.in_(inc_ids or ["-"]))
                    ))
            ).limit(settings.GRAPH_MAX_BRANCH)
        ).scalars().all()
        for case in cases:
            k_id = f"case:{case.id}"
            self._node(k_id, "case", case.case_number, href=f"/cases/{case.id}",
                       status=case.status.value)
            linked = False
            for (i_id_raw,) in self.db.execute(
                select(CaseIncident.incident_id).where(CaseIncident.case_id == case.id)
            ).all():
                if f"incident:{i_id_raw}" in self._nodes:
                    self._edge(f"incident:{i_id_raw}", k_id, "part_of_case")
                    linked = True
            if not linked:
                self._edge(v_id, k_id, "subject_of_case")
            for (ev_id,) in self.db.execute(
                select(CaseEvidence.vehicle_event_id).where(CaseEvidence.case_id == case.id)
            ).all():
                e_id = f"evidence:{ev_id}"
                self._node(e_id, "evidence", "snapshot", href=f"/investigation?plate={norm}")
                self._edge(k_id, e_id, "has_evidence")

        return self._result(root=v_id, subject=norm)

    # ------------------------------------------------------------------ #
    def _result(self, *, root: str, subject: str) -> dict:
        counts: dict[str, int] = {}
        for n in self._nodes.values():
            counts[n["type"]] = counts.get(n["type"], 0) + 1
        return {
            "root": root,
            "subject": subject,
            "nodes": list(self._nodes.values()),
            "edges": self._edges,
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
            "counts_by_type": counts,
            "truncated": (len(self._nodes) >= settings.GRAPH_MAX_NODES
                          or len(self._edges) >= settings.GRAPH_MAX_EDGES),
            "note": (
                "Deterministic graph built only from persisted records. Every "
                "node links to its Sentinel entity page."
            ),
        }
