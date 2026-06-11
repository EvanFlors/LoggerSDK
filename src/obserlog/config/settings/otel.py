"""OpenTelemetry settings."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

_Protocol = Literal["grpc", "http"]


class OTelSettings(BaseModel):
    enabled: bool = False
    service_name: str | None = None
    otlp_endpoint: str | None = "http://localhost:4317"  # gRPC default
    http_endpoint: str | None = "http://localhost:4318"  # HTTP default
    protocol: _Protocol = "grpc"
    insecure: bool = True
    sample_ratio: float = 1.0
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_s: float = 10.0
