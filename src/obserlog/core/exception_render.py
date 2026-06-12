"""
Rich exception rendering for the `Logger` library.

Two renderers:

- `format_exception_structured(exc_info) -> dict`
  Returns a JSON-serializable dict with `type`, `message`, and a
  list of frames (each with `file`, `line`, `function`, `source`,
  `locals`). Used by `JSONFormatter`.

- `format_exception_pretty(exc_info, *, color=True) -> str`
  Returns a colorized, box-drawn terminal string that mirrors the
  `structlog` `RichTracebackFormatter` style. Used by
  `ConsoleFormatter`.

Both renderers fall back to plain `traceback.format_exception` if
anything goes wrong (e.g. the source file was deleted between run
time and log time). The user never sees a broken traceback.

The renderers are intentionally **synchronous** and **side-effect
free**: they walk the in-memory traceback object and read source
files via `linecache`. No I/O happens unless `linecache` decides
the file is no longer cached.
"""
from __future__ import annotations

import linecache
import sys
import traceback
from dataclasses import dataclass, field
from types import FrameType, TracebackType
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Public data model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Frame:
    file: str
    line: int
    function: str
    source: list[str] = field(default_factory=list)  # window of code lines
    locals: dict[str, Any] = field(default_factory=dict)  # filtered to user vars

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "function": self.function,
            "source": self.source,
            "locals": self.locals,
        }


@dataclass(frozen=True)
class ExceptionReport:
    type: str
    message: str
    frames: list[Frame]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "message": self.message,
            "frames": [f.to_dict() for f in self.frames],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# Local variables that are noise. We skip them in the "locals" block
# because they show up in every frame and are never the cause of a bug.
_DUNDER_OR_NOISE = (
    "__name__", "__doc__", "__package__", "__loader__", "__spec__",
    "__annotations__", "__builtins__", "__file__", "__cached__",
    "__class__", "__dict__", "__module__", "__qualname__",
    # Common stdlib module names that show up as "user vars" because
    # they were imported at the top of the file.
    "sys", "traceback", "logger", "log", "logging"
)


def _is_user_var(name: str, value: Any) -> bool:
    """Decide if a local variable is worth showing."""
    if name in _DUNDER_OR_NOISE:
        return False
    if name.startswith("__") and name.endswith("__"):
        return False
    # Skip modules, classes, and frame objects themselves.
    return not isinstance(value, type(sys))


def _safe_repr(value: Any, max_len: int = 120) -> str:
    """Render a value safely, truncated, no exceptions."""
    try:
        r = repr(value)
    except Exception as e:
        return f"<repr failed: {e.__class__.__name__}>"
    if len(r) > max_len:
        r = r[: max_len - 1] + "…"
    return r


def _read_source(filename: str, lineno: int, *, window: int = 3) -> list[str]:
    """
    Read up to `2*window+1` lines centered on `lineno`. Returns
    `["   5  def foo():", "   6      return bar", ...]` — formatted
    with the line number prefix. Empty if the file is unavailable.
    """
    if not filename or filename.startswith("<"):
        return []
    start = max(1, lineno - window)
    end = lineno + window
    out: list[str] = []
    for ln in range(start, end + 1):
        line = linecache.getline(filename, ln)
        if not line:
            continue
        out.append(f"{ln:>4}  {line.rstrip()}")
    return out


def _frame_locals(frame: FrameType) -> dict[str, Any]:
    """
    Extract a JSON-serializable view of the frame's locals.

    Filters out noise (dunder names, modules, classes) and replaces
    values with their string repr. The result is meant for
    human-readable rendering, not for restoring state.
    """
    result: dict[str, Any] = {}
    for k, v in frame.f_locals.items():
        if not _is_user_var(k, v):
            continue
        result[k] = _safe_repr(v)
    return result


# ---------------------------------------------------------------------------
# Structured (JSON-friendly) rendering
# ---------------------------------------------------------------------------
def _iter_frames_in_source_order(
    exc_type: type[BaseException],
    exc_val: BaseException,
    exc_tb: TracebackType | None,
) -> list[Frame]:
    """
    Walk the traceback chain and return frames in source order
    (root frame first, exception site last). Filters out frames
    that point to <stdin>, <console>, or other synthetic files
    that have no source code (but only if there are real frames
    to show; otherwise show them all).
    """
    if exc_tb is None:
        return []

    # Walk the traceback chain. CPython's `tb_next` walks the chain
    # in source-call order: outermost (root) first, innermost
    # (exception site) last. We keep that order.
    pairs: list[tuple[FrameType, int]] = []
    cur: TracebackType | None = exc_tb
    while cur is not None:
        pairs.append((cur.tb_frame, cur.tb_lineno))
        cur = cur.tb_next

    # Build the Frame objects.
    frames: list[Frame] = []
    for frame, lineno in pairs:
        filename = frame.f_code.co_filename or "<unknown>"
        function = frame.f_code.co_name or "<lambda>"
        frames.append(
            Frame(
                file=filename,
                line=lineno,
                function=function,
                source=_read_source(filename, lineno),
                locals=_frame_locals(frame),
            )
        )
    return frames


def format_exception_structured(
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None]
    | BaseException
    | None,
) -> dict[str, Any]:
    """
    Render an `exc_info` tuple (or a bare exception) as a JSON-friendly
    dict. Returns `{"type": ..., "message": ..., "frames": [...]}`.

    On any internal failure, falls back to a plain string traceback
    so the user never loses the error to a renderer bug.
    """
    try:
        if exc_info is None:
            return {"type": "None", "message": "", "frames": []}
        if isinstance(exc_info, BaseException):
            # Bare exception — synthesize an exc_info-like tuple.
            return _bare_exception_to_dict(exc_info)
        exc_type, exc_val, exc_tb = exc_info
        if exc_type is None or exc_val is None:
            return {"type": "None", "message": "", "frames": []}
        frames = _iter_frames_in_source_order(exc_type, exc_val, exc_tb)
        return {
            "type": exc_type.__name__,
            "message": str(exc_val),
            "frames": [f.to_dict() for f in frames],
        }
    except Exception as e:
        # Last-ditch fallback. Should never trigger in practice.
        return {
            "type": "RenderError",
            "message": f"rich exception render failed: {e}",
            "frames": [],
            "fallback": _plain_fallback(exc_info),
        }


def _bare_exception_to_dict(exc: BaseException) -> dict[str, Any]:
    """Render a bare exception (no traceback attached)."""
    return {
        "type": type(exc).__qualname__,
        "message": str(exc),
        "frames": [],
    }


def _plain_fallback(
    exc_info: Any,
) -> str:
    """Last-ditch: return the stdlib traceback as a single string."""
    try:
        if isinstance(exc_info, BaseException):
            return "".join(traceback.format_exception(type(exc_info), exc_info, exc_info.__traceback__))
        if exc_info is None:
            return ""
        # Validate: must be a 3-tuple of (type, value, tb). If the
        # caller passed garbage we return a string rather than raise.
        if not (isinstance(exc_info, tuple) and len(exc_info) == 3):
            return f"<unparseable exc_info: {exc_info!r}>"
        return "".join(traceback.format_exception(*exc_info))
    except Exception as e:
        return f"<traceback fallback failed: {e}>"


# ---------------------------------------------------------------------------
# Pretty (colorized terminal) rendering
# ---------------------------------------------------------------------------
# ANSI escape codes. Used only when `color=True`. The terminal's
# `NO_COLOR` env var is honored by the caller (see `format_exception_pretty`).
_BOLD_RED = "\x1b[1;31m"
_RED = "\x1b[31m"
_CYAN = "\x1b[36m"
_GREEN = "\x1b[32m"
_DIM = "\x1b[2m"
_BOLD_WHITE = "\x1b[1;37m"
_RESET = "\x1b[0m"


def _c(code: str, text: str, color: bool) -> str:
    return f"{code}{text}{_RESET}" if color else text


def format_exception_pretty(
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None]
    | BaseException
    | None,
    *,
    color: bool = True,
    show_locals: bool = True,
    max_frames: int | None = None,
) -> str:
    """
    Render an `exc_info` tuple (or a bare exception) as a multi-line
    colorized string ready to be written to a TTY.

    Layout:

        ┌─ Traceback (most recent call last) ──────────────────────┐
        │  File "/path/to/file.py", line 42, in make_invoice       │
        │    39  def make_invoice(order_id, amount):               │
        │    40      d = {"x": 42}                                 │
        │  ▶ 41      print(SomeClass(d["y"]))                      │
        │    42      return d                                      │
        │                                                          │
        │    locals:                                               │
        │      order_id = 'ord-00001'                              │
        │      amount   = 99.0                                     │
        └──────────────────────────────────────────────────────────┘
        KeyError: 'y'

    Args:
        exc_info: stdlib exc_info tuple, a bare exception, or None.
        color: enable ANSI color codes (set False when redirecting
            to a file).
        show_locals: include the locals block for each frame.
        max_frames: if set, only render the last N frames (useful
            for noisy test logs).

    Returns:
        A newline-terminated string. Never raises; falls back to
        `traceback.format_exception` on internal error.
    """
    try:
        if exc_info is None:
            return ""
        if isinstance(exc_info, BaseException):
            return _render_bare_exception(exc_info, color=color, show_locals=show_locals)
        exc_type, exc_val, exc_tb = exc_info
        if exc_type is None or exc_val is None:
            return ""

        # Re-walk in source order.
        frames = _iter_frames_in_source_order(exc_type, exc_val, exc_tb)
        if max_frames is not None and len(frames) > max_frames:
            skipped = len(frames) - max_frames
            frames = frames[-max_frames:]
        else:
            skipped = 0

        lines: list[str] = []
        # Header line. The boxed form (`┌─ ... ─...─┐`) was removed;
        # the renderer now emits a plain colored header for legibility
        # alongside the source-context lines below.
        header = "Traceback (most recent call last)"
        if skipped > 0:
            header += f"  [skipped {skipped} earlier frame(s)]"
        lines.append(
            _c(
                _BOLD_RED,
                f"{header}",
                color,
            )
        )

        for f in frames:
            _render_frame(lines, f, color=color, show_locals=show_locals)

        # The exception type and message on its own line.
        type_msg = f"{exc_type.__name__}: {exc_val}"
        lines.append(_c(_BOLD_RED, f"{type_msg}", color))

        return "\n".join(lines) + "\n"
    except Exception:
        # Absolute last resort: never let the renderer crash the log call.
        return _plain_fallback(exc_info)


def _render_bare_exception(
    exc: BaseException, *, color: bool, show_locals: bool
) -> str:
    """Render a bare exception (no traceback)."""
    lines = [f"{type(exc).__qualname__}: {exc}"]
    tb = exc.__traceback__
    if tb is not None:
        frames = _iter_frames_in_source_order(type(exc), exc, tb)
        for f in frames:
            _render_frame(lines, f, color=color, show_locals=show_locals)
    return "\n".join(lines) + "\n"


def _render_frame(
    lines: list[str], frame: Frame, *, color: bool, show_locals: bool
) -> None:
    """Append the per-frame lines to `lines`."""
    frame.file.rsplit("/", 1)[-1] if "/" in frame.file else frame.file
    location = f'  File "{frame.file}", line {frame.line}, in {frame.function}'
    lines.append(_c(_DIM, location, color))

    # Source lines
    if frame.source:
        for src in frame.source:
            # Mark the offending line.
            try:
                line_num = int(src[:4].strip())
            except (ValueError, IndexError):
                line_num = -1
            is_offender = line_num == frame.line
            if is_offender:
                lines.append(_c(_BOLD_RED, f"  ▶  {src}", color))
            else:
                lines.append(_c(_DIM, f"     {src}", color))
    else:
        # No source available (e.g. <stdin>); show the line text.
        lines.append(_c(_DIM, "     (source unavailable)", color))

    # Locals block
    if show_locals and frame.locals:
        # Find the longest key for alignment.
        max_key = max(len(k) for k in frame.locals)
        for k, v in frame.locals.items():
            line = f"    {k.ljust(max_key)} = {_c(_GREEN, v, color)}"
            lines.append(_c(_CYAN, line, color))

    # Blank line between frames
    lines.append("")


# ---------------------------------------------------------------------------
# Public hook for `logging.Handler.formatException`
# ---------------------------------------------------------------------------
def rich_format_exception(
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None]
    | BaseException
    | None,
    *,
    style: Literal["structured", "pretty"] = "pretty",
    color: bool = True,
    show_locals: bool = True,
) -> str | dict[str, Any]:
    """
    Convenience entry point. Dispatches to the structured or pretty
    renderer based on `style`.

    Returns a `dict` for `style="structured"` (JSON-serializable)
    and a `str` for `style="pretty"`.
    """
    if style == "structured":
        return format_exception_structured(exc_info)
    return format_exception_pretty(
        exc_info, color=color, show_locals=show_locals
    )
