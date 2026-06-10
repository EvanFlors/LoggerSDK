"""
Build the right OTLP span exporter from `OTelSettings`.

- `protocol="grpc"` → `opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter`
- `protocol="http"` → `opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter`
"""
from __future__ import annotations

from typing import Any

from src.config import OTelSettings


class OTLPSettingsAdapter:
    """Resolves gRPC vs HTTP exporter from a single `OTelSettings`."""

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
            endpoint=f"{(self.settings.http_endpoint or 'http://localhost:4318').rstrip('/')}/v1/traces",
            headers=self.settings.headers,
            timeout=self.settings.timeout_s,
        )
