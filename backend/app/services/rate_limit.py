"""
In-process login rate limiter for POST /api/v1/auth/login.

Scope / limitation (documented, not hidden): this counter lives in the
backend process's memory. With more than one backend replica behind a load
balancer, each replica enforces the limit independently, so the effective
global limit is `replicas * MAX_FAILURES`. A shared-store (Redis) limiter
that holds across replicas is ROADMAP (see SECURITY.md). For the current
single-node deployment this is a real, effective brute-force slowdown.

Design:
  * key   = f"{client_ip}|{username_lower}" -- limits per (source, account),
            so one noisy IP can't lock out every account and one targeted
            account can't be hammered from a single IP.
  * a failed attempt appends `now` to the key's list (pruned to WINDOW).
  * once >= MAX_FAILURES failures sit inside the window, the key is blocked
    for BLOCK_SECONDS; `check()` returns the remaining block seconds.
  * a SUCCESSFUL login calls `reset(key)` -- the account owner logging in
    correctly immediately clears the throttle.

Never receives or stores a password or token -- only timestamps and the
already-non-secret (ip, username) key.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Optional

from app.config import settings


class LoginRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key -> deque[float] of recent failure timestamps (monotonic)
        self._failures: Dict[str, Deque[float]] = {}
        # key -> monotonic timestamp until which the key is blocked
        self._blocked_until: Dict[str, float] = {}
        self._last_prune = 0.0

    # -- config (read live so tests can monkeypatch settings) ------------ #
    @property
    def _enabled(self) -> bool:
        return bool(settings.LOGIN_RATE_LIMIT_ENABLED)

    @property
    def _max_failures(self) -> int:
        return int(settings.LOGIN_RATE_LIMIT_MAX_FAILURES)

    @property
    def _window(self) -> int:
        return int(settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS)

    @property
    def _block(self) -> int:
        return int(settings.LOGIN_RATE_LIMIT_BLOCK_SECONDS)

    # -- public API ----------------------------------------------------- #
    @staticmethod
    def make_key(ip: Optional[str], username: str) -> str:
        return f"{ip or 'unknown'}|{(username or '').strip().lower()}"

    def check(self, key: str) -> Optional[int]:
        """Return remaining block seconds (>=1) if the key is currently
        rate-limited, else None."""
        if not self._enabled:
            return None
        now = time.monotonic()
        with self._lock:
            self._maybe_prune(now)
            until = self._blocked_until.get(key)
            if until is not None and until > now:
                return max(1, int(round(until - now)))
            if until is not None:
                # block expired
                self._blocked_until.pop(key, None)
                self._failures.pop(key, None)
            return None

    def record_failure(self, key: str) -> None:
        if not self._enabled:
            return
        now = time.monotonic()
        with self._lock:
            dq = self._failures.setdefault(key, deque())
            dq.append(now)
            cutoff = now - self._window
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self._max_failures:
                self._blocked_until[key] = now + self._block

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._blocked_until.pop(key, None)

    def clear(self) -> None:
        """Test hook -- wipe all state."""
        with self._lock:
            self._failures.clear()
            self._blocked_until.clear()

    # -- housekeeping -------------------------------------------------- #
    def _maybe_prune(self, now: float) -> None:
        if now - self._last_prune < 60.0:
            return
        self._last_prune = now
        cutoff = now - self._window
        for k in list(self._failures.keys()):
            dq = self._failures[k]
            while dq and dq[0] < cutoff:
                dq.popleft()
            if not dq and self._blocked_until.get(k, 0.0) <= now:
                self._failures.pop(k, None)
                self._blocked_until.pop(k, None)


login_rate_limiter = LoginRateLimiter()
