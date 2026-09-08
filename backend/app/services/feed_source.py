"""
Feed-source abstraction (Phase 15H §12).

One place decides whether a camera / detection is a REAL government feed, a
local MOCK stream, or seeded DEMO data. Derived, never guessed:

    DEMO   -- is_demo is set (seed_ai_demo / DEMO scenarios)
    MOCK   -- code matches ^mock[_-]?cam  (a local simulated clip)
    REAL   -- everything else (a government RTSP feed)

The frontend badges each explicitly. Demo data is NEVER shown as
government CCTV.
"""
import re

_MOCK_RE = re.compile(r"^mock[_-]?cam", re.IGNORECASE)

REAL = "REAL"
MOCK = "MOCK"
DEMO = "DEMO"


def feed_source(*, is_demo: bool = False, code: str | None = None) -> str:
    if is_demo:
        return DEMO
    if code and _MOCK_RE.match(code):
        return MOCK
    return REAL


def is_mock_code(code: str | None) -> bool:
    return bool(code and _MOCK_RE.match(code))
