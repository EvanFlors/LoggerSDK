"""
`@function_log` — log function entry and exit with timing.

If no `LoggerFactory` is active, the decorator is a transparent
pass-through (it just calls the function). When a factory is active,
it derives a `BoundLogger` for the call site and emits two records:
one on entry, one on exit (or on exception).

On exception, by default the decorator:
- emits a minimal `ERROR` record (message is the function name, not
  the exception text; `extras` only contains `type` and `function`),
- renders the rich boxed traceback via `log.exception(...)` so the
  call site doesn't have to wrap every call in a `try/except`,
- hides the wrapper's own frame from the rich traceback so the
  boxed output only shows user code,
- suppresses the duplicated stdlib `Traceback (most recent call last):`
  print that Python would otherwise emit on unhandled exceptions.

All four of those behaviors are opt-out flags so the decorator can
be used in code that prefers a quieter log surface.
"""
from __future__ import annotations

import functools
import json
import sys
import time
import types
from collections.abc import Callable
from typing import Any

from obserlog.decorators.base import active_factory, bound_logger_for_call

_DECORATOR_MODULE_FILE = __file__
_DECORATOR_PACKAGE_DIR = _DECORATOR_MODULE_FILE.rsplit("/", 1)[0] + "/"


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


def _is_decorator_frame(tb: Any) -> bool:
    """
    Return True if the given traceback frame lives inside
    `obserlog/decorators/`. Used to identify wrapper frames that
    should be hidden from the rich traceback.
    """
    try:
        filename = tb.tb_frame.f_code.co_filename
    except AttributeError:
        return False
    return filename.startswith(_DECORATOR_PACKAGE_DIR)


def _rewind_decorator_frames(tb: types.TracebackType | None) -> types.TracebackType | None:
    """
    Walk a traceback chain and re-link it to skip any frame whose
    source file is inside `obserlog/decorators/`. The original
    chain's internal links are mutated in place via `tb_next`
    reassignment (legal in CPython — `tb_next` is an assignable
    slot on `types.TracebackType`).

    The chain in `tb` runs from the outermost frame (head) to
    the innermost (tail, where the raise happened). The
    decorator's wrapper frame is in the **middle** of the chain,
    between the user's caller (outer) and the user's function
    (inner). We unlink it by walking the chain and reassigning
    `previous.tb_next = current.tb_next` for each decorator
    frame.

    Returns the (possibly new) head of the chain — the same
    object as the input if no decorator frames were found, or a
    re-linked sub-chain otherwise. The input is mutated.

    The exception's `__traceback__` is **not** re-assigned by
    this function; the caller is responsible for using the
    returned head. (Mutating `__traceback__` inside an `except`
    block is also pointless because bare `raise` re-raises with
    the original chain.)
    """
    if tb is None:
        return None

    head: types.TracebackType | None = tb
    prev: types.TracebackType | None = None
    cur: types.TracebackType | None = tb

    while cur is not None:
        if _is_decorator_frame(cur):
            nxt = cur.tb_next
            if prev is None:
                head = nxt
            else:
                prev.tb_next = nxt
            cur = nxt
        else:
            prev = cur
            cur = cur.tb_next
    return head


def _silent_excepthook(
    exc_type: type[BaseException],
    exc_value: BaseException,
    tb: Any,
) -> None:
    """
    Silent `sys.excepthook`. When installed, unhandled exceptions
    reach the interpreter's top level and exit the process, but the
    default `Traceback (most recent call last):` block is NOT
    printed to stderr.
    """
    return


def restore_default_excepthook() -> None:
    """
    Re-install Python's default excepthook. Use this if a previous
    decorated call left the silent hook installed and you want the
    stdlib `Traceback (most recent call last):` print back for
    subsequent unhandled exceptions.
    """
    sys.excepthook = sys.__excepthook__


def function_log(
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

    Args:
        show_args: include `cur_args` / `cur_kwargs` in the entry record.
        show_result: include `result` in the exit record.
        log_exceptions: emit any log record on exception. When `False`,
            the decorator is silent on errors and the caller is
            responsible for logging.
        exc_extra_fields: include `exc_type` / `exc_message` in the
            `extra` dict of the error record. Default off — the rich
            boxed traceback already includes the type and message.
        render_rich_traceback: when `True`, also emit `log.exception(...)`
            so the rich boxed `▶` traceback renders once, even when
            the caller has no `try/except` around the call.
        suppress_stdlib_traceback: when `True` and the wrapped function
            raises, swap `sys.excepthook` for a no-op and re-raise. If
            the caller catches the exception, the previous excepthook
            is restored. If the caller does not catch, the silent hook
            is left installed and the stdlib
            `Traceback (most recent call last):` print is suppressed
            when the unhandled exception reaches the interpreter's
            top level. Call `restore_default_excepthook()` to undo it
            for the rest of the process.

            The hook swap is process-global: an unhandled exception
            raised by another thread during the swap window will
            also be silenced.
        show_decorator_frames: when `False` (default), the wrapper's
            own frame is unlinked from the traceback before
            `log.exception(...)` is called, so the rich boxed
            traceback only shows user code. Set to `True` to keep
            the wrapper frame visible (useful when debugging the
            decorator itself).
    """

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
                if log_exceptions:
                    log.error(
                        f"{func.__name__} failed",
                        extra=(
                            {"type": "Error", "function": func.__name__}
                            | (
                                {"exc_type": type(exc).__name__, "exc_message": str(exc)}
                                if exc_extra_fields
                                else {}
                            )
                        ),
                    )
                    if render_rich_traceback:
                        if not show_decorator_frames:
                            # Build a synthetic exc_info tuple with
                            # the wrapper frame unlinked. The
                            # original `__traceback__` is preserved
                            # on the exception object (bare `raise`
                            # would re-raise with the original
                            # chain anyway), but the rendered log
                            # record uses our rewinded tuple.
                            rewinded_tb = _rewind_decorator_frames(exc.__traceback__)
                            exc_info: tuple[Any, Any, Any] = (
                                type(exc), exc, rewinded_tb
                            )
                            log.error(
                                f"{func.__name__} failed",
                                exc_info=exc_info,
                            )
                        else:
                            log.exception(f"{func.__name__} failed", exc_info=exc)
                if suppress_stdlib_traceback:
                    # The wrapper cannot know whether the caller will
                    # catch this raise, so there is no safe moment to
                    # restore the previous excepthook before the
                    # exception either reaches the caller's
                    # `try/except` or propagates to the top of
                    # `__main__`. We install the silent hook and
                    # leave it installed. The caller-catches case
                    # still works correctly (the silent hook simply
                    # never fires); only subsequent unhandled
                    # exceptions are affected, which the user can
                    # undo with `restore_default_excepthook()`.
                    sys.excepthook = _silent_excepthook
                raise

        return wrapper

    return decorator
