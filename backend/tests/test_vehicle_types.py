"""Phase 5 -- canonical vehicle-type handling."""
import pytest

from app.services.vehicle_types import CANONICAL_VEHICLE_TYPES, canonical_vehicle_type


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("car", "car"),
        ("Car", "car"),
        ("  CAR ", "car"),
        ("motorcycle", "motorcycle"),
        ("motorbike", "motorcycle"),
        ("Bike", "motorcycle"),
        ("lorry", "truck"),
        ("VAN", "truck"),
        ("minibus", "bus"),
        ("auto", "auto-rickshaw"),
        ("rickshaw", "auto-rickshaw"),
        ("suv", "car"),
        ("", None),
        ("   ", None),
        (None, None),
        # unrecognised but real -> kept, just lower-cased (never upgraded)
        ("armoured personnel carrier", "armoured personnel carrier"),
    ],
)
def test_canonical_vehicle_type(raw, expected):
    assert canonical_vehicle_type(raw) == expected


def test_yolo_default_classes_are_all_canonical():
    for cls in ("car", "motorcycle", "bus", "truck"):
        assert canonical_vehicle_type(cls) == cls
        assert cls in CANONICAL_VEHICLE_TYPES
