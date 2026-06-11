"""
Top-level `LoggerConfig`. Aggregates the per-feature settings models
and adds the cross-cutting knobs (service name, level, directory, …).
"""
from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .settings.amqp import AMQPSettings
from .settings.console import ConsoleSettings
from .settings.otel import OTelSettings
from .settings.queue import QueueSettings
from .settings.rotation import RotationSettings
from .settings.sampling import SamplingSettings, _to_level


class LoggerConfig(BaseSettings):
    """
    The single, full logger configuration. Read from kwargs, from
    environment variables prefixed with `LOGGER_` (nested keys use
    `__`), and from a `.env` file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="LOGGER_",
        env_nested_delimiter="__",
        extra="ignore",
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
    amqp: AMQPSettings | None = None
    otel: OTelSettings = Field(default_factory=OTelSettings)

    @field_validator("level")
    @classmethod
    def _v_level(cls, v: str) -> str:
        _to_level(v)
        return v.upper()

    def numeric_level(self) -> int:
        return _to_level(self.level)
