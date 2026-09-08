"""
Camera Transition Intelligence (Phase 14 §3).

Statistical historical baselines -- NOT ML prediction -- over the existing
`vehicle_events`. For every ordered camera pair (A -> B) seen as a
consecutive same-plate hop, we store how long that hop usually takes.

    CameraTransitionService(db).recompute()              # idempotent upsert
    .expected_travel(from_id, to_id)                     # {typical band, source}
    .classify(from_id, to_id, observed_seconds)          # PLAUSIBLE/FAST/SLOW/IMPOSSIBLE/UNKNOWN
    .likely_next_cameras(camera_id)  / .likely_previous_cameras(camera_id)

`expected_travel` falls back to a distance / assumed-urban-speed model when
there is no history, and to "unknown" when even the geometry is missing.
Every returned figure is labelled with its `source`.
"""
from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import select
from sqlmodel import Session

from app.config import settings
from app.models.camera import Camera
from app.models.camera_transition_stat import CameraTransitionStat
from app.models.vehicle_event import VehicleEvent
from app.services.geo import haversine_m

logger = logging.getLogger("sentinel.ai.transitions")

_UNKNOWN = "UNKNOWN"


class CameraTransitionService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ #
    #  recompute
    # ------------------------------------------------------------------ #
    def recompute(self, *, lookback_days: Optional[int] = None) -> dict:
        """Rebuild camera_transition_stats from consecutive same-plate hops.
        Bounded by CAMERA_TRANSITION_MAX_EVENTS. Idempotent upsert."""
        days = lookback_days or settings.CAMERA_TRANSITION_LOOKBACK_DAYS
        since = datetime.utcnow() - timedelta(days=days)
        cap = settings.CAMERA_TRANSITION_MAX_EVENTS

        rows = self.db.execute(
            select(
                VehicleEvent.plate_number_normalized,
                VehicleEvent.camera_id,
                VehicleEvent.timestamp,
            )
            .where(
                VehicleEvent.timestamp >= since,
                VehicleEvent.plate_number_normalized != _UNKNOWN,
            )
            .order_by(VehicleEvent.plate_number_normalized, VehicleEvent.timestamp)
            .limit(cap)
        ).all()

        # group by plate, walk consecutive sightings
        by_plate: dict[str, list[tuple[str, datetime]]] = defaultdict(list)
        for plate, cam_id, ts in rows:
            by_plate[plate].append((cam_id, ts))

        hops: dict[tuple[str, str], list[int]] = defaultdict(list)
        for seq in by_plate.values():
            for (a_cam, a_ts), (b_cam, b_ts) in zip(seq, seq[1:]):
                if a_cam == b_cam:
                    continue
                dt = int((b_ts - a_ts).total_seconds())
                if dt <= 0 or dt > settings.CAMERA_TRANSITION_MAX_HOP_SECONDS:
                    continue
                hops[(a_cam, b_cam)].append(dt)

        # camera geo + code lookup (bounded -- dozens of cameras)
        cam_rows = self.db.execute(
            select(Camera.id, Camera.code, ST_Y(Camera.location), ST_X(Camera.location))
        ).all()
        cam_code = {cid: code for cid, code, _, _ in cam_rows}
        cam_xy = {cid: (lat, lon) for cid, _, lat, lon in cam_rows}

        now = datetime.utcnow()
        upserted = 0
        seen_pairs: set[tuple[str, str]] = set()
        for (a_cam, b_cam), samples in hops.items():
            if len(samples) < settings.CAMERA_TRANSITION_MIN_SAMPLES:
                continue
            samples.sort()
            seen_pairs.add((a_cam, b_cam))
            dist = None
            la = cam_xy.get(a_cam)
            lb = cam_xy.get(b_cam)
            if la and lb and None not in la and None not in lb:
                dist = round(haversine_m(la[0], la[1], lb[0], lb[1]), 1)

            existing = self.db.execute(
                select(CameraTransitionStat).where(
                    CameraTransitionStat.from_camera_id == a_cam,
                    CameraTransitionStat.to_camera_id == b_cam,
                )
            ).scalar_one_or_none()
            payload = dict(
                from_camera_code=cam_code.get(a_cam),
                to_camera_code=cam_code.get(b_cam),
                sample_count=len(samples),
                min_seconds=samples[0],
                median_seconds=int(statistics.median(samples)),
                p90_seconds=samples[min(len(samples) - 1, int(0.9 * len(samples)))],
                max_seconds=samples[-1],
                mean_seconds=int(statistics.fmean(samples)),
                distance_meters=dist,
                last_computed_at=now,
            )
            if existing:
                for k, v in payload.items():
                    setattr(existing, k, v)
            else:
                self.db.add(CameraTransitionStat(
                    from_camera_id=a_cam, to_camera_id=b_cam, **payload
                ))
            upserted += 1

        self.db.commit()
        return {"pairs_upserted": upserted, "events_scanned": len(rows)}

    # ------------------------------------------------------------------ #
    #  lookups
    # ------------------------------------------------------------------ #
    def _stat(self, from_id: str, to_id: str) -> Optional[CameraTransitionStat]:
        return self.db.execute(
            select(CameraTransitionStat).where(
                CameraTransitionStat.from_camera_id == from_id,
                CameraTransitionStat.to_camera_id == to_id,
            )
        ).scalar_one_or_none()

    def _camera_xy(self, cam_id: str):
        row = self.db.execute(
            select(ST_Y(Camera.location), ST_X(Camera.location)).where(Camera.id == cam_id)
        ).first()
        if not row or row[0] is None or row[1] is None:
            return None
        return (row[0], row[1])

    def expected_travel(self, from_id: str, to_id: str) -> dict:
        """Typical travel-time band for a hop. `source` is always stated:
        'historical' | 'distance-model' | 'unknown'."""
        stat = self._stat(from_id, to_id)
        if stat and stat.sample_count >= settings.CAMERA_TRANSITION_MIN_SAMPLES:
            return {
                "source": "historical",
                "sample_count": stat.sample_count,
                "typical_min_seconds": stat.min_seconds,
                "typical_max_seconds": stat.p90_seconds,
                "median_seconds": stat.median_seconds,
                "hard_max_seconds": stat.max_seconds,
                "distance_meters": stat.distance_meters,
            }

        a = self._camera_xy(from_id)
        b = self._camera_xy(to_id)
        if a and b:
            dist = haversine_m(a[0], a[1], b[0], b[1])
            fast = dist / (settings.CAMERA_TRANSITION_MODEL_MAX_KMH / 3.6)
            slow = dist / (settings.CAMERA_TRANSITION_MODEL_MIN_KMH / 3.6)
            return {
                "source": "distance-model",
                "sample_count": 0,
                "typical_min_seconds": int(fast),
                "typical_max_seconds": int(slow),
                "median_seconds": int((fast + slow) / 2),
                "hard_max_seconds": int(slow * settings.CAMERA_TRANSITION_IMPOSSIBLE_FACTOR),
                "distance_meters": round(dist, 1),
            }
        return {
            "source": "unknown", "sample_count": 0,
            "typical_min_seconds": None, "typical_max_seconds": None,
            "median_seconds": None, "hard_max_seconds": None, "distance_meters": None,
        }

    def classify(self, from_id: str, to_id: str, observed_seconds: int) -> dict:
        """PLAUSIBLE / FAST / SLOW / IMPOSSIBLE / UNKNOWN + the band used."""
        band = self.expected_travel(from_id, to_id)
        lo, hi, hard = band["typical_min_seconds"], band["typical_max_seconds"], band["hard_max_seconds"]
        if lo is None:
            verdict = "UNKNOWN"
        elif observed_seconds < lo * settings.CAMERA_TRANSITION_FAST_FACTOR:
            verdict = "IMPOSSIBLE" if observed_seconds < lo * 0.5 else "FAST"
        elif observed_seconds <= hi:
            verdict = "PLAUSIBLE"
        elif hard is not None and observed_seconds > hard:
            verdict = "SLOW"
        else:
            verdict = "SLOW"
        return {
            "classification": verdict,
            "observed_seconds": observed_seconds,
            "expected": band,
        }

    def _related(self, camera_id: str, *, direction: str) -> list[dict]:
        col = (
            CameraTransitionStat.from_camera_id
            if direction == "next"
            else CameraTransitionStat.to_camera_id
        )
        other_id = (
            CameraTransitionStat.to_camera_id
            if direction == "next"
            else CameraTransitionStat.from_camera_id
        )
        other_code = (
            CameraTransitionStat.to_camera_code
            if direction == "next"
            else CameraTransitionStat.from_camera_code
        )
        rows = self.db.execute(
            select(other_id, other_code, CameraTransitionStat.sample_count,
                   CameraTransitionStat.median_seconds)
            .where(col == camera_id)
            .order_by(CameraTransitionStat.sample_count.desc())
            .limit(settings.CAMERA_TRANSITION_TOPN)
        ).all()
        total = sum(r[2] for r in rows) or 1
        return [
            {
                "camera_id": cid, "camera_code": code,
                "observed_hops": cnt,
                "share": round(cnt / total, 3),
                "median_seconds": med,
            }
            for cid, code, cnt, med in rows
        ]

    def likely_next_cameras(self, camera_id: str) -> list[dict]:
        return self._related(camera_id, direction="next")

    def likely_previous_cameras(self, camera_id: str) -> list[dict]:
        return self._related(camera_id, direction="prev")
