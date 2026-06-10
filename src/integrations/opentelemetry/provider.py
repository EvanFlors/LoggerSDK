"""
Configure the global OpenTelemetry `TracerProvider` for this process.

Idempotent. No-op if OTel is not installed or `OTelSettings.enabled=False`.
Also calls `LoggingInstrumentor().instrument(set_logging_format=False)` so
third-party `logging` calls carry the active `trace_id` / `span_id` too.
"""
from __future__ import annotations

from typing import Any

from src.config import OTelSettings


def configure_opentelemetry(settings: OTelSettings, service_name_hint: str = "") -> None:
    if not settings.enabled:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except ImportError:
        return  # OTel is optional

    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return  # already configured

    # Local import to avoid a hard dependency on the adapter's deps.
    from integrations.opentelemetry.exporter import OTLPSettingsAdapter

    resource = Resource.create(
        {"service.name": settings.service_name or service_name_hint or "logger"}
    )
    provider = TracerProvider(
        resource=resource,
        sampler=TraceIdRatioBased(settings.sample_ratio),
    )
    exporter: Any = OTLPSettingsAdapter(settings).build_exporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    try:
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        LoggingInstrumentor().instrument(set_logging_format=False)
    except Exception:
        pass
