"""
`@function_log` — log function entry and exit with timing.

If no `LoggerFactory` is active, the decorator is a transparent
pass-through (it just calls the function). When a factory is active,
it derives a `BoundLogger` for the call site and emits two records:
one on entry, one on exit (or on exception).
"""
from __future__ import annotations

import functools
import json
import time
import traceback
from collections.abc import Callable
from typing import Any

from src.decorators.base import active_factory, bound_logger_for_call


def _safe(obj: Any) -> Any:
    """
    Return `obj` if it's JSON-serializable (with a `default=str` fallback),
    else fall back to its `repr`. Used to make sure decorator-emitted
    `cur_args` / `result` extras never raise out of the emit path.
    """
    try:
        json.dumps(obj, default=str)
        return obj
    except Exception:
        return repr(obj)


def function_log(*, show_args: bool = True, show_result: bool = True) -> Callable[..., Any]:
    """Decorator factory. See module docstring for behavior."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            factory = active_factory()
            if factory is None:
                return func(*args, **kwargs)
            log = bound_logger_for_call(factory, func, args)
            start = time.perf_counter()
            try:
                if show_args:
                    log.info(
                        f"Executing {func.__name__}",
                        extra={
                            "type": "Execution",
                            "cur_args": _safe(args),
                            "cur_kwargs": _safe(kwargs),
                        },
                    )
                else:
                    log.info("Executing function", extra={"type": "Execution"})
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                if show_result:
                    log.info(
                        f"Finished {func.__name__} in {elapsed:.4f}s",
                        extra={"type": "Result", "result": _safe(result)},
                    )
                else:
                    log.info(f"Finished in {elapsed:.4f}s", extra={"type": "Result"})
                return result
            except Exception as exc:
                log.error(
                    f"Exception: {exc}",
                    extra={"type": "Error", "exception": traceback.format_exc(limit=3)},
                )
                raise

        return wrapper

    return decorator
