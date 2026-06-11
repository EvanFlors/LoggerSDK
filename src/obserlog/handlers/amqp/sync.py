"""
Sync AMQP handler (pika). Use this from workers, scripts, and CLIs that
are not already running inside an asyncio program. Safe in any context;
the publishing happens on the caller's thread, batched + serialized.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Any

from obserlog.config import AMQPSettings
from obserlog.errors import AMQPError
from obserlog.handlers.amqp.common import serialize_record, validate_settings


class AMQPSyncHandler(logging.Handler):
    """
    Blocking-connection (`pika`) AMQP handler. One connection per process;
    one in-memory buffer guarded by a `threading.Lock`.

    Thread-safety: emit() is safe to call from any thread.
    """

    def __init__(self, settings: AMQPSettings) -> None:
        super().__init__()
        validate_settings(settings)
        self._settings = settings
        self._buffer: list[bytes] = []
        self._lock = threading.Lock()
        self._conn: Any = None
        self._chan: Any = None
        self._last_flush = time.monotonic()
        self._closed = False
        self._connect()

    # ----- connection ----------------------------------------------------
    def _connect(self) -> None:
        try:
            import pika
        except ImportError as e:
            raise AMQPError("install 'pika' (logger[amqp])") from e
        params = pika.URLParameters(self._settings.url)
        params.socket_timeout = self._settings.connect_timeout_s
        self._conn = pika.BlockingConnection(params)
        self._chan = self._conn.channel()
        self._chan.exchange_declare(
            exchange=self._settings.exchange,
            exchange_type=self._settings.exchange_type,
            durable=self._settings.durable,
        )
        if self._settings.queue:
            self._chan.queue_declare(queue=self._settings.queue, durable=self._settings.durable)
            self._chan.queue_bind(
                queue=self._settings.queue,
                exchange=self._settings.exchange,
                routing_key=self._settings.routing_key,
            )

    # ----- emit / flush --------------------------------------------------
    def emit(self, record: logging.LogRecord) -> None:
        if self._closed:
            return
        payload = serialize_record(record) + b"\n"
        with self._lock:
            self._buffer.append(payload)
            if (
                len(self._buffer) >= self._settings.batch_size
                or (time.monotonic() - self._last_flush) >= self._settings.flush_interval_s
            ):
                self._flush_locked()

    def _flush_locked(self) -> None:
        if not self._buffer or self._chan is None:
            return
        try:
            for msg in self._buffer:
                self._chan.basic_publish(
                    exchange=self._settings.exchange,
                    routing_key=self._settings.routing_key,
                    body=msg,
                    properties=None,
                )
            self._buffer.clear()
            self._last_flush = time.monotonic()
        except Exception as e:
            if not self._settings.fail_open:
                raise
            sys.stderr.write(f"[logger] AMQP sync flush failed: {e}\n")
            self._buffer.clear()

    def flush(self) -> None:
        if self._closed:
            return
        with self._lock:
            self._flush_locked()

    # ----- close ---------------------------------------------------------
    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.flush()
            if self._conn is not None and self._conn.is_open:
                self._conn.close()
        except Exception as e:
            sys.stderr.write(f"[logger] AMQP sync close failed: {e}\n")
        finally:
            super().close()
