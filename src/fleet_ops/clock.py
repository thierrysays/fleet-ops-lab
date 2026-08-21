"""Injectable time.

Rollback deadlines are the reason this exists. A confirmation window measured
against ``time.monotonic()`` cannot be tested, and an untested rollback deadline
is a rollback that has never happened.
"""

from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()


class ManualClock:
    """Moves only when a test moves it."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = float(start)

    def monotonic(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += float(seconds)
