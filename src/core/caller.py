from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from types import FrameType

_SKIP_NAMES = {
    "process",
    "_log",
    "emit",
    "handle",
    "callHandlers",
    "handleError",
    "findCaller",
    "_log_recursion_lock"
}

_FRAME_CACHE: dict[tuple[str, str], int] = {}

@dataclass(frozen=True)
class CallerInfo:
    file: str
    line: int
    func: str
    qualname: str

    def render(self) -> str:
        return f"{self.file}:{self.line} {self.func}()"

def _class_from_frame(frame: FrameType) -> str | None:
    self_obj = frame.f_locals.get("self")
    if self_obj is not None and hasattr(self_obj, "__class__"):
        return self_obj.__class__.__name__
    cls = frame.f_locals.get("cls")

    if isinstance(cls, type):
        return cls.__name__

    return None

def resolve_caller(skip_modules: set[str] | None = None) -> CallerInfo:
    skip_modules = skip_modules or set()

    try:
        frame: FrameType = sys._getframe(1)
        while frame is not None:
            code = frame.f_code
            file_name = code.co_filename.replace("\\", "/")
            func_name = code.co_name
            short_file_name = os.path.basename(file_name)
            cache_key = (short_file_name, func_name)

            if cache_key in _FRAME_CACHE:
                frame = frame.f_back
                continue

            if any(s in file_name for s in skip_modules) or func_name in _SKIP_NAMES:
                frame = frame.f_back
                continue

            if func_name in _SKIP_NAMES or func_name.startswith("_"):
                frame = frame.f_back
                continue

            class_name = _class_from_frame(frame)
            qualname = f"{class_name}.{func_name}" if class_name else func_name
            return CallerInfo(file=short_file_name, line=frame.f_lineno, func=func_name, qualname=qualname)

        return CallerInfo(file="unknown", line=0, func="unknown", qualname="unknown")
    except Exception:
        return CallerInfo(file="unknown", line=0, func="unknown", qualname="unknown")