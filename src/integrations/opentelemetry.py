from __future__ import annotations

from typing import Any

from config import OTelSettings


class OTLPSettingsAdapter:
    """
    Resolves gRPC vs HTTP exporter from a single OTelSettings.
    """

    def __init__(self, settings: OTelSettings) -> None:
        self.settings = settings

    def build_exporter(self) -> Any:
        if self.settings.protocol == "grpc":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            return OTLPSpanExporter(
                endpoint=self.settings.otlp_endpoint,
                insecure=self.settings.insecure,
                headers=self.settings.headers,
                timeout=self.settings.timeout_s,
            )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as HTTPExporter,
        )
        return HTTPExporter(
            endpoint=f"{self.settings.http_endpoint.rstrip('/')}/v1/traces",
            headers=self.settings.headers,
            timeout=self.settings.timeout_s,
        )


def configure_opentelemetry(settings: OTelSettings, service_name_hint: str = "") -> None:
    """
    Sets the global TracerProvider with a BatchSpanProcessor pointing at the
    chosen OTLP exporter. Idempotent. If OTel SDK is not installed, no-op.
    """
    if not settings.enabled:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except ImportError:
        return  # OTel optional

    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return  # already configured

    resource = Resource.create({
        "service.name": settings.service_name or service_name_hint or "logger",
    })
    provider = TracerProvider(
        resource=resource,
        sampler=TraceIdRatioBased(settings.sample_ratio),
    )
    exporter = OTLPSettingsAdapter(settings).build_exporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    try:
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        LoggingInstrumentor().instrument(set_logging_format=False)
    except Exception:
        pass
