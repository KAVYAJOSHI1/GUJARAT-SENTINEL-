"""
RTSP credential handling for the SENTINEL stream ingestion layer.

The Sentinel RTSP server (``rtsp://103.250.160.189:8554/stream/<camera_id>``)
answers with HTTP Basic auth (``WWW-Authenticate: Basic realm="ipcam"``).
OpenCV/FFmpeg pick credentials up from the URL userinfo, so the cleanest way
to authenticate is to inject ``user:pass@`` into the netloc right before the
``cv2.VideoCapture(...)`` call -- and never anywhere else.

Rules:
  * credentials come ONLY from the environment (SENTINEL_RTSP_USERNAME /
    SENTINEL_RTSP_PASSWORD) or explicit function args -- never hard-coded;
  * if no credentials are configured, the URL is returned unchanged
    (unauthenticated behaviour preserved);
  * an URL that already carries inline userinfo is left alone;
  * :func:`redact_rtsp_url` is the ONLY string that should ever be logged.
"""
from __future__ import annotations

import os
import re
from typing import Optional, Tuple
from urllib.parse import quote, urlsplit, urlunsplit

__all__ = [
    "env_rtsp_credentials",
    "has_inline_credentials",
    "apply_rtsp_credentials",
    "redact_rtsp_url",
]

_USERINFO_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*://)([^/@]+@)")


def env_rtsp_credentials() -> Tuple[Optional[str], Optional[str]]:
    """Return ``(username, password)`` from the environment (either may be None)."""
    return (
        os.environ.get("SENTINEL_RTSP_USERNAME") or None,
        os.environ.get("SENTINEL_RTSP_PASSWORD") or None,
    )


def has_inline_credentials(url: Optional[str]) -> bool:
    if not url:
        return False
    try:
        parts = urlsplit(url)
        return bool(parts.username or parts.password)
    except ValueError:
        return bool(_USERINFO_RE.match(url))


def apply_rtsp_credentials(
    url: Optional[str],
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Optional[str]:
    """Inject Basic-auth userinfo into an ``rtsp://`` URL.

    Precedence: explicit args > inline userinfo already in the URL > env vars.
    Returns the URL unchanged for non-RTSP schemes, when no credentials are
    available, or when the URL already has userinfo.
    """
    if not url or not str(url).lower().startswith("rtsp://"):
        return url
    if has_inline_credentials(url):
        return url

    if username is None and password is None:
        username, password = env_rtsp_credentials()
    if not username or not password:
        return url  # unauthenticated behaviour preserved

    parts = urlsplit(url)
    host = parts.hostname or ""
    netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{host}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def redact_rtsp_url(url: Optional[str]) -> Optional[str]:
    """``rtsp://user:pass@host:554/x`` -> ``rtsp://***:***@host:554/x``.

    Safe to log. Always use this instead of the raw (possibly authenticated)
    URL. Never raises.
    """
    if not url:
        return url
    try:
        parts = urlsplit(url)
        if parts.username or parts.password:
            host = parts.hostname or ""
            if parts.port:
                host = f"{host}:{parts.port}"
            return urlunsplit((parts.scheme, f"***:***@{host}", parts.path, parts.query, parts.fragment))
        return url
    except ValueError:
        return _USERINFO_RE.sub(r"\1***:***@", str(url))
