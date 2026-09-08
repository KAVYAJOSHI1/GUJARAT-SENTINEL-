"""
Deterministic natural-language query parser (phase brief §1 / §2).

Rule-based intent + entity extraction. NO external call, NO LLM. This is
the parser both the Investigation Copilot and the NL search box share, so
the two can never drift. Anything it cannot resolve is recorded in
`parsed.notes` and surfaced to the officer -- the AI stays explainable.
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta

from app.schemas.ai import ParsedQuery
from app.services.plate_utils import normalize_plate
from app.services.vehicle_types import CANONICAL_VEHICLE_TYPES, _SYNONYMS

# Gujarat plate: GJ + 2 digits + 1-2 letters + 4 digits, tolerant of spaces/dashes.
_PLATE_RE = re.compile(r"\bGJ[\s\-]?\d{2}[\s\-]?[A-Z]{1,2}[\s\-]?\d{3,4}\b", re.IGNORECASE)
# camera tokens: "CAM-04", "CAM04", "camera 4", "cam 4", "mockcam01"
_CAM_RE = re.compile(r"\b((?:mock[\s\-]?)?cam(?:era)?)[\s\-]?0*(\d{1,4})\b", re.IGNORECASE)
_CAM_CODE_RE = re.compile(r"\b([A-Za-z]{2,}[\-_]?[A-Za-z]*[\-_]?\d{1,4})\b")

_COLORS = (
    "white", "black", "red", "blue", "silver", "grey", "gray", "green",
    "yellow", "orange", "brown", "gold", "maroon",
)

_INTENT_KEYWORDS = [
    ("VEHICLE_JOURNEY", ("journey", "route", "trajectory", "movement", "path", "trace ", "trace.", "how did", "travel")),
    ("CAMERA_SEARCH", ("which camera", "what camera", "cameras detected", "cameras saw", "spotted by")),
    ("ALERT_SEARCH", ("alert", "alarm")),
    ("INCIDENT_SEARCH", ("incident",)),
    ("CASE_SEARCH", ("case",)),
    ("EVIDENCE_SEARCH", ("evidence", "snapshot", "photo")),
    ("WATCHLIST_SEARCH", ("watchlist", "wanted vehicle", "stolen vehicle", "flagged vehicle")),
    ("VEHICLE_LAST_SEEN", ("last seen", "where is", "current location", "most recent")),
]

_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()


def _parse_relative_window(text: str, now: datetime):
    m = re.search(r"\b(last|past|previous)\s+(\d+)\s*(hour|hr|minute|min|day)s?\b", text)
    if m:
        n = int(m.group(2))
        unit = m.group(3)
        if unit.startswith(("hour", "hr")):
            delta, phrase = timedelta(hours=n), f"last {n} hour(s)"
        elif unit.startswith(("minute", "min")):
            delta, phrase = timedelta(minutes=n), f"last {n} minute(s)"
        else:
            delta, phrase = timedelta(days=n), f"last {n} day(s)"
        return now - delta, None, phrase
    if re.search(r"\btoday\b", text):
        return now.replace(hour=0, minute=0, second=0, microsecond=0), None, "today"
    if re.search(r"\byesterday\b", text):
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1), "yesterday"
    if re.search(r"\bthis week\b", text):
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, None, "this week"
    return None, None, None


def _parse_time_of_day(text: str):
    """Return (time_from, time_to) as 'HH:MM' strings, or (None, None)."""
    def _to_hhmm(hour: int, minute: int, ampm: str | None):
        h = hour % 12
        if ampm and ampm.lower().startswith("p"):
            h += 12
        elif ampm and ampm.lower().startswith("a"):
            pass
        else:
            h = hour  # 24h given
        h = max(0, min(23, h))
        return f"{h:02d}:{minute:02d}"

    # between X and Y
    m = re.search(
        r"\bbetween\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+(?:and|to|-)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
        text,
    )
    if m:
        return (
            _to_hhmm(int(m.group(1)), int(m.group(2) or 0), m.group(3)),
            _to_hhmm(int(m.group(4)), int(m.group(5) or 0), m.group(6)),
        )
    m = re.search(r"\bafter\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if m:
        return _to_hhmm(int(m.group(1)), int(m.group(2) or 0), m.group(3)), None
    m = re.search(r"\bbefore\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if m:
        return None, _to_hhmm(int(m.group(1)), int(m.group(2) or 0), m.group(3))
    return None, None


def _parse_min_duration(text: str):
    m = re.search(r"\b(?:more than|longer than|over|at least|>=?)\s+(\d+)\s*(second|sec|minute|min|hour|hr)s?\b", text)
    if not m:
        m = re.search(r"\bfor\s+(\d+)\s*(second|sec|minute|min|hour|hr)s?\b", text)
    if not m:
        return None
    n = int(m.group(1))
    u = m.group(2)
    if u.startswith(("sec",)):
        return n
    if u.startswith(("min",)):
        return n * 60
    return n * 3600


def parse_query(text: str, *, context_plate: str | None = None, now: datetime | None = None) -> ParsedQuery:
    now = now or datetime.utcnow()
    raw = text.strip()
    low = raw.lower()
    notes: list[str] = []

    # --- plate ---
    plate = None
    pm = _PLATE_RE.search(raw)
    if pm:
        plate = normalize_plate(pm.group(0))
    elif re.search(r"\b(this vehicle|this car|it|the vehicle|same vehicle|this plate)\b", low) and context_plate:
        plate = normalize_plate(context_plate)
        notes.append(f"'this vehicle' resolved to {plate} from page context")
    elif re.search(r"\b(this vehicle|this car|the vehicle)\b", low) and not context_plate:
        notes.append("query refers to 'this vehicle' but no plate context was provided")

    # --- cameras ---
    camera_codes: list[str] = []
    for m in _CAM_RE.finditer(raw):
        prefix = m.group(1).lower().replace(" ", "").replace("-", "")
        num = int(m.group(2))
        if prefix.startswith("mock"):
            camera_codes.append(f"MOCK_CAM{num:02d}")
        camera_codes.append(f"CAM-{num:02d}")
        camera_codes.append(f"CAM{num:02d}")
        camera_codes.append(f"cam{num:02d}")
    camera_codes = list(dict.fromkeys(camera_codes))

    # --- vehicle type / colour ---
    vtype = None
    for cand in list(CANONICAL_VEHICLE_TYPES) + list(_SYNONYMS.keys()):
        if re.search(rf"\b{re.escape(cand)}s?\b", low):
            vtype = _SYNONYMS.get(cand, cand)
            break
    vcolor = next((c for c in _COLORS if re.search(rf"\b{c}\b", low)), None)
    if vcolor in ("gray",):
        vcolor = "grey"

    # --- time ---
    date_from, date_to, rel = _parse_relative_window(low, now)
    tf, tt = _parse_time_of_day(low)
    min_dur = _parse_min_duration(low)

    watchlist_only = bool(re.search(r"\bwatchlist|wanted|stolen|flagged\b", low)) and "watchlist" in low
    unknown_only = bool(re.search(r"\bunknown (vehicle|plate|car)", low))

    # --- intent ---
    intent = None
    for name, kws in _INTENT_KEYWORDS:
        if any(k in low for k in kws):
            intent = name
            break
    if intent is None:
        if plate:
            intent = "VEHICLE_SEARCH"
        elif camera_codes or date_from or tf or tt or vtype or vcolor:
            intent = "TIME_RANGE_SEARCH"
        else:
            intent = "VEHICLE_SEARCH"
            notes.append("no clear entities found — treating as a broad vehicle search")
    # a plain "where was X seen" with no time is really a search, not journey
    if intent == "VEHICLE_LAST_SEEN" and re.search(r"\bwhere\b.*\bseen\b", low) and not re.search(r"last seen|current|most recent", low):
        intent = "VEHICLE_SEARCH"

    if intent in ("VEHICLE_JOURNEY", "VEHICLE_LAST_SEEN", "CAMERA_SEARCH") and not plate:
        notes.append(f"intent {intent} needs a plate; none found in the query")

    return ParsedQuery(
        intent=intent,
        plate=plate,
        camera_codes=[c for c in camera_codes if c.startswith(("CAM-", "MOCK_"))][:6] or camera_codes[:6],
        vehicle_type=vtype,
        vehicle_color=vcolor,
        date_from=date_from,
        date_to=date_to,
        time_from=tf,
        time_to=tt,
        relative_window=rel,
        watchlist_only=watchlist_only,
        unknown_only=unknown_only,
        min_duration_seconds=min_dur,
        notes=notes,
    )
