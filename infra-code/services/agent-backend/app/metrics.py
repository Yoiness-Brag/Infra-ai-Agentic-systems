"""Prometheus metrics for the agent-backend."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

REQUEST_COUNT = Counter(
    "agent_backend_requests_total",
    "Total HTTP requests handled.",
    labelnames=("method", "path", "status"),
)

REQUEST_LATENCY = Histogram(
    "agent_backend_request_latency_seconds",
    "HTTP request latency in seconds.",
    labelnames=("method", "path"),
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 120, 300, float("inf")),
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

IN_FLIGHT = Gauge(
    "agent_backend_in_flight_requests",
    "Requests currently being served. Drives the KEDA concurrency trigger.",
    labelnames=("path",),
)

INGEST_CHUNKS = Counter(
    "agent_backend_ingest_chunks_total",
    "Document chunks written to the memory graph.",
    labelnames=("outcome",),
)

INGEST_JOBS = Counter(
    "agent_backend_ingest_jobs_total",
    "Document ingestion jobs by terminal state.",
    labelnames=("state",),
)

INGEST_DURATION = Histogram(
    "agent_backend_ingest_duration_seconds",
    "Wall-clock duration of a document ingestion job.",
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800, float("inf")),
)
