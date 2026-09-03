"""Registration plate string normalization shared by ingestion and search."""
import re


def normalize_plate(raw_plate: str) -> str:
    """Uppercase and strip all non-alphanumeric characters, e.g. 'gj01 ab-1234' -> 'GJ01AB1234'."""
    return re.sub(r"[^A-Za-z0-9]", "", raw_plate or "").upper()
