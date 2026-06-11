"""
Exception hierarchy for the logger package.

Renamed from `exceptions.py` to `errors.py` for discoverability and to
match the naming used by the rest of the modern Python ecosystem.
"""
from __future__ import annotations


class LoggerError(Exception):
    """Base for all logger errors."""


class ConfigError(LoggerError):
    """Invalid configuration."""


class HandlerError(LoggerError):
    """Generic handler failure."""


class HandlerBuildError(HandlerError):
    """A handler could not be constructed at factory-build time."""


class AMQPError(HandlerError):
    """An AMQP handler raised during connect, publish, or shutdown."""


class OTelError(HandlerError):
    """An OpenTelemetry integration raised."""


class ShutdownError(LoggerError):
    """Operation attempted after the factory is shut down."""


# ---------------------------------------------------------------------------
# Backwards-compatibility aliases
#
# The original `exceptions.py` exposed these names; downstream code (and our
# own modules that pre-date the rename) may still import them. Keep them
# alive as aliases for the v1.x line. New code should use the names above.
# ---------------------------------------------------------------------------
LoggerConfigError = ConfigError
HandlerInitError = HandlerBuildError
AMQPConnectError = AMQPError
LoggerShutdownError = ShutdownError

__all__ = [
    "AMQPConnectError",
    "AMQPError",
    "ConfigError",
    "HandlerBuildError",
    "HandlerError",
    "HandlerInitError",
    "LoggerConfigError",
    "LoggerError",
    "LoggerShutdownError",
    "OTelError",
    "ShutdownError",
]
