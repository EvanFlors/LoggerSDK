"""
`@class_log` — apply `@function_log` to every public callable on a class
(instance methods, classmethods, staticmethods).
"""
from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import Any

from obserlog.decorators.base import active_factory
from obserlog.decorators.functions import function_log


def _unwrap(value: object) -> tuple[object, bool, bool]:
    """
    Unwrap a class attribute to its underlying function, returning
    `(func, is_static, is_class)`.
    """
    is_static = isinstance(value, staticmethod)
    is_class = isinstance(value, classmethod)
    if is_static or is_class:
        return value.__func__, is_static, is_class  # type: ignore[attr-defined]
    if callable(value):
        return value, False, False
    return None, False, False


def class_log(
    *,
    show_args: bool = True,
    show_result: bool = True,
    log_exceptions: bool = True,
    exc_extra_fields: bool = False,
    render_rich_traceback: bool = True,
    suppress_stdlib_traceback: bool = True,
    show_decorator_frames: bool = False,
) -> Callable[..., Any]:
    """
    Decorator factory. See module docstring for behavior.

    Forwards the same exception-handling flags as `@function_log`
    to every method it wraps. See `function_log` for the meaning
    of each flag.
    """

    def decorator(cls: type) -> type:
        # If no factory is active there's nothing to do; the decorator
        # would just be a transparent pass-through anyway.
        if active_factory() is None:
            return cls
        for name, value in list(cls.__dict__.items()):
            if name.startswith("_"):
                continue
            func, is_static, is_class = _unwrap(value)
            if func is None:
                continue
            wrapped = function_log(
                show_args=show_args,
                show_result=show_result,
                log_exceptions=log_exceptions,
                exc_extra_fields=exc_extra_fields,
                render_rich_traceback=render_rich_traceback,
                suppress_stdlib_traceback=suppress_stdlib_traceback,
                show_decorator_frames=show_decorator_frames,
            )(func)
            try:
                if is_static:
                    setattr(cls, name, staticmethod(wrapped))
                elif is_class:
                    setattr(cls, name, classmethod(wrapped))
                else:
                    setattr(cls, name, wrapped)
            except (AttributeError, TypeError) as e:
                warnings.warn(
                    f"class_log: cannot wrap {cls.__name__}.{name}: {e}",
                    RuntimeWarning,
                    stacklevel=2,
                )
        return cls

    return decorator
