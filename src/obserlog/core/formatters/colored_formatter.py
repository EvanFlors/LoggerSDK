"""
Colored console formatter. Two variants:
- with colors (default, for terminals that support ANSI)
- without colors (for piped / captured output)

On `exc_info` records, the exception is rendered as a rich, boxed
traceback (boxed header, source code with the offending line marked
by `▶`, and a `locals` block). The `NO_COLOR` env var is honored.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from colorlog import ColoredFormatter

from obserlog.core.exception_render import format_exception_pretty
from obserlog.core.formatters.json_formatter import _RESERVED

_BASE = (
    "[%(asctime)s] [%(levelname)s] [%(name)s] [%(context)s]"
    " [trace=%(trace_id)s span=%(span_id)s]"
    "%(extras)s - %(message)s"
)
_LOG_COLORS: dict[str, str] = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}


class ConsoleFormatter(ColoredFormatter):
    """Single source of truth for the colored console line format."""

    def __init__(self, date_format: str = "%H:%M:%S", use_colors: bool = True) -> None:
        # Honor NO_COLOR (https://no-color.org/).
        if "NO_COLOR" in os.environ and use_colors:
            use_colors = False

        fmt = (
            "%(log_color)s[%(asctime)s] [%(levelname)s]%(reset)s"
            " [%(name)s] [%(context)s]"
            " [trace=%(trace_id)s span=%(span_id)s]"
            "%(extras)s - %(message)s"
        ) if use_colors else _BASE

        # Save for formatException() — color use should match the
        # color use in the regular lines.
        self._use_colors = use_colors

        super().__init__(
            fmt=fmt,
            datefmt=date_format,
            log_colors=_LOG_COLORS if use_colors else {},
            reset=True,
        )

    def format(self, record: logging.LogRecord) -> str:
        # Guarantee custom fields exist so %(trace_id)s / %(span_id)s
        # never raise KeyError, even for plain stdlib log calls.
        if not hasattr(record, "context"):
            record.context = "<no-context>"
        if not hasattr(record, "trace_id"):
            record.trace_id = "0" * 32
        if not hasattr(record, "span_id"):
            record.span_id = "0" * 16
        extras: dict[str, Any] = {
            k: v for k, v in record.__dict__.items()
            if k not in _RESERVED
            and k not in ("context", "trace_id", "span_id")
        }
        record.extras = (
            " | extras=" + json.dumps(extras, default=str) if extras else ""
        )
        return super().format(record)

    def formatException(self, ei):  # type: ignore[override]
        """
        Rich, boxed, colorized exception rendering. See
        `src/core/exception_render.py` for the full design.
        """
        return format_exception_pretty(
            ei, color=self._use_colors, show_locals=True
        )
