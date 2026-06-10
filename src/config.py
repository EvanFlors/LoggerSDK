from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_VALID_LOG_LEVELS = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

def _to_level(value: str) -> int:
    level = value.upper()
    if level not in logging._nameToLevel:
        raise ValueError(f"Invalid log level: {value}")
    return logging._nameToLevel[level]


class SamplingSettings(BaseModel):
    rate: float = Field(..., gt=0.0, le=1.0)
    min_level: _VALID_LOG_LEVELS = "WARNING"
    deterministic: bool = False

    @field_validator("min_level")
    @classmethod
    def _v_level(cls, v: str) -> str:
        _to_level(v)
        return v.upper()

class RotationSettings(BaseModel):
    max_bytes: int | None = 10_000_000
    backup_count: int | None = 5
    when: Literal["S", "M", "H", "D", "MIDNIGHT", "W0", "W1", "W2", "W3", "W4", "W5", "W6"] | None = None

class QueueSettings(BaseModel):
    capacity: int = 10_000
    overflow: Literal["drop_oldest", "drop_newest", "block"] = "drop_oldest"
    flush_on_exit: bool = True

class ConsoleSettings(BaseModel):
    enabled: bool = True
    colors: bool = True
    destination: Literal["stdout", "stderr"] = "stdout"

class AMQPSettings(BaseModel):
    url: str = "amqp://guest:guest@localhost:5672/"
    exchange: str = "logs"
    exchange_type: Literal["direct", "topic", "fanout", "headets"] = "fanout"
    routing_key: str = ""
    queue: str = "logs"
    durable: bool = True
    batch_size: int = 100
    flush_interval_s: float = 1.0
    transport: Literal["sync", "async"] = "sync"
    fail_open: bool = True
    connect_timeout_s: float = 5.0
    max_retries: int = 5

class OTelSettings(BaseModel):
    enabled: bool = False
    service_name: str | None = None
    otlp_endpoint: str | None = "http://localhost:4317" # gRCP default
    http_endpoint: str | None = "http://localhost:4318" # HTTP default
    protocol: Literal["http", "grpc"] = "grpc"
    insecure: bool = True
    sample_ratio: float = 1.0
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_s: float = 10.0

class LoggerConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="LOGGER_",
        env_nested_delimiter="__",
        extra="ignore"
    )

    service_name: str = "app"
    level: str = "INFO"
    directory: str = "logs"
    json_logs: bool = True
    date_format: str = "%Y-%m-%dT%H:%M:%S.%fZ"
    module_levels: dict[str, str] = Field(default_factory=dict)

    sampling: SamplingSettings = Field(default_factory=SamplingSettings)
    rotation: RotationSettings = Field(default_factory=RotationSettings)
    queue: QueueSettings = Field(default_factory=QueueSettings)
    console: ConsoleSettings = Field(default_factory=ConsoleSettings)
    amqp: AMQPSettings = Field(default_factory=AMQPSettings)
    otel: OTelSettings = Field(default_factory=OTelSettings)

    @field_validator("level")
    @classmethod
    def _v_level(cls, v: str) -> str:
        _to_level(v)
        return v.upper()

    def numeric_level(self) -> int:
        return _to_level(self.level)