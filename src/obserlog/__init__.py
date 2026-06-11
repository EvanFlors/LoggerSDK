"""
Public API surface.

Re-exports the classes and exceptions that downstream code (and our
own examples / tests) are expected to import.

Typical usage:

    from obserlog import LoggerFactory, LoggerConfig

    config = LoggerConfig(
        service_name="billing-api",
        level="INFO",
        directory="logs",
        json_logs=True,
        rotation={"max_bytes": 10_000_000, "backup_count": 5, "when": "midnight"},
        amqp={"url": "amqp://guest:guest@localhost:5672/", "exchange": "logs"},
        otel={"enabled": True, "otlp_endpoint": "http://localhost:4317", "protocol": "grpc"},
    )
    factory = LoggerFactory(config)
    log = factory.get_logger().bind(component="billing")
    log.info("started", extra={"user_id": 42})
    factory.shutdown()
"""
from .config.logger_config import LoggerConfig
from .config.settings.amqp import AMQPSettings
from .config.settings.console import ConsoleSettings
from .config.settings.otel import OTelSettings
from .config.settings.queue import QueueSettings
from .config.settings.rotation import RotationSettings
from .config.settings.sampling import SamplingSettings
from .core.context import BoundLogger
from .core.exception_render import (
    ExceptionReport,
    Frame,
    format_exception_pretty,
    format_exception_structured,
    rich_format_exception,
)
from .core.formatters.colored_formatter import ConsoleFormatter
from .core.formatters.json_formatter import JSONFormatter
from .core.tracer import Tracer, _NoopSpan  # noqa: F401 — internal

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
    "AMQPConnectError",
    "AMQPError",
    "AMQPSettings",
    "BoundLogger",
    "ConfigError",
    "ConsoleFormatter",
    "ConsoleSettings",
    "ExceptionReport",
    "Frame",
    "HandlerBuildError",
    "HandlerError",
    "HandlerInitError",
    "JSONFormatter",
    "LoggerConfig",
    "LoggerConfigError",
    "LoggerError",
    "LoggerFactory",
    "LoggerShutdownError",
    "OTelError",
    "OTelSettings",
    "QueueSettings",
    "RotationSettings",
    "SamplingSettings",
    "ShutdownError",
    "Tracer",
    "format_exception_pretty",
    "format_exception_structured",
    "rich_format_exception",
]
