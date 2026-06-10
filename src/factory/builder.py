"""
Translate a `LoggerConfig` into a set of `logging.Handler` instances.

This is the only place that knows how to build handlers from config.
Splitting it out of the factory keeps the factory class focused on
lifecycle (init, get_logger, shutdown, context managers).
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from dataclasses import dataclass

from src.config import LoggerConfig
from src.handlers.console import make_console_handler
from src.handlers.queue import build_queue_pipeline
from src.handlers.rotating_file import make_rotating_file_handler


@dataclass
class HandlerPlan:
    """
    The result of `build_handlers`: which handlers attach to the root
    logger directly (the console, which is immediate) and which are
    served by the queue (file + AMQP).
    """

    immediate: list[logging.Handler]
    queue: tuple[logging.Handler, logging.handlers.QueueListener] | None


def build_handlers(config: LoggerConfig) -> HandlerPlan:
    """
    Build the full handler set for a given config. Never raises; AMQP
    failures are downgraded to a stderr warning + file-only when
    `fail_open=True` (the default).
    """
    immediate: list[logging.Handler] = []
    if config.console.enabled:
        immediate.append(make_console_handler(config))

    sinks: list[logging.Handler] = []
    # File sink: always added when `directory` is set, regardless of
    # whether AMQP is also configured. The two transports are
    # independent — the user may want both for redundancy, or
    # AMQP-only and accept that files are skipped.
    if config.directory:
        sinks.append(make_rotating_file_handler(config))

    if config.amqp:
        try:
            from src.handlers.amqp import make_amqp_handler
            sinks.append(make_amqp_handler(config.amqp))
        except Exception as e:
            if not config.amqp.fail_open:
                raise
            sys.stderr.write(f"[logger] AMQP disabled: {e}\n")

    queue = build_queue_pipeline(config, sinks) if sinks else None
    return HandlerPlan(immediate=immediate, queue=queue)
