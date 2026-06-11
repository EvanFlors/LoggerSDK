"""
Build the in-memory `QueueHandler` + `QueueListener` pipeline that fronts
all non-console sinks.
"""
from __future__ import annotations

import logging
import logging.handlers
import queue as _queue

from obserlog.config import LoggerConfig
from obserlog.core.filters.overflow import OverflowFilter, QueueCapacityProbe


def build_queue_pipeline(
    cfg: LoggerConfig,
    sinks: list[logging.Handler],
) -> tuple[logging.Handler, logging.handlers.QueueListener]:
    """
    Returns `(queue_handler, listener)`. The caller is responsible for
    adding the queue handler to the root logger and starting the listener.
    """
    qcfg = cfg.queue
    q: _queue.Queue = _queue.Queue(maxsize=qcfg.capacity)
    listener = logging.handlers.QueueListener(q, *sinks, respect_handler_level=True)

    probe = QueueCapacityProbe(size_fn=q.qsize, capacity=qcfg.capacity)
    qh = logging.handlers.QueueHandler(q)
    qh.addFilter(OverflowFilter(probe, qcfg.overflow))
    return qh, listener
