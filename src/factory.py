from __future__ import annotations

import logging
import sys
import threading
from contextlib import asynccontextmanager
from typing import Any

from config import LoggerConfig
from core.context import BoundLogger
from core.tracer import Tracer
from exceptions import LoggerShutdownError
from handlers.console import make_console_handler
from handlers.queue import build_queue_pipeline
from handlers.rotating_file import make_rotating_file_handler


class LoggerFactory:
    """
    DI entrypoint. Construct once with a LoggerConfig, call get_logger(), shutdown() at end.
    """

    def __init__(self, config: LoggerConfig | None = None) -> None:
        self._config = config or LoggerConfig()
        self._shutdown = False
        self._lock = threading.Lock()
        self.tracer = Tracer(self._config.otel)

        self._root = logging.getLogger(self._config.service_name)
        self._root.setLevel(self._config.numeric_level())
        self._root.propagate = False

        # per-module levels
        for mod, lvl in self._config.module_levels.items():
            logging.getLogger(mod).setLevel(logging.getLevelName(lvl.upper()))

        # console (direct, never queued)
        if self._config.console.enabled:
            self._root.addHandler(make_console_handler(self._config))

        # queue + listeners
        sinks: list[logging.Handler] = []
        if self._config.directory and not self._config.amqp:
            sinks.append(self._make_sink_from_config(self._config))

        if self._config.amqp:
            try:
                from handlers.amqp import make_amqp_handler
                sinks.append(make_amqp_handler(self._config.amqp))
            except Exception as e:
                if not self._config.amqp.fail_open:
                    raise
                sys.stderr.write(f"[logger] AMQP disabled: {e}\n")

        if sinks:
            qh, listener = build_queue_pipeline(self._config, sinks)
            self._queue_handler = qh
            self._listener = listener
            self._root.addHandler(qh)
            listener.start()
        else:
            self._queue_handler = None
            self._listener = None

    # ------------------------------------------------------------------
    def _make_sink_from_config(self, cfg: LoggerConfig) -> logging.Handler:
        if cfg.rotation is not None:
            return make_rotating_file_handler(cfg)
        return make_rotating_file_handler(cfg)  # default-rotating fallback

    # ------------------------------------------------------------------
    def get_logger(self) -> BoundLogger:
        if self._shutdown:
            raise LoggerShutdownError("LoggerFactory is shut down")
        return BoundLogger(self._root, {}, self.tracer)

    def bind(self, **fields: Any) -> BoundLogger:
        return self.get_logger().bind(**fields)

    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
            if self._listener is not None:
                self._listener.stop()
            for h in list(self._root.handlers):
                try:
                    h.close()
                except Exception:
                    pass
                self._root.removeHandler(h)

    @asynccontextmanager
    async def lifecycle(self):
        try:
            yield self
        finally:
            self.shutdown()