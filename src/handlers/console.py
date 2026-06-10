"""
Colored console handler. Always immediate (never queued) so developers
see logs even if a sink is broken.
"""
from __future__ import annotations

import logging
import sys

from src.config import LoggerConfig
from src.core.formatters.colored_formatter import ConsoleFormatter


def make_console_handler(cfg: LoggerConfig) -> logging.Handler:
    stream = sys.stdout if cfg.console.destination == "stdout" else sys.stderr
    h = logging.StreamHandler(stream)
    h.setLevel(cfg.numeric_level())
    h.setFormatter(ConsoleFormatter(date_format="%H:%M:%S", use_colors=cfg.console.colors))
    return h
