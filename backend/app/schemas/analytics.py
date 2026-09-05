"""GET /api/v1/analytics/overview response schema.

Every number is a live aggregate over the real `vehicle_events` / `alerts`
tables. Nothing here is mocked or estimated -- an empty database returns
zeros / empty lists, never placeholder data.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class LabelCount(BaseModel):
    label: str
    count: int
    # optional human-friendly secondary label (e.g. camera name for a code)
    detail: Optional[str] = None


class HourBucket(BaseModel):
    hour: str          # "2026-09-05T14:00Z"
    count: int


class AnalyticsOverview(BaseModel):
    generated_at: datetime
    window_hours: int

    total_events: int
    total_events_in_window: int
    readable_reads_in_window: int      # plate != UNKNOWN
    unknown_reads_in_window: int
    distinct_plates_in_window: int

    detections_by_type: List[LabelCount]       # all-time, vehicle_type -> count
    detections_by_camera: List[LabelCount]     # window, top N, code -> count (+name)
    top_plates: List[LabelCount]               # window, top N, excludes UNKNOWN
    recent_activity_by_hour: List[HourBucket]  # last `window_hours` hourly buckets

    watchlist_matches_total: int
    watchlist_matches_in_window: int
    active_alerts: int
