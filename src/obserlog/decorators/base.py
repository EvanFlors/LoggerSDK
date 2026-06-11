"""
Common plumbing for the `@function_log` and `@class_log` decorators.

`@function_log` and `@class_log` need to:
1. Find the active `LoggerFactory` (if any).
2. Resolve the calling context (file / class.method).
3. Build a `BoundLogger` bound to that context.

This module owns steps 1 and 2 in one place so both decorators stay thin.
"""
from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from obserlog.core.context import BoundLogger

if TYPE_CHECKING:
    from obserlog.factory.logger_factory import LoggerFactory


def active_factory() -> LoggerFactory | None:
    """
    Look up the active factory. Always returns `None` if no factory has
    been constructed yet (decorator becomes a transparent pass-through in
    that case).
    """
    from obserlog.factory.registry import active
    return active()


def build_context_string(func: object, args: tuple) -> str:
    """
    Build a `file | ClassName.method` string from a wrapped function and
    the positional args of the current call.
    """
    module = inspect.getmodule(func)
    file_path = getattr(module, "__file__", None) if module else None
    file_name = file_path.rsplit("/", 1)[-1] if file_path else "<unknown>"

    class_name: str | None = None
    if args:
        owner = args[0]
        # classmethod passes the class itself as args[0].
        if isinstance(owner, type):
            class_name = owner.__name__
        elif hasattr(owner, "__class__"):
            class_name = owner.__class__.__name__

    parts = [file_name]
    if class_name:
        parts.append(class_name)
    parts.append(f"{func.__name__}()")  # type: ignore[attr-defined]
    return " | ".join(parts)


def bound_logger_for_call(
    factory: LoggerFactory, func: object, args: tuple
) -> BoundLogger:
    """
    Build a `BoundLogger` for the current call, with `context` set to
    `file | ClassName.method()`.
    """
    return factory.get_logger().bind(context=build_context_string(func, args))
