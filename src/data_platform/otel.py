"""OpenTelemetry tracing wired for SigNoz.

Spans are exported over OTLP/gRPC to the collector (which forwards to SigNoz).
`requests` is auto-instrumented so every HTTP call to the source API shows up as
a child span on the ingest trace.
"""

from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .config import settings

_log = logging.getLogger(__name__)
_configured = False


def configure_telemetry() -> None:
    """Idempotently install the global tracer provider + OTLP exporter."""
    global _configured
    if _configured:
        return

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "deployment.environment": settings.deployment_environment,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=settings.otel_exporter_otlp_endpoint.startswith("http://"),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    try:
        RequestsInstrumentor().instrument()
    except Exception:  # already instrumented in a re-imported subprocess
        _log.debug("requests instrumentation already active")

    _configured = True
    _log.info("OpenTelemetry configured -> %s", settings.otel_exporter_otlp_endpoint)


def get_tracer(name: str = "data_platform") -> trace.Tracer:
    configure_telemetry()
    return trace.get_tracer(name)
