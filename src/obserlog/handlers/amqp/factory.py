"""
Public entrypoint for AMQP handlers. Picks the right class based on
`settings.transport`.
"""
from __future__ import annotations

import asyncio
import logging

from obserlog.config import AMQPSettings
from obserlog.handlers.amqp.async_handler import AMQPAsyncHandler
from obserlog.handlers.amqp.sync import AMQPSyncHandler


def make_amqp_handler(settings: AMQPSettings) -> logging.Handler:
    """
    Build the right handler for the configured transport.

    - `transport="sync"`  → pika (BlockingConnection). Safe anywhere.
    - `transport="async"` → aio-pika. If a loop is already running in the
      current thread, attach to it; otherwise the handler starts and owns
      a dedicated loop in a daemon thread.
    """
    if settings.transport == "sync":
        return AMQPSyncHandler(settings)

    try:
        loop = asyncio.get_running_loop()
        return AMQPAsyncHandler(settings, loop=loop)
    except RuntimeError:
        # No running loop in the current thread. The async handler will
        # create its own loop in a daemon thread.
        return AMQPAsyncHandler(settings)
