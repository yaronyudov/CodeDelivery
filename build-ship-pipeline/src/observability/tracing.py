"""OpenTelemetry instrumentation for the agent plane.

Call setup_tracing() once at startup.  All other symbols are module-level
singletons used by governed() and individual agent nodes.
"""
from __future__ import annotations

import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_SERVICE_NAME = "build-ship-pipeline"
_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")


def setup_tracing() -> None:
    """Configure OTel SDK with OTLP exporters.  Safe to call multiple times."""
    resource = Resource(attributes={"service.name": _SERVICE_NAME})

    # Traces → Tempo via OTLP
    tp = TracerProvider(resource=resource)
    tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=_OTLP_ENDPOINT)))
    trace.set_tracer_provider(tp)

    # Metrics → Prometheus via OTLP collector
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=_OTLP_ENDPOINT),
        export_interval_millis=15_000,
    )
    mp = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(mp)


# Module-level singletons; safe to import before setup_tracing() is called
# because the SDK returns a no-op tracer/meter until a provider is set.
tracer = trace.get_tracer(_SERVICE_NAME)
_meter = metrics.get_meter(_SERVICE_NAME)

# Counters emitted by governed() and agent nodes
cost_counter = _meter.create_counter(
    "agent_cost_usd",
    description="Cumulative USD cost per agent",
)
token_counter = _meter.create_counter(
    "agent_tokens",
    description="Cumulative token count per agent",
)
halt_counter = _meter.create_counter(
    "agent_halts",
    description="Number of budget-induced halts per agent",
)
latency_histogram = _meter.create_histogram(
    "agent_latency_seconds",
    description="Wall-clock time per agent node call",
)
parse_failure_counter = _meter.create_counter(
    "llm_parse_failures",
    description="Number of LLM output parse/validation failures per agent",
)
run_counter = _meter.create_counter(
    "pipeline_runs_total",
    description="Total pipeline runs started",
)
ws_events_counter = _meter.create_counter(
    "ws_events_sent",
    description="WebSocket events published to clients",
)


def record_agent_usage(
    agent: str, tokens: int, cost_usd: float, latency_s: float
) -> None:
    """Emit all per-action metrics in one call (used by governed())."""
    attrs = {"agent": agent}
    token_counter.add(tokens, attrs)
    cost_counter.add(cost_usd, attrs)
    latency_histogram.record(latency_s, attrs)
