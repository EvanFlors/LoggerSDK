from __future__ import annotations

import asyncio
import json
import logging
import threading
import time

from config import AMQPSettings
from exceptions import AMQPConnectError

_SENTINEL = object()


class _AMQPCommon:
    def _serialize(self, record: logging.LogRecord) -> bytes:
        try:
            return (self.format(record) if hasattr(self, "format") else
                    json.dumps({
                        "message": record.getMessage(),
                        "level": record.levelname,
                        "logger": record.name,
                        "trace_id": getattr(record, "trace_id", None),
                        "span_id": getattr(record, "span_id", None),
                        "context": getattr(record, "context", None),
                    }, default=str).encode("utf-8") + b"\n")
        except Exception as e:
            return json.dumps({"error": str(e), "level": "ERROR"}).encode("utf-8") + b"\n"


class AMQPSyncHandler(_AMQPCommon, logging.Handler):
    def __init__(self, settings: AMQPSettings) -> None:
        super().__init__()
        self._settings = settings
        self._buffer: list[bytes] = []
        self._lock = threading.Lock()
        self._conn = None
        self._chan = None
        self._last_flush = time.time()
        self._connect()

    def _connect(self) -> None:
        try:
            import pika
        except ImportError as e:
            raise AMQPConnectError("install 'pika' (logger[amqp])") from e
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
            self._chan.queue_bind(queue=self._settings.queue,
                                  exchange=self._settings.exchange,
                                  routing_key=self._settings.routing_key)

    def emit(self, record: logging.LogRecord) -> None:
        payload = self._serialize(record)
        with self._lock:
            self._buffer.append(payload)
            if (len(self._buffer) >= self._settings.batch_size or
                    time.time() - self._last_flush >= self._settings.flush_interval_s):
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
            self._last_flush = time.time()
        except Exception as e:
            if not self._settings.fail_open:
                raise
            import sys
            sys.stderr.write(f"[logger] AMQP flush failed: {e}\n")
            self._buffer.clear()

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def close(self) -> None:
        try:
            self.flush()
            if self._conn is not None and self._conn.is_open:
                self._conn.close()
        finally:
            super().close()


class AMQPAsyncHandler(_AMQPCommon, logging.Handler):
    def __init__(self, settings: AMQPSettings, loop: asyncio.AbstractEventLoop | None = None) -> None:
        super().__init__()
        self._settings = settings
        self._buffer: list[bytes] = []
        self._lock = asyncio.Lock()
        self._loop = loop or asyncio.get_event_loop()
        self._conn = None
        self._chan = None
        self._connect_sync()

    def _connect_sync(self) -> None:
        try:
            import aio_pika
        except ImportError as e:
            raise AMQPConnectError("install 'aio-pika' (logger[amqp])") from e
        async def _do():
            self._conn = await aio_pika.connect_robust(self._settings.url, timeout=self._settings.connect_timeout_s)
            self._chan = await self._conn.channel()
            await self._chan.declare_exchange(
                self._settings.exchange, type=self._settings.exchange_type,
                durable=self._settings.durable,
            )
        asyncio.run_coroutine_threadsafe(_do(), self._loop).result(timeout=self._settings.connect_timeout_s)

    def emit(self, record: logging.LogRecord) -> None:
        payload = self._serialize(record)
        async def _do():
            async with self._lock:
                self._buffer.append(payload)
                if len(self._buffer) >= self._settings.batch_size:
                    await self._flush_locked()
        asyncio.run_coroutine_threadsafe(_do(), self._loop)

    async def _flush_locked(self) -> None:
        if not self._buffer or self._chan is None:
            return
        try:
            for msg in self._buffer:
                await self._chan.default_exchange.publish(
                    __import__("aio_pika").Message(body=msg),
                    routing_key=self._settings.routing_key,
                )
            self._buffer.clear()
        except Exception as e:
            if not self._settings.fail_open:
                raise
            import sys
            sys.stderr.write(f"[logger] AMQP async flush failed: {e}\n")
            self._buffer.clear()

    async def flush(self) -> None:
        async with self._lock:
            await self._flush_locked()

    def close(self) -> None:
        try:
            asyncio.run_coroutine_threadsafe(self.flush(), self._loop).result(timeout=5.0)
        finally:
            super().close()


def make_amqp_handler(settings: AMQPSettings) -> logging.Handler:
    if settings.transport == "async":
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        return AMQPAsyncHandler(settings, loop=loop)
    return AMQPSyncHandler(settings)