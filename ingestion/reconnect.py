"""
Exponential backoff reconnection engine.

Ladder per spec: 2s -> 4s -> 8s -> 16s -> 30s, then holds at 30s.
Deliberately has zero OpenCV / network dependencies so it can be unit
tested in isolation and reused by any worker that needs "retry with
backoff, stop cleanly on shutdown".
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple, TypeVar

logger = logging.getLogger("sentinel.ingestion.reconnect")

T = TypeVar("T")

DEFAULT_LADDER: Tuple[float, ...] = (2.0, 4.0, 8.0, 16.0, 30.0)


@dataclass
class BackoffPolicy:
    """Stateful backoff sequence generator.

    Not thread-safe by itself -- each StreamWorker owns its own instance,
    so no locking is needed.
    """

    ladder: Tuple[float, ...] = DEFAULT_LADDER
    _index: int = field(default=0, init=False, repr=False)

    def reset(self) -> None:
        """Call after a successful (re)connection to restart the ladder."""
        self._index = 0

    def next_delay(self) -> float:
        """Return the next delay and advance the step counter.

        Stays at the final (max) rung once reached, per spec (cap at 30s)
        rather than continuing to grow or wrapping back to the start.
        """
        delay = self.ladder[min(self._index, len(self.ladder) - 1)]
        if self._index < len(self.ladder) - 1:
            self._index += 1
        return delay


class ReconnectSupervisor:
    """Runs `connect_fn` repeatedly with backoff until it succeeds or
    `stop_event` is set.

    `connect_fn` should return a truthy "connection handle" on success, or
    raise / return None/False on failure. This class does not decide *when*
    a reconnect is needed -- the caller (StreamWorker) detects the frame
    read failure and invokes this.
    """

    def __init__(
        self,
        connect_fn: Callable[[], Optional[T]],
        stop_event: threading.Event,
        ladder: Tuple[float, ...] = DEFAULT_LADDER,
        on_attempt: Optional[Callable[[int, float], None]] = None,
    ) -> None:
        self._connect_fn = connect_fn
        self._stop_event = stop_event
        self._policy = BackoffPolicy(ladder=ladder)
        self._on_attempt = on_attempt
        self._attempt_count = 0

    def reset(self) -> None:
        self._policy.reset()
        self._attempt_count = 0

    def run(self) -> Optional[T]:
        """Blocks (in the calling thread) until connected or stopped."""
        while not self._stop_event.is_set():
            self._attempt_count += 1
            try:
                handle = self._connect_fn()
            except Exception as exc:  # noqa: BLE001 -- any failure means retry
                logger.warning("Reconnect attempt %d failed: %s", self._attempt_count, exc)
                handle = None

            if handle:
                self.reset()
                return handle

            delay = self._policy.next_delay()
            if self._on_attempt:
                self._on_attempt(self._attempt_count, delay)
            logger.info(
                "Reconnect attempt %d failed, retrying in %.0fs", self._attempt_count, delay
            )

            # Sleep until the next retry interval, stopping immediately if stop_event is set.
            if self._stop_event.wait(timeout=delay):
                return None

        return None
