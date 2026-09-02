"""
Camera catalogue parser & validator.

Fetches the government camera inventory payload and turns it into a list
of validated CameraRecord objects. Bad entries are logged and skipped
rather than raising -- one malformed camera record must never take down
the whole ingest run.

Two real sources have been confirmed so far, with genuinely different
shapes:

1. docs/API_CONTRACTS.md#1-camera-registry-api (GET /api/v1/cameras):

    {
      "status": "success",
      "data": [
        {
          "camera_id": "CAM_AHM_001",
          "name": "Ashram Road Junction North",
          "department": "Traffic Police",
          "location": {"latitude": 23.0225, "longitude": 72.5714},
          "stream_url": "rtsp://10.0.1.100:554/live/ch1",
          "stream_protocol": "RTSP/TCP",
          "status": "ONLINE"
        }
      ]
    }

2. https://cctv.corp8.cloud/cameras.json (confirmed live, 2026-09-02,
   behind auth -- requires a logged-in session):

    [
      {"id": "cam01", "name": "01 Chiman bhai Bridge"},
      {"id": "cam02", "name": "02 Janpath"}
    ]

   A bare list. No stream_url, department, location, or status at all.

This module accepts both: `id` or `camera_id` as the identifier,
`stream_url` treated as OPTIONAL (None when absent, e.g. for every
camera from source #2 today). No synthetic data: nothing here fabricates
a camera_id, name, or stream_url when a source doesn't provide one --
missing/invalid records are skipped and logged, and a present-but-absent
stream_url is stored as None, not guessed or derived from a pattern.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Set

import requests

from .models import CameraLocation, CameraRecord

logger = logging.getLogger("sentinel.ingestion.catalogue")


class CatalogueError(Exception):
    """Raised when the catalogue endpoint itself is unreachable / malformed."""


def _extract_records(payload: Any) -> List[Dict[str, Any]]:
    """Pull the list of camera dicts out of whatever envelope shape we got.

    Confirmed shape: {"status": "success", "data": [...]}.
    Also accepted, defensively, in case /api/ingest differs from the
    Camera Registry API: a bare list, or {"cameras": [...]}.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            return payload["data"]
        if isinstance(payload.get("cameras"), list):
            return payload["cameras"]

    raise CatalogueError(f"Unexpected catalogue payload shape: {type(payload).__name__}")


def fetch_catalogue(url: str, timeout_s: float = 10.0) -> List[Dict[str, Any]]:
    """GET the raw catalogue payload from the registry and return the list
    of camera dicts, exactly as the registry reported them.

    Raises CatalogueError on network failure, a non-2xx/non-JSON response,
    or an unexpected top-level shape. Never fabricates records.
    """
    try:
        resp = requests.get(url, timeout=timeout_s)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise CatalogueError(f"Failed to fetch catalogue from {url}: {exc}") from exc

    return _extract_records(payload)


def _parse_location(raw_location: Any) -> Optional[CameraLocation]:
    if not isinstance(raw_location, dict):
        return None
    try:
        return CameraLocation(
            latitude=float(raw_location["latitude"]),
            longitude=float(raw_location["longitude"]),
        )
    except (KeyError, TypeError, ValueError):
        logger.debug("Could not parse location object: %s", raw_location)
        return None


def _validate_record(raw: Dict[str, Any]) -> Optional[CameraRecord]:
    # Source #1 calls the identifier "camera_id"; source #2 calls it "id".
    # Whichever is present wins; camera_id is preferred if a record somehow
    # has both.
    raw_id = raw.get("camera_id") or raw.get("id")
    if not raw_id:
        logger.warning("Skipping camera record with no camera_id/id: %s", raw)
        return None
    camera_id = str(raw_id)

    # stream_url is OPTIONAL: source #2 never provides one. If present, it
    # must actually look like an RTSP URL or we drop just that field (log
    # it) rather than reject the whole camera -- an unusable stream_url is
    # still useful information, but we don't want stream_manager treating
    # a non-RTSP string as connectable.
    stream_url: Optional[str] = None
    raw_stream_url = raw.get("stream_url")
    if raw_stream_url:
        candidate = str(raw_stream_url)
        if candidate.lower().startswith("rtsp://"):
            stream_url = candidate
        else:
            logger.warning(
                "Camera %s: stream_url present but not an RTSP URL, dropping it: %s",
                camera_id, raw_stream_url,
            )

    return CameraRecord(
        camera_id=camera_id,
        name=raw.get("name"),
        stream_url=stream_url,
        stream_protocol=raw.get("stream_protocol"),
        department=raw.get("department"),
        location=_parse_location(raw.get("location")),
        codec_hint=raw.get("codec"),
        registry_status=raw.get("status"),
        # Not in either confirmed source yet -- kept defensive in case a
        # future version of a source adds one of these key names.
        webrtc_url=raw.get("webrtc_url") or raw.get("whep_url"),
        hls_url=raw.get("hls_url"),
        raw=raw,
    )


def parse_catalogue(raw_records: Iterable[Dict[str, Any]]) -> List[CameraRecord]:
    """Validate a list of raw catalogue dicts into CameraRecord objects.

    Duplicate camera_ids are de-duplicated, keeping the first occurrence
    and logging a warning -- the registry (Model 1 / GIS foundation) is
    the real source of truth for uniqueness, but we defend against a
    stale or duplicated feed here too.
    """
    seen: Set[str] = set()
    records: List[CameraRecord] = []

    for raw in raw_records:
        record = _validate_record(raw)
        if record is None:
            continue
        if record.camera_id in seen:
            logger.warning(
                "Duplicate camera_id %s in catalogue, ignoring repeat", record.camera_id
            )
            continue
        seen.add(record.camera_id)
        records.append(record)

    logger.info("Parsed %d valid camera record(s) from catalogue", len(records))
    return records


def load_catalogue(url: str, timeout_s: float = 10.0) -> List[CameraRecord]:
    """Convenience wrapper: fetch + parse in one call."""
    raw_records = fetch_catalogue(url, timeout_s=timeout_s)
    return parse_catalogue(raw_records)
