from __future__ import annotations

import warnings
from collections.abc import Callable

from decorators.functions import function_log


def class_log(*, show_args: bool = True, show_result: bool = True) -> Callable:
    """
    Class decorator that wraps public callables (instance/class/static methods)
    with function_log. Skips __slots__-locked or frozen classes with a warning.
    """

    def decorator(cls: type) -> type:
        for name, value in list(cls.__dict__.items()):
            if name.startswith("_") or not callable(value):
                continue
            is_static = isinstance(value, staticmethod)
            is_class = isinstance(value, classmethod)
            func = value.__func__ if (is_static or is_class) else value
            wrapped = function_log(show_args=show_args, show_result=show_result)(func)
            try:
                if is_static:
                    setattr(cls, name, staticmethod(wrapped))
                elif is_class:
                    setattr(cls, name, classmethod(wrapped))
                else:
                    setattr(cls, name, wrapped)
            except (AttributeError, TypeError):
                warnings.warn(f"class_log: cannot wrap {cls.__name__}.{name}", RuntimeWarning, stacklevel=2)
        return cls

    return decorator
