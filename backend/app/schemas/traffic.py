"""Schemas for Traffic Analytics + heatmap (Phase 14 §4, §5)."""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class HourCount(BaseModel):
    hour: str
    count: int


class LabelCount(BaseModel):
    label: str
    count: int
    detail: Optional[str] = None
    per_hour: Optional[float] = None


class TrafficOverview(BaseModel):
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    window_hours: int
    total_vehicles: int
    readable_plates: int
    unknown_plates: int
    distinct_plates: int
    active_cameras: int
    vehicles_per_hour: float
    peak_hour: Optional[HourCount] = None
    trend: str                       # up | down | flat
    trend_pct: Optional[float] = None
    prev_window_total: int
    congestion: str                  # NONE | LOW | MODERATE | HIGH
    vehicle_type_distribution: List[LabelCount] = []
    top_cameras: List[LabelCount] = []
    filters_applied: Dict[str, Optional[object]] = {}


class CameraTraffic(BaseModel):
    camera_id: str
    camera_code: Optional[str] = None
    camera_name: Optional[str] = None
    location_desc: Optional[str] = None
    total_vehicles: int
    readable_plates: int
    vehicles_per_hour: float
    busiest_hour: Optional[HourCount] = None
    congestion: str


class TrafficByCamera(BaseModel):
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    window_hours: int
    cameras: List[CameraTraffic] = []
    filters_applied: Dict[str, Optional[object]] = {}


class TrendPoint(BaseModel):
    bucket: str
    total: int
    readable: int


class TrafficTrends(BaseModel):
    generated_at: datetime
    bucket: str
    window_start: datetime
    window_end: datetime
    window_hours: int
    series: List[TrendPoint] = []
    total: int
    mean_per_bucket: float
    max_bucket: Optional[TrendPoint] = None
    filters_applied: Dict[str, Optional[object]] = {}


class HeatPoint(BaseModel):
    camera_id: str
    camera_code: Optional[str] = None
    camera_name: Optional[str] = None
    latitude: float
    longitude: float
    count: int
    weight: float


class TrafficHeatmap(BaseModel):
    generated_at: datetime
    kind: str
    window_start: datetime
    window_end: datetime
    window_hours: int
    max_count: int
    geolocated_cameras: int
    contributing_cameras: int
    points: List[HeatPoint] = []
    note: str
    filters_applied: Dict[str, Optional[object]] = {}
