"""
Async AMQP handler (aio-pika). Drives the connection from a dedicated
event loop (`LoopRunner`) and uses a single long-running consumer
coroutine + a sync `queue.SimpleQueue` to bridge from `emit()` (sync
caller) to AMQP (async broker).

The lifecycle is now straightforward:

    emit() ──> _inbox.put_nowait(payload)  ──> _wake_event.set()
                                                     │
                                                     ▼
                                              _consumer()
                                                ├─ drain inbox into buffer
                                                ├─ publish batch via aio_pika
                                                └─ if closing: final flush + return
                                                     │
                                                     ▼
                                            _drained_event.set() ◄─── _barrier
                                                     │
                                                     ▼
                                            flush_sync() returns
                                                     │
                                                     ▼
                                            consumer task completes
                                                     │
                                                     ▼
                                            close() closes conn, stops loop

There is exactly ONE pending coroutine in the loop at any time during
normal operation. close() never has to drain thousands of pending
coroutines because they don't exist.

A "drain barrier" (`_drained_event`) is set by the consumer after it
finishes publishing the current buffer. `flush_sync` waits on this event,
so callers see a true barrier that only fires once all currently-queued
records are on the wire.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import logging
import queue as _queue
import sys
from typing import Any

from src.config import AMQPSettings
from src.errors import AMQPError
from src.handlers.amqp.async_loop import LoopRunner
from src.handlers.amqp.common import serialize_record, validate_settings


def _observe_future(fut: concurrent.futures.Future) -> None:
    """
    Mark a `concurrent.futures.Future` as observed so Python's garbage
    collector doesn't print `Future exception was never retrieved` when
    the future is finalized with an unhandled exception or cancellation.

    The `concurrent.futures.Future` returned by `asyncio.run_coroutine_threadsafe`
    carries the coroutine's exception state. If the coroutine was cancelled
    by a loop shutdown, the future ends up in CANCELLED state with no
    `.result()` ever called on it — which would trigger the warning
    during finalization.
    """
    if not fut.done():
        return
    # Calling `.exception()` marks the future as observed even if we
    # don't actually re-raise. Returning a `BaseException` (e.g. from
    # a cancelled coroutine) without observing would otherwise trigger
    # the "Future exception was never retrieved" warning at GC time.
    with contextlib.suppress(BaseException):
        fut.exception()


class AMQPAsyncHandler(logging.Handler):
    """
    Async AMQP handler. Either attaches to an existing running loop
    (`loop=`) or owns a fresh loop in a daemon thread.
    """

    def __init__(
        self,
        settings: AMQPSettings,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        super().__init__()
        validate_settings(settings)
        self._settings = settings

        # Sync side: producer drops records here.
        self._inbox: _queue.SimpleQueue[bytes] = _queue.SimpleQueue()

        # Async side: connection + channel, populated in `_connect_async`.
        self._conn: Any = None
        self._chan: Any = None
        self._aio_pika: Any = None  # cached module reference

        # Lifecycle flags. `_closing` flips first (tells the consumer to
        # exit), `_closed` flips last (after the consumer is done).
        self._closing = False
        self._closed = False

        # Sync/async bridge: `_wake_event` is the producer→consumer signal.
        # `_drained_event` is the consumer→flush_sync signal. Both are
        # asyncio primitives created on the loop's thread.
        self._wake_event: asyncio.Event | None = None
        self._drained_event: asyncio.Event | None = None

        # Task handle for the consumer.
        self._consumer_task: asyncio.Task[None] | None = None

        # Loop ownership.
        self._external_loop = loop is not None
        self._runner: LoopRunner | None = None
        self._loop: asyncio.AbstractEventLoop
        if loop is not None:
            self._loop = loop
        else:
            self._runner = LoopRunner.start()
            assert self._runner.loop is not None
            self._loop = self._runner.loop

        # Synchronous connect via aio_pika (driven by a coroutine on the
        # loop), then bootstrap the consumer + barriers.
        self._connect()
        self._bootstrap_async_state()

    # =====================================================================
    # bootstrap
    # =====================================================================
    def _connect(self) -> None:
        """Connect to AMQP and declare the exchange. Sync wrapper around
        a coroutine that runs on the loop."""
        try:
            import aio_pika
        except ImportError as e:
            raise AMQPError("install 'aio-pika' (logger[amqp])") from e
        self._aio_pika = aio_pika

        async def _do() -> None:
            self._conn = await aio_pika.connect_robust(
                self._settings.url,
                timeout=self._settings.connect_timeout_s,
            )
            self._chan = await self._conn.channel()
            await self._chan.declare_exchange(
                self._settings.exchange,
                type=self._settings.exchange_type,
                durable=self._settings.durable,
            )

        assert self._loop is not None
        if self._external_loop:
            # We can't block on a loop that's currently running the calling
            # code, so we submit and wait asynchronously via run_coroutine_threadsafe.
            try:
                asyncio.run_coroutine_threadsafe(_do(), self._loop).result(
                    timeout=self._settings.connect_timeout_s
                )
            except Exception as e:
                raise AMQPError(f"AMQP async connect failed: {e}") from e
        else:
            # We own the loop; submit and wait.
            try:
                self._runner.submit(_do()).result(  # type: ignore[union-attr]
                    timeout=self._settings.connect_timeout_s
                )
            except Exception as e:
                raise AMQPError(f"AMQP async connect failed: {e}") from e

    def _bootstrap_async_state(self) -> None:
        """
        Create the asyncio events and the consumer task. Must run after
        the loop is up and the connection is open.
        """
        assert self._loop is not None

        async def _setup() -> None:
            self._wake_event = asyncio.Event()
            self._drained_event = asyncio.Event()
            self._drained_event.set()  # nothing pending yet
            self._consumer_task = asyncio.create_task(
                self._consumer(),
                name="amqp-async-consumer",
            )

        if self._external_loop:
            try:
                asyncio.run_coroutine_threadsafe(_setup(), self._loop).result(
                    timeout=2.0
                )
            except Exception as e:
                raise AMQPError(f"AMQP async bootstrap failed: {e}") from e
        else:
            self._runner.submit(_setup()).result(timeout=2.0)  # type: ignore[union-attr]

    # =====================================================================
    # producer side (sync, any thread)
    # =====================================================================
    def emit(self, record: logging.LogRecord) -> None:
        if self._closing or self._closed:
            return
        if self._loop is None or self._loop.is_closed():
            return
        payload = serialize_record(record) + b"\n"
        try:
            self._inbox.put_nowait(payload)
        except Exception:
            return
        # Wake the consumer (no-op if it's already running).
        if self._wake_event is not None:
            with contextlib.suppress(RuntimeError):
                self._loop.call_soon_threadsafe(self._wake_event.set)

    # =====================================================================
    # consumer (async, on the loop)
    # =====================================================================
    async def _consumer(self) -> None:
        """
        Long-running coroutine. The single point of execution on the
        AMQP loop. Reads from `_inbox`, batches, and publishes.
        """
        assert self._loop is not None
        assert self._wake_event is not None
        assert self._drained_event is not None

        buffer: list[bytes] = []
        try:
            while True:
                # Wait for new data or the wake-timeout.
                try:
                    await asyncio.wait_for(
                        self._wake_event.wait(),
                        timeout=self._settings.flush_interval_s,
                    )
                except asyncio.TimeoutError:
                    pass
                finally:
                    self._wake_event.clear()

                # Drain the inbox into the local buffer.
                while True:
                    try:
                        msg = self._inbox.get_nowait()
                    except Exception:
                        break
                    buffer.append(msg)

                # Publish if we have anything to say.
                if buffer:
                    await self._publish_buffer(buffer)

                # Signal anyone waiting in flush_sync that the current
                # backlog is on the wire.
                self._drained_event.set()

                if self._closing:
                    # One final drain, then exit.
                    while True:
                        try:
                            msg = self._inbox.get_nowait()
                        except Exception:
                            break
                        buffer.append(msg)
                    if buffer:
                        await self._publish_buffer(buffer)
                    self._drained_event.set()
                    return
        except asyncio.CancelledError:
            # Loop is being torn down. Best-effort flush of whatever's left.
            while True:
                try:
                    msg = self._inbox.get_nowait()
                except Exception:
                    break
                buffer.append(msg)
            if buffer:
                with contextlib.suppress(Exception):
                    await self._publish_buffer(buffer)
            if self._drained_event is not None:
                self._drained_event.set()
            raise

    async def _publish_buffer(self, buffer: list[bytes]) -> None:
        if not buffer or self._chan is None:
            buffer.clear()
            return
        try:
            for msg in buffer:
                await self._chan.default_exchange.publish(
                    self._aio_pika.Message(body=msg),
                    routing_key=self._settings.routing_key,
                )
        except Exception as e:
            if not self._settings.fail_open:
                raise
            sys.stderr.write(f"[logger] AMQP async publish failed: {e}\n")
        finally:
            buffer.clear()

    # =====================================================================
    # sync flush bridge
    # =====================================================================
    def flush(self) -> None:
        """Sync flush (required by stdlib)."""
        self.flush_sync(timeout=max(1.0, self._settings.flush_interval_s * 2))

    def flush_sync(self, timeout: float = 5.0) -> None:
        """
        Force the consumer to publish everything currently in the inbox,
        then wait for it to acknowledge via `_drained_event`.

        Safe to call from sync code (`factory.shutdown`, `atexit`,
        `QueueListener.stop`).
        """
        if self._closing or self._closed:
            return
        if self._loop is None or self._loop.is_closed():
            return
        if self._wake_event is None or self._drained_event is None:
            return

        # Clear the drained flag BEFORE waking the consumer, so the consumer
        # is guaranteed to set it on the next cycle even if a previous flush
        # already cleared it.
        async def _kick_and_wait() -> None:
            assert self._drained_event is not None
            assert self._wake_event is not None
            self._drained_event.clear()
            self._wake_event.set()

        # Submit the kick; then wait on the drain.
        # Catch BaseException here too: `CancelledError` is a BaseException,
        # and the loop can be cancelled mid-kick during shutdown.
        kick_future: concurrent.futures.Future | None = None
        try:
            if self._external_loop:
                kick_future = asyncio.run_coroutine_threadsafe(
                    _kick_and_wait(), self._loop
                )
                kick_future.result(timeout=2.0)
            else:
                kick_future = self._runner.submit(_kick_and_wait())  # type: ignore[union-attr]
                kick_future.result(timeout=2.0)
        except BaseException as e:
            # Suppress the kick failure. Mark the future as observed so
            # Python's GC doesn't print "Future exception was never
            # retrieved" when it cleans up.
            if kick_future is not None:
                _observe_future(kick_future)
            if not isinstance(e, asyncio.CancelledError):
                sys.stderr.write(f"[logger] AMQP async flush_sync kick failed: {e}\n")
            return

        # Now wait for the consumer to set the drain event.
        async def _await_drain() -> None:
            assert self._drained_event is not None
            # Don't re-raise TimeoutError: caller treats this as a soft
            # failure (the consumer may simply be slow).
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._drained_event.wait(), timeout=timeout)

        drain_future: concurrent.futures.Future | None = None
        try:
            if self._external_loop:
                drain_future = asyncio.run_coroutine_threadsafe(
                    _await_drain(), self._loop
                )
                drain_future.result(timeout=timeout + 1.0)
            else:
                drain_future = self._runner.submit(_await_drain())  # type: ignore[union-attr]
                drain_future.result(timeout=timeout + 1.0)
        except BaseException:
            # Suppress: CancelledError / RuntimeError here means the
            # loop is shutting down — close() is already in progress.
            # Mark the future as observed so the GC warning stays quiet.
            if drain_future is not None:
                _observe_future(drain_future)
            return

    # =====================================================================
    # close
    # =====================================================================
    def close(self) -> None:
        """
        Stop accepting emits, signal the consumer to drain and exit, close
        the aio_pika connection, then stop the loop (if we own it).

        Idempotent. Order matters: drain BEFORE closing the connection.
        """
        if self._closed:
            return
        self._closing = True

        # Tell the consumer to drain and exit.
        if self._wake_event is not None and self._loop is not None and not self._loop.is_closed():
            with contextlib.suppress(RuntimeError):
                self._loop.call_soon_threadsafe(self._wake_event.set)

        # Wait for the consumer to finish.
        if self._consumer_task is not None:
            if self._external_loop:
                consumer_future: concurrent.futures.Future | None = None
                with contextlib.suppress(BaseException):
                    # `run_coroutine_threadsafe` needs a coroutine, not a
                    # Future, so we wrap the shielded task in a coroutine.
                    async def _await_shield() -> None:
                        await asyncio.shield(self._consumer_task)  # type: ignore[arg-type]
                    consumer_future = asyncio.run_coroutine_threadsafe(
                        _await_shield(), self._loop
                    )
                    consumer_future.result(timeout=5.0)
                if consumer_future is not None:
                    _observe_future(consumer_future)
            else:
                # `_consumer_task` is a `Task` on a loop we own. We need
                # the loop to keep running for the task to make progress,
                # so we wait on it via the runner.
                consumer_future = self._runner.submit(self._wait_for_consumer())  # type: ignore[union-attr]
                with contextlib.suppress(BaseException):
                    consumer_future.result(timeout=5.0)
                _observe_future(consumer_future)

        # Close the aio_pika connection.
        if self._conn is not None:
            conn_future: concurrent.futures.Future | None = None
            with contextlib.suppress(BaseException):
                if self._external_loop:
                    conn_future = asyncio.run_coroutine_threadsafe(
                        self._conn.close(), self._loop
                    )
                    conn_future.result(timeout=2.0)
                else:
                    conn_future = self._runner.submit(self._conn.close())  # type: ignore[union-attr]
                    conn_future.result(timeout=2.0)
            if conn_future is not None:
                _observe_future(conn_future)

        # Stop the loop if we own it.
        if not self._external_loop and self._runner is not None:
            self._runner.stop()

        self._closed = True
        self._wake_event = None
        self._drained_event = None
        self._consumer_task = None
        super().close()

    async def _wait_for_consumer(self) -> None:
        """Helper used by `close()` to wait for the consumer task."""
        if self._consumer_task is not None:
            with contextlib.suppress(Exception):
                await self._consumer_task
