"""
Public API surface.

Re-exports the classes and exceptions that downstream code (and our own
examples / tests) are expected to import.
"""
from .config.logger_config import LoggerConfig
from .config.settings.amqp import AMQPSettings
from .config.settings.console import ConsoleSettings
from .config.settings.otel import OTelSettings
from .config.settings.queue import QueueSettings
from .config.settings.rotation import RotationSettings
from .config.settings.sampling import SamplingSettings
from .core.context import BoundLogger
from .core.tracer import Tracer

# Backwards-compat names.
from .errors import (
    AMQPConnectError,
    AMQPError,
    ConfigError,
    HandlerBuildError,
    HandlerError,
    HandlerInitError,
    LoggerConfigError,
    LoggerError,
    LoggerShutdownError,
    OTelError,
    ShutdownError,
)
from .factory import LoggerFactory

__all__ = [
    # errors (backwards-compat)
    "AMQPConnectError",
    "AMQPError",
    "AMQPSettings",
    # core
    "BoundLogger",
    "ConfigError",
    "ConsoleSettings",
    "HandlerBuildError",
    "HandlerError",
    "HandlerInitError",
    # config
    "LoggerConfig",
    "LoggerConfigError",
    # errors (new names)
    "LoggerError",
    # factory
    "LoggerFactory",
    "LoggerShutdownError",
    "OTelError",
    "OTelSettings",
    "QueueSettings",
    "RotationSettings",
    "SamplingSettings",
    "ShutdownError",
    "Tracer",
]
