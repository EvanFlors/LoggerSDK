"""
Sync, thread-safe batch buffer for transport sinks.

Used by `AMQPSyncHandler`. The async handler wraps this with a single
long-running coroutine; the sync handler calls `push()` from any thread
and `tick()` from the emit path's size-or-time check.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable


class BatchBuffer:
    """
    Accumulates byte payloads. Flushes either when it reaches `max_size`
    or when `tick()` is called and `max_age_s` has elapsed since the
    last flush.
    """

    def __init__(
        self,
        max_size: int,
        max_age_s: float,
        on_flush: Callable[[list[bytes]], None],
    ) -> None:
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        if max_age_s <= 0:
            raise ValueError("max_age_s must be > 0")
        self._max_size = max_size
        self._max_age_s = max_age_s
        self._on_flush = on_flush
        self._buf: list[bytes] = []
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def push(self, item: bytes) -> None:
        """
        Add `item` to the buffer. Flushes synchronously if the buffer
        reaches `max_size`. Callers that need time-based flushing should
        also call `tick()` periodically (or rely on the size threshold).
        """
        with self._lock:
            self._buf.append(item)
            if len(self._buf) >= self._max_size:
                self._flush_locked()

    def tick(self) -> None:
        """Flush if the buffer is non-empty and `max_age_s` has elapsed."""
        with self._lock:
            if self._buf and (time.monotonic() - self._last) >= self._max_age_s:
                self._flush_locked()

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if not self._buf:
            return
        try:
            self._on_flush(self._buf)
        finally:
            self._buf.clear()
            self._last = time.monotonic()
