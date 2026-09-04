"""
ai/tracking/correlation.py

Cross-camera trajectory builder.

Consumes the consolidated per-track AI events (one per completed vehicle track,
from every camera) and correlates sightings of the *same registration plate*
across different camera locations, ordered chronologically (timestamp ASC).

Primary cross-camera identity (DEVELOPER_README section 6):
    plate_number + timestamp + camera_id + location

Downstream consumers:
  * Vanshal's backend  -> feeds ``GET /api/v1/vehicles/search`` ordering logic
    (``to_vehicle_history`` matches ``backend/app/schemas/vehicle.py``:
    ``VehicleHistoryResponse`` -- the real "contract #4 - Vehicle History").
  * Vishakha's investigation UI -> ``build_trajectory`` output drives the
    Leaflet polyline route map.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger("CrossCameraCorrelation")

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def normalize_plate(raw: Optional[str]) -> str:
    """Uppercase + strip non-alphanumerics -- identical rule to
    ``backend/app/services/plate_utils.normalize_plate`` (kept local so ``ai/``
    has no dependency on ``backend/``)."""
    return re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()


def parse_timestamp(value: Any) -> datetime:
    """Best-effort parse to a timezone-aware UTC ``datetime``.

    Accepts ``datetime``, ISO-8601 strings (``...Z`` tolerated), and UNIX epoch
    seconds or milliseconds (int/float or numeric string). Unparseable input
    logs a warning and sorts to the UNIX epoch rather than crashing the pipeline.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    if isinstance(value, (int, float)):
        secs = float(value)
        if secs > 1e11:                       # milliseconds
            secs /= 1000.0
        return datetime.fromtimestamp(secs, tz=timezone.utc)

    if value is not None:
        s = str(value).strip()
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            pass
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        try:
            secs = float(s)
            return datetime.fromtimestamp(secs / 1000.0 if secs > 1e11 else secs, tz=timezone.utc)
        except ValueError:
            pass

    logger.warning("Unparseable timestamp %r -- sorting to epoch.", value)
    return _EPOCH


class CrossCameraCorrelator:
    """Accumulates vehicle sightings and assembles chronological trajectories."""

    def __init__(self, dedup_seconds: float = 1.0) -> None:
        self.dedup_seconds = dedup_seconds
        self._by_plate: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._seen_event_ids: set = set()
        self._seen_composite: set = set()

    # -- ingestion ---------------------------------------------------- #
    def add_event(self, event: Dict[str, Any]) -> bool:
        """Register one sighting. Returns ``True`` if stored, ``False`` if it was
        a duplicate under the composite identity rule."""
        plate_raw = (
            event.get("plate_number")
            or event.get("license_plate", {}).get("plate_number")
            or event.get("plate")
        )
        plate = normalize_plate(plate_raw)
        if not plate or plate.startswith("UNPLATEDTRACK") or plate == "UNKNOWN":
            return False

        camera_id = str(event.get("camera_id", "") or "")
        location = event.get("location") or event.get("camera_name")
        ts = parse_timestamp(event.get("timestamp") or event.get("ts"))
        event_id = event.get("event_id")

        if event_id is not None:
            if event_id in self._seen_event_ids:
                return False
            self._seen_event_ids.add(event_id)

        # composite identity: plate + timestamp(sec bucket) + camera + location
        bucket = int(ts.timestamp() // max(self.dedup_seconds, 1e-9))
        composite = (plate, bucket, camera_id, str(location or ""))
        if composite in self._seen_composite:
            return False
        self._seen_composite.add(composite)

        lp = event.get("license_plate", {})
        vehicle = event.get("vehicle", {})
        self._by_plate[plate].append(
            {
                "event_id": event_id,
                "plate_number": plate,
                "camera_id": camera_id,
                "camera_name": event.get("camera_name") or location,
                "location": location,
                "timestamp": ts,
                "latitude": event.get("latitude"),
                "longitude": event.get("longitude"),
                "confidence": event.get("confidence")
                if event.get("confidence") is not None
                else lp.get("confidence"),
                "vehicle_type": event.get("vehicle_type") or vehicle.get("type"),
                "snapshot_url": event.get("snapshot_url")
                or event.get("evidence", {}).get("frame_snapshot_path"),
            }
        )
        return True

    def add_events(self, events: Iterable[Dict[str, Any]]) -> int:
        return sum(1 for e in events if self.add_event(e))

    # -- queries ---------------------------------------------------- #
    def build_trajectory(self, plate: str) -> List[Dict[str, Any]]:
        """Chronological (timestamp ASC) sighting list for one plate.

        Each hop is annotated with ``previous_camera_id`` and
        ``seconds_since_previous`` for route drawing / speed estimation.
        """
        plate_n = normalize_plate(plate)
        rows = sorted(
            self._by_plate.get(plate_n, []),
            key=lambda r: (r["timestamp"], r["camera_id"]),
        )
        out: List[Dict[str, Any]] = []
        prev: Optional[Dict[str, Any]] = None
        for r in rows:
            hop = {
                "event_id": r["event_id"],
                "plate_number": r["plate_number"],
                "camera_id": r["camera_id"],
                "camera_name": r["camera_name"],
                "location": r["location"],
                "timestamp": r["timestamp"].isoformat(),
                "epoch": r["timestamp"].timestamp(),
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "confidence": r["confidence"],
                "vehicle_type": r["vehicle_type"],
                "previous_camera_id": prev["camera_id"] if prev else None,
                "seconds_since_previous": (
                    round(r["timestamp"].timestamp() - prev["timestamp"].timestamp(), 3)
                    if prev
                    else None
                ),
            }
            out.append(hop)
            prev = r
        return out

    def all_plates(self) -> List[str]:
        return sorted(self._by_plate.keys())

    def get_all_trajectories(self) -> Dict[str, List[Dict[str, Any]]]:
        return {plate: self.build_trajectory(plate) for plate in self.all_plates()}

    def to_vehicle_history(self, plate: str, is_watchlisted: bool = False) -> Dict[str, Any]:
        """Shape-match ``backend/app/schemas/vehicle.VehicleHistoryResponse``."""
        plate_n = normalize_plate(plate)
        rows = sorted(
            self._by_plate.get(plate_n, []),
            key=lambda r: (r["timestamp"], r["camera_id"]),
        )
        sightings = [
            {
                "event_id": r["event_id"],
                "camera_id": r["camera_id"],
                "camera_name": r["camera_name"],
                "timestamp": r["timestamp"].isoformat(),
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "snapshot_url": r["snapshot_url"],
                "confidence_score": r["confidence"],
            }
            for r in rows
        ]
        return {
            "plate_number": plate_n,
            "total_sightings": len(sightings),
            "is_watchlisted": is_watchlisted,
            "sightings": sightings,
        }

    def clear(self) -> None:
        self._by_plate.clear()
        self._seen_event_ids.clear()
        self._seen_composite.clear()
