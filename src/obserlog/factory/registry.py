"""
Registry of active `LoggerFactory` instances.

The decorator-based API (`@function_log`, `@class_log`) needs to discover
the factory that is currently in scope for the calling code. The registry
serves as that single source of truth and lives in its own module so
that decorators don't have to import the factory (and the factory doesn't
have to import the decorators).
"""
from __future__ import annotations

import logging
import threading
from contextlib import suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from obserlog.factory.logger_factory import LoggerFactory

_ATTR_NAME = "_logger_factory"
_STACK: list[LoggerFactory] = []
_LOCK = threading.Lock()


def publish(factory: LoggerFactory) -> None:
    """
    Make `factory` the active factory for decorator lookup.
    """
    with _LOCK:
        _STACK.append(factory)
    setattr(logging.Logger, _ATTR_NAME, factory)


def withdraw(factory: LoggerFactory) -> None:
    """
    Remove `factory` from the registry. If it was the top of the stack,
    fall back to the previous one.
    """
    with _LOCK, suppress(ValueError):
        _STACK.remove(factory)
    current = getattr(logging.Logger, _ATTR_NAME, None)
    if current is factory:
        with suppress(AttributeError):
            delattr(logging.Logger, _ATTR_NAME)
        with _LOCK:
            if _STACK:
                setattr(logging.Logger, _ATTR_NAME, _STACK[-1])


def active() -> LoggerFactory | None:
    """
    Return the most recently published factory, or `None`.
    """
    return getattr(logging.Logger, _ATTR_NAME, None)
