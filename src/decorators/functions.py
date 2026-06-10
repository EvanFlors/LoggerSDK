from __future__ import annotations

import functools
import inspect
import json
import time
import traceback
from collections.abc import Callable
from typing import Any

from core.context import BoundLogger


def function_log(*, show_args: bool = True, show_result: bool = True) -> Callable:
    """
    Decorator factory. Uses a factory-bound logger captured from the call site
    via `factory.get_logger().bind(context)`. Falls back to stdlib root if no
    factory is active.
    """

    def decorator(func: Callable) -> Callable:
        sig = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            factory = _active_factory()
            if factory is None:
                return func(*args, **kwargs)
            logger = _bind_for_call(factory, func, args)
            start = time.perf_counter()
            try:
                if show_args:
                    logger.info(
                        f"Executing {func.__name__}",
                        extra={"type": "Execution",
                               "cur_args": _safe(args), "cur_kwargs": _safe(kwargs)},
                    )
                else:
                    logger.info("Executing function", extra={"type": "Execution"})
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                if show_result:
                    logger.info(
                        f"Finished {func.__name__} in {elapsed:.4f}s",
                        extra={"type": "Result", "result": _safe(result)},
                    )
                else:
                    logger.info(f"Finished in {elapsed:.4f}s", extra={"type": "Result"})
                return result
            except Exception as exc:
                logger.error(
                    f"Exception: {exc}",
                    extra={"type": "Error", "exception": traceback.format_exc(limit=3)},
                )
                raise

        return wrapper

    return decorator


# ----- helpers (imported from factory to avoid circulars) -----
_FACTORY_KEY = "_logger_factory"


def _active_factory():
    import logging
    return getattr(logging.getLogger(), _FACTORY_KEY, None)


def _bind_for_call(factory, func, args) -> BoundLogger:
    module = inspect.getmodule(func)
    file_name = module.__file__.rsplit("/", 1)[-1] if module and module.__file__ else "<unknown>"
    class_name = None
    if args and hasattr(args[0], "__class__"):
        class_name = args[0].__class__.__name__
    ctx_parts = [file_name]
    if class_name:
        ctx_parts.append(class_name)
    ctx_parts.append(f"{func.__name__}()")
    return factory.get_logger().bind(context=" | ".join(ctx_parts))


def _safe(obj: Any) -> Any:
    try:
        json.dumps(obj, default=str)
        return obj
    except Exception:
        return repr(obj)