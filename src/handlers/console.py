from __future__ import annotations

import logging
import sys

from colorlog import ColoredFormatter

from config import LoggerConfig


def make_console_handler(cfg: LoggerConfig) -> logging.Handler:
    stream = sys.stdout if cfg.console.destination == "stdout" else sys.stderr
    h = logging.StreamHandler(stream)
    h.setLevel(cfg.numeric_level())
    fmt = ColoredFormatter(
        fmt="%(log_color)s[%(asctime)s] [%(levelname)s] [%(name)s] [%(context)s]%(reset)s - %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG": "cyan", "INFO": "green", "WARNING": "yellow",
            "ERROR": "red", "CRITICAL": "bold_red",
        },
        reset=True,
    ) if cfg.console.colors else logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s] [%(context)s] - %(message)s",
        datefmt="%H:%M:%S",
    )
    h.setFormatter(fmt)
    return h