"""OpenTelemetry tracing with GenAI semantic conventions, exported to Langfuse.

Activation is opt-in and inert by default: if ``OTEL_EXPORTER_OTLP_ENDPOINT``
is unset the module installs nothing, imports no exporter and costs no memory.
That matters because Langfuse is a separate profile that only runs when the
host has the headroom for ClickHouse.

Langfuse accepts OTLP over **HTTP/protobuf only** — gRPC is not supported — at
``/api/public/otel``, authenticated with HTTP Basic over
``base64(public_key:secret_key)``.

Per ADR-0006 and ``docs/protocols/otel-genai-semconv.md``, prompt and completion
bodies must never land in span *attributes*. Only metadata is recorded here:
model, token counts, latency and outcome. The bodies belong in span events with
a 32 KB cap and OTTL redaction at the collector, which is a Stage-03 concern.
"""

from __future__ import annotations

import base64
import logging
import os
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("agent_backend.tracing")

_enabled = False


def is_enabled() -> bool:
    """True when a tracer provider was successfully installed."""
    return _enabled


def setup_tracing(service_name: str, service_version: str = "1.0.0") -> bool:
    """Install an OTLP/HTTP tracer provider. Returns False when not configured.

    Never raises: tracing is observability, and a misconfigured collector must
    not stop the agent from serving traffic.
    """
    global _enabled
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        logger.info("tracing disabled (OTEL_EXPORTER_OTLP_ENDPOINT unset)")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning("opentelemetry packages are not installed; tracing disabled")
        return False

    headers: dict[str, str] = {}
    public = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret = os.getenv("LANGFUSE_SECRET_KEY", "")
    if public and secret:
        token = base64.b64encode(f"{public}:{secret}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
        headers["x-langfuse-ingestion-version"] = "4"

    try:
        provider = TracerProvider(
            resource=Resource.create(
                {"service.name": service_name, "service.version": service_version}
            )
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=endpoint, headers=headers or None),
                max_queue_size=512,
                max_export_batch_size=64,
            )
        )
        trace.set_tracer_provider(provider)
    except Exception as exc:  # noqa: BLE001 - never block startup on telemetry
        logger.warning("tracing setup failed", extra={"err": exc.__class__.__name__})
        return False

    _enabled = True
    logger.info("tracing enabled", extra={"endpoint": endpoint, "authenticated": bool(headers)})
    return True


def instrument_app(app: Any) -> None:
    """Attach FastAPI and httpx instrumentation when tracing is live.

    httpx instrumentation is what propagates ``traceparent`` across the A2A hop,
    so the kagent call appears as a child span rather than an orphan trace.
    """
    if not _enabled:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="/healthz,/readyz,/metrics")
    except Exception as exc:  # noqa: BLE001
        logger.warning("fastapi instrumentation failed", extra={"err": exc.__class__.__name__})
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception as exc:  # noqa: BLE001
        logger.warning("httpx instrumentation failed", extra={"err": exc.__class__.__name__})


@contextmanager
def gen_ai_span(
    operation: str,
    model: str,
    system: str = "gemini",
    **extra: Any,
):
    """Span carrying OTel GenAI semantic conventions.

    Records only ``gen_ai.*`` metadata. Prompt and completion text is
    deliberately excluded — see the module docstring.
    """
    if not _enabled:
        yield None
        return
    try:
        from opentelemetry import trace
    except ImportError:
        yield None
        return

    tracer = trace.get_tracer("agent_backend")
    with tracer.start_as_current_span(f"{operation} {model}") as span:
        span.set_attribute("gen_ai.system", system)
        span.set_attribute("gen_ai.operation.name", operation)
        span.set_attribute("gen_ai.request.model", model)
        for key, value in extra.items():
            if value is not None:
                span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.set_attribute("error.type", exc.__class__.__name__)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            raise
