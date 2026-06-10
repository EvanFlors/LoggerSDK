"""Config package: top-level `LoggerConfig` + per-feature settings."""
from .logger_config import LoggerConfig
from .settings.amqp import AMQPSettings
from .settings.console import ConsoleSettings
from .settings.otel import OTelSettings
from .settings.queue import QueueSettings
from .settings.rotation import RotationSettings
from .settings.sampling import SamplingSettings

__all__ = [
    "AMQPSettings",
    "ConsoleSettings",
    "LoggerConfig",
    "OTelSettings",
    "QueueSettings",
    "RotationSettings",
    "SamplingSettings",
]
