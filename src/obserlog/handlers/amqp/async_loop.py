"""
A dedicated asyncio event loop running in a daemon thread.

The async AMQP handler needs an event loop to drive aio-pika. There are two
common situations:

1. The caller is already inside an asyncio program (e.g. a FastAPI worker).
   In that case they pass `loop=` to the handler and we do nothing here.
2. The caller is in a sync script / CLI / worker. In that case the handler
   owns a fresh loop in its own daemon thread so it can run aio-pika
   coroutines without blocking the caller.

This module is the second case. It exposes `LoopRunner` with a tiny API:

    runner = LoopRunner.start()           # loop + thread are running
    runner.submit(coro).result()          # schedule a coroutine, wait
    runner.run(coro)                      # schedule a coroutine, fire-and-forget
    runner.stop()                         # stop the loop, join the thread

The runner is single-use: once `stop()` is called it cannot be reused.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import logging
import threading
from collections.abc import Coroutine
from typing import Any

from obserlog.errors import AMQPError

_log = logging.getLogger(__name__)


class LoopRunner:
    """
    Owns one asyncio loop running in one daemon thread. Thread-safe.

    Public surface is intentionally tiny: `start`, `submit`, `run`, `stop`.
    Everything else (queues, events, futures) is an implementation detail
    of the handler that holds a `LoopRunner`.
    """

    def __init__(self, name: str = "amqp-async-loop") -> None:
        self._name = name
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    # ----- lifecycle -----------------------------------------------------
    @classmethod
    def start(cls, name: str = "amqp-async-loop") -> LoopRunner:
        runner = cls(name=name)
        runner._start()
        return runner

    @staticmethod
    def _loop_exception_handler(
        loop: asyncio.AbstractEventLoop, context: dict[str, Any]
    ) -> None:
        exc = context.get("exception")
        if isinstance(exc, asyncio.CancelledError):
            return
        msg = context.get("message", "Unhandled exception in AMQP async loop")
        _log.warning("%s: %s", msg, exc)

    def _start(self) -> None:
        loop = asyncio.new_event_loop()
        loop.set_exception_handler(self._loop_exception_handler)
        ready = threading.Event()

        def _runner() -> None:
            asyncio.set_event_loop(loop)
            ready.set()
            try:
                loop.run_forever()
            finally:
                with contextlib.suppress(Exception):  # the loop may already be closed
                    loop.close()

        thread = threading.Thread(
            target=_runner,
            name=self._name,
            daemon=True,
        )
        thread.start()
        if not ready.wait(timeout=2.0):
            raise AMQPError("AMQP async loop failed to start within 2s")
        self._loop = loop
        self._thread = thread

    # ----- coroutine submission -----------------------------------------
    def submit(self, coro: Coroutine[Any, Any, Any]) -> concurrent.futures.Future:
        """
        Schedule a coroutine on the loop, return a `Future` so the caller
        can `.result()` it. Thread-safe.
        """
        if self._loop is None or self._thread is None:
            raise AMQPError("LoopRunner is not started")
        if self._loop.is_closed():
            raise AMQPError("LoopRunner loop is closed")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def run(self, coro: Coroutine[Any, Any, Any]) -> concurrent.futures.Future:
        """
        Fire-and-forget variant of `submit`. The future is still attached
        to the loop, so an unhandled exception inside the coroutine will
        be reported via the loop's exception handler — never silently lost.
        """
        future = self.submit(coro)

        def _log_error(fut: concurrent.futures.Future) -> None:
            if fut.cancelled():
                return
            exc = fut.exception()
            if exc is not None:
                _log.debug("amqp loop coroutine raised: %r", exc, exc_info=exc)

        future.add_done_callback(_log_error)
        return future

    # ----- shutdown ------------------------------------------------------
    def stop(self, timeout: float = 2.0) -> None:
        """
        Stop the loop and join the thread. Idempotent and safe to call
        multiple times. Sets `_loop = None` so any subsequent `submit` raises
        instead of silently failing.
        """
        if self._loop is None and self._thread is None:
            return
        loop = self._loop
        thread = self._thread
        self._loop = None
        self._thread = None
        if loop is not None and not loop.is_closed():
            async def _cancel_all() -> None:
                tasks = [
                    t for t in asyncio.all_tasks(loop)
                    if t is not asyncio.current_task()
                ]
                for task in tasks:
                    task.cancel()
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, Exception) and not isinstance(
                        r, (asyncio.CancelledError, concurrent.futures.CancelledError)
                    ):
                        _log.warning("Task exception during shutdown: %r", r)

            with contextlib.suppress(BaseException):
                fut = asyncio.run_coroutine_threadsafe(_cancel_all(), loop)
                fut.result(timeout=timeout)

            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(loop.stop)
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    # ----- introspection -------------------------------------------------
    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        return self._loop
