"""Backwards-compatibility shim. The config now lives in `config/`."""
from .config.logger_config import LoggerConfig
from .config.settings.amqp import AMQPSettings
from .config.settings.console import ConsoleSettings
from .config.settings.otel import OTelSettings
from .config.settings.queue import QueueSettings
from .config.settings.rotation import RotationSettings
from .config.settings.sampling import SamplingSettings

__all__ = [
    "AMQPSettings",
    "ConsoleSettings",
    "LoggerConfig",
    "OTelSettings",
    "QueueSettings",
    "RotationSettings",
    "SamplingSettings",
]
