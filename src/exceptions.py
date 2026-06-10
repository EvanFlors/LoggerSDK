"""
Backwards-compatibility shim.

The exception types used to live in this file. They were renamed to
`src/errors.py` in v1.1.0; this module re-exports them so existing
imports (`from src.exceptions import AMQPConnectError`) keep working.
"""
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
