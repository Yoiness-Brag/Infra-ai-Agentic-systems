"""A2A (JSON-RPC 2.0) client for the kagent Agent.

Sends the user message (plus retrieved memory context) to the kagent Agent's
A2A endpoint and returns the agent's text result. The transport speaks the A2A
``message/send`` method (``params.message`` with ``parts``) and adds a bounded
retry with jitter, a request timeout, and a lightweight circuit breaker so a
sick kagent never stalls every request.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from dataclasses import dataclass

import httpx

from .config import Settings

logger = logging.getLogger("agent_backend.a2a")


class A2AError(RuntimeError):
    """Raised when the kagent Agent cannot be reached or returns an error."""


class CircuitOpenError(A2AError):
    """Raised when the breaker is open and the call is short-circuited."""


@dataclass
class _Breaker:
    """Minimal consecutive-failure circuit breaker."""

    threshold: int
    cooldown: float
    failures: int = 0
    opened_at: float = 0.0

    def allow(self) -> bool:
        """Return True if a call may proceed (closed, or a probe after cooldown)."""
        if self.failures < self.threshold:
            return True
        if (time.monotonic() - self.opened_at) >= self.cooldown:
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
        """Return True while the breaker is tripped."""
        return self.failures >= self.threshold


class A2AClient:
    """Async A2A client wrapping a shared httpx.AsyncClient."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._url = settings.kagent_agent_a2a_url
        self._client: httpx.AsyncClient | None = None
        self._breaker = _Breaker(
            threshold=settings.a2a_breaker_threshold,
            cooldown=settings.a2a_breaker_cooldown_seconds,
        )

    async def connect(self) -> None:
        """Create the shared HTTP client (idempotent)."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._settings.a2a_timeout_seconds),
                headers={"Content-Type": "application/json"},
            )

    async def close(self) -> None:
        """Close the shared HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def breaker_open(self) -> bool:
        """Return True while the A2A circuit breaker is tripped."""
        return self._breaker.is_open

    def _build_payload(self, text: str, context_id: str | None) -> dict:
        """Build the JSON-RPC ``message/send`` request envelope."""
        request_id = str(uuid.uuid4())
        message: dict[str, object] = {
            "role": "user",
            "parts": [{"kind": "text", "text": text}],
            "messageId": str(uuid.uuid4()),
            "kind": "message",
        }
        if context_id:
            message["contextId"] = context_id
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "message/send",
            "params": {"message": message},
        }

    @staticmethod
    def _compose_prompt(message: str, memory_context: list[str]) -> str:
        if not memory_context:
            return message
        facts = "\n".join(f"- {f}" for f in memory_context)
        return (
            "Relevant memory from earlier in this session:\n"
            f"{facts}\n\n"
            f"User message:\n{message}"
        )

    async def send(
        self,
        message: str,
        memory_context: list[str] | None = None,
        context_id: str | None = None,
    ) -> str:
        """Send a message to the kagent Agent and return its text answer.

        Applies the circuit breaker, then retries transient failures up to
        ``A2A_MAX_RETRIES`` with exponential backoff and full jitter.
        """
        if self._client is None:
            raise A2AError("a2a client not connected")
        if not self._breaker.allow():
            raise CircuitOpenError("kagent A2A circuit breaker is open")

        payload = self._build_payload(
            self._compose_prompt(message, memory_context or []), context_id
        )

        last_exc: Exception | None = None
        attempts = self._settings.a2a_max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                resp = await self._client.post(self._url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if "error" in data and data["error"]:
                    raise A2AError(f"a2a error: {data['error']}")
                answer = _extract_text(data.get("result"))
                self._breaker.record_success()
                return answer
            except (httpx.HTTPError, A2AError, ValueError) as exc:
                last_exc = exc
                self._breaker.record_failure()
                logger.warning(
                    "a2a call failed",
                    extra={"attempt": attempt, "max": attempts, "err": str(exc)},
                )
                if attempt < attempts and self._breaker.allow():
                    await asyncio.sleep(self._backoff_delay(attempt))
                    continue
                break

        raise A2AError(f"kagent A2A call failed after {attempts} attempt(s): {last_exc}")

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        """Exponential backoff with full jitter, capped at 5 seconds."""
        ceiling = min(5.0, 0.5 * (2 ** (attempt - 1)))
        return random.uniform(0.0, ceiling)  # noqa: S311


def _extract_text(result: object) -> str:
    """Pull the assistant text out of an A2A result envelope.

    kagent may return either a Message (``parts``) or a Task (``status.message``
    / ``artifacts``). Walk the common shapes defensively.
    """
    if result is None:
        raise A2AError("a2a result was empty")
    if isinstance(result, str):
        return result

    if isinstance(result, dict):
        text = _text_from_parts(result.get("parts"))
        if text:
            return text
        status = result.get("status")
        if isinstance(status, dict):
            msg = status.get("message")
            if isinstance(msg, dict):
                text = _text_from_parts(msg.get("parts"))
                if text:
                    return text
        artifacts = result.get("artifacts")
        if isinstance(artifacts, list):
            chunks = [
                _text_from_parts(a.get("parts"))
                for a in artifacts
                if isinstance(a, dict)
            ]
            joined = "".join(c for c in chunks if c)
            if joined:
                return joined

    raise A2AError("could not extract text from a2a result")


def _text_from_parts(parts: object) -> str:
    if not isinstance(parts, list):
        return ""
    out: list[str] = []
    for part in parts:
        if isinstance(part, dict):
            if part.get("kind") in (None, "text") or part.get("type") == "text":
                value = part.get("text")
                if isinstance(value, str):
                    out.append(value)
    return "".join(out)
