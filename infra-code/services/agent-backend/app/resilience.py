"""Shared resilience primitives.

The platform invariant is a circuit breaker on every external dependency
(LLM, FalkorDB, Postgres, MinIO, MCP tool). This module holds the one
implementation they all share.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


class CircuitOpenError(RuntimeError):
    """Raised when the breaker is open and a call is short-circuited."""


@dataclass
class Breaker:
    """Consecutive-failure circuit breaker with a half-open probe.

    ``allow()`` is the only admission gate. After ``cooldown`` elapses the
    breaker drops to ``threshold - 1`` failures so that a single successful
    probe closes it again; without that step the failure count could never
    fall back below the threshold on its own.
    """

    name: str
    threshold: int
    cooldown: float
    failures: int = 0
    opened_at: float = 0.0

    def allow(self) -> bool:
        """Return True if a call may proceed (closed, or a probe after cooldown)."""
        if self.failures < self.threshold:
            return True
        if (time.monotonic() - self.opened_at) >= self.cooldown:
            self.failures = max(self.threshold - 1, 0)
            self.opened_at = 0.0
            return True
        return False

    def record_success(self) -> None:
        """Reset failure state after a successful call."""
        self.failures = 0
        self.opened_at = 0.0

    def record_failure(self) -> None:
        """Count a failure and arm the cooldown when the threshold is reached."""
        self.failures += 1
        if self.failures >= self.threshold and self.opened_at == 0.0:
            self.opened_at = time.monotonic()

    @property
    def is_open(self) -> bool:
        """True while the breaker is tripped and still inside its cooldown."""
        if self.failures < self.threshold:
            return False
        return (time.monotonic() - self.opened_at) < self.cooldown
