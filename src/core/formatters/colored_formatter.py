"""
Colored console formatter. Two variants:
- with colors (default, for terminals that support ANSI)
- without colors (for piped / captured output)
"""
from __future__ import annotations

import json
import logging
from typing import Any

from colorlog import ColoredFormatter

from src.core.formatters.json_formatter import _RESERVED

_BASE = "[%(asctime)s] [%(levelname)s] [%(name)s] [%(context)s] %(extras)s - %(message)s"
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
        # fmt = ("%(log_color)s" + _BASE + "%(reset)s") if use_colors else _BASE
        fmt = ("%(log_color)s[%(asctime)s] [%(levelname)s]%(reset)s [%(name)s] [%(context)s]%(extras)s - %(message)s") if use_colors else _BASE

        super().__init__(
            fmt=fmt,
            datefmt=date_format,
            log_colors=_LOG_COLORS if use_colors else {},
            reset=True,
        )

    def format(self, record: logging.LogRecord) -> str:
        # The format string uses `%(context)s`. If the record doesn't
        # have a `context` attribute (e.g. a plain stdlib log call that
        # bypasses BoundLogger), fall back to a placeholder so the line
        # still renders.
        if not hasattr(record, "context"):
            record.context = "<no-context>"
        extras: dict[str, Any] = {
            k: v for k, v in record.__dict__.items()
            if k not in _RESERVED
            and k not in ("context", "trace_id", "span_id")
        }
        record.extras = (
            " | extras=" + json.dumps(extras, default=str) if extras else ""
        )
        return super().format(record)
