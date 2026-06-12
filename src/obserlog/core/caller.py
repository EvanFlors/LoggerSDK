"""
Frame-walking caller resolution.

Walks back from the current frame to find the user's call site, skipping
the stdlib `logging` module and this package's own modules. Returns a
`CallerInfo` with the short file name, line number, function name, and a
qualified name like `MyClass.method`.

The result is *not* cached: the frame walk is cheap (a handful of
pointer hops) and the cache in earlier revisions was never read, only
written. We don't want a cache that drifts away from the actual call
site in long-lived processes.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from types import FrameType

# Names that always indicate stdlib internals. The frame walk stops at the
# first frame whose function name is not in this set and whose file is
# not in stdlib `logging/`.
_SKIP_NAMES: frozenset[str] = frozenset({
    "process", "_log", "log", "debug", "info", "warning", "warn",
    "error", "exception", "critical", "fatal", "emit", "handle",
    "callHandlers", "handleError", "findCaller", "_log_recursion_lock",
})

# Path substrings that identify stdlib `logging` (always skipped).
_SKIP_PATHS: tuple[str, ...] = ("/logging/__init__.py", "/logging/")

# Path substrings that identify this package (always skipped).
# Resolved at module load from the file's own path.
_THIS_PKG = os.path.dirname(os.path.abspath(__file__))
_SKIP_PATHS = (*_SKIP_PATHS, _THIS_PKG)


@dataclass(frozen=True)
class CallerInfo:
    file: str
    line: int
    func: str
    qualname: str

    def render(self) -> str:
        return f"{self.file}:{self.line} {self.qualname}()"

    def values(self) -> tuple:
        return (self.file, self.line, self.func, self.qualname)


def _class_from_frame(frame: FrameType) -> str | None:
    self_obj = frame.f_locals.get("self")
    if self_obj is not None and hasattr(self_obj, "__class__"):
        cls = self_obj.__class__
        # The frame's `self` may be a class itself (classmethod) — keep
        # its own name rather than the metaclass.
        return cls.__name__
    cls = frame.f_locals.get("cls")
    if isinstance(cls, type):
        return cls.__name__
    return None


def _is_skippable(file_name: str, func_name: str) -> bool:
    if any(p in file_name for p in _SKIP_PATHS):
        return True
    if func_name in _SKIP_NAMES:
        return True
    return bool(func_name.startswith("_"))


def resolve_caller() -> CallerInfo:
    """
    Walk back from this function's caller to the first user frame.
    Always returns a `CallerInfo`; never raises.
    """
    try:
        frame: FrameType | None = sys._getframe(1)
        while frame is not None:
            code = frame.f_code
            file_name = code.co_filename.replace("\\", "/")
            func_name = code.co_name
            short = os.path.basename(file_name)
            if not _is_skippable(file_name, func_name):
                class_name = _class_from_frame(frame)
                qualname = f"{class_name}.{func_name}" if class_name else func_name
                return CallerInfo(
                    file=short, line=frame.f_lineno, func=func_name, qualname=qualname
                )
            frame = frame.f_back
        return CallerInfo(file="unknown", line=0, func="unknown", qualname="unknown")
    except Exception:
        return CallerInfo(file="unknown", line=0, func="unknown", qualname="unknown")
