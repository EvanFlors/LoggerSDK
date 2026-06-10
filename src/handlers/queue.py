from __future__ import annotations

import logging
import logging.handlers
import queue as _queue

from config import LoggerConfig, QueueSettings
from core.filters import OverflowFilter


def build_queue_pipeline(cfg: LoggerConfig, sinks: list[logging.Handler]):
    qcfg: QueueSettings = cfg.queue
    q: _queue.Queue = _queue.Queue(maxsize=qcfg.capacity)
    listener = logging.handlers.QueueListener(q, *sinks, respect_handler_level=True)

    def _size() -> int:
        return q.qsize()
    _size.capacity = qcfg.capacity  # type: ignore[attr-defined]

    qh = logging.handlers.QueueHandler(q)
    qh.addFilter(OverflowFilter(_size, qcfg.overflow))
    return qh, listener
