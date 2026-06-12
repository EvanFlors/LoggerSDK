"""
DI entrypoint for the logger.

`LoggerFactory` owns the root `logging.Logger`, the queue pipeline, and
the lifecycle. It publishes itself to `factory.registry` so the
decorators can find it from any module.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
from contextlib import asynccontextmanager
from typing import Any

from obserlog.config import LoggerConfig
from obserlog.core.context import BoundLogger
from obserlog.core.tracer import Tracer
from obserlog.errors import ShutdownError
from obserlog.factory.builder import build_handlers
from obserlog.factory.registry import publish, withdraw


class LoggerFactory:
    """
    Construct once with a `LoggerConfig`, call `get_logger()`, and call
    `shutdown()` (or use the `with` form) at the end of the process.
    """

    _queue_handler: logging.Handler | None
    _listener: logging.handlers.QueueListener | None

    def __init__(self, config: LoggerConfig | None = None) -> None:
        self._config = config or LoggerConfig()
        self._shutdown = False
        self._lock = threading.Lock()
        self._queue_handler = None
        self._listener = None
        self.tracer = Tracer(self._config.otel)

        self._root = logging.getLogger(self._config.service_name)
        self._root.setLevel(self._config.numeric_level())
        self._root.propagate = False

        # Per-module log levels.
        for mod, lvl in self._config.module_levels.items():
            logging.getLogger(mod).setLevel(lvl.upper())

        # Build the handler plan, attach the immediate (console) handler
        # directly, and start the queue listener for the deferred sinks.
        plan = build_handlers(self._config)
        for h in plan.immediate:
            self._root.addHandler(h)
        if plan.queue is not None:
            qh, listener = plan.queue
            self._queue_handler = qh
            self._listener = listener
            self._root.addHandler(qh)
            listener.start()

        # Make ourselves discoverable to `@function_log` / `@class_log`.
        publish(self)

    # ----- public API ----------------------------------------------------
    def get_logger(self) -> BoundLogger:
        if self._shutdown:
            raise ShutdownError("LoggerFactory is shut down")
        return BoundLogger(self._root, {}, self.tracer)

    def bind(self, **fields: Any) -> BoundLogger:
        return self.get_logger().bind(**fields)

    def flush(self, timeout: float = 5.0) -> None:
        """
        Drain the in-memory queue and flush every handler synchronously.
        Idempotent. Useful for tests and for ensuring records hit their
        sinks before process exit.
        """
        for h in list(self._root.handlers):
            flush_sync = getattr(h, "flush_sync", None)
            if callable(flush_sync):
                try:
                    flush_sync(timeout=timeout)
                except Exception as e:
                    sys.stderr.write(
                        f"[logger] handler {type(h).__name__} flush failed: {e}\n"
                    )
            else:
                try:
                    h.flush()
                except Exception as e:
                    sys.stderr.write(
                        f"[logger] handler {type(h).__name__} flush failed: {e}\n"
                    )

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
                except Exception as e:
                    sys.stderr.write(
                        f"[logger] handler {type(h).__name__} close failed: {e}\n"
                    )
                self._root.removeHandler(h)
            withdraw(self)

    # ----- context managers ---------------------------------------------
    def __enter__(self) -> LoggerFactory:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.shutdown()

    @asynccontextmanager
    async def lifecycle(self):
        try:
            yield self
        finally:
            self.shutdown()
