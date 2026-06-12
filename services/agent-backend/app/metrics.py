"""Prometheus metrics for the agent-backend."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "agent_backend_requests_total",
    "Total HTTP requests handled.",
    labelnames=("method", "path", "status"),
)

REQUEST_LATENCY = Histogram(
    "agent_backend_request_latency_seconds",
    "HTTP request latency in seconds.",
    labelnames=("method", "path"),
)

ERROR_COUNT = Counter(
    "agent_backend_errors_total",
    "Total handler errors by type.",
    labelnames=("path", "type"),
)

A2A_CALL_COUNT = Counter(
    "agent_backend_a2a_calls_total",
    "Total A2A calls to the kagent Agent.",
    labelnames=("outcome",),
)
