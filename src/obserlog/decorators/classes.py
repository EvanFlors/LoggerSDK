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


def class_log(*, show_args: bool = True, show_result: bool = True) -> Callable[..., Any]:
    """Decorator factory. See module docstring for behavior."""

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
            wrapped = function_log(show_args=show_args, show_result=show_result)(func)
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
