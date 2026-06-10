"""
Shared helpers for the AMQP sync and async handlers.

Lives in its own module so that the sync and async handlers don't have to
duplicate the JSON-serialization shape, the URL/credentials parsing, or the
retry-policy constants.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.config import AMQPSettings


def serialize_record(record: logging.LogRecord) -> bytes:
    """
    Stable JSON shape used for every record that goes on the wire to AMQP.
    Returns a single UTF-8 encoded line (no trailing newline is appended —
    the publisher is responsible for framing).
    """
    payload: dict[str, Any] = {
        "message": record.getMessage(),
        "level": record.levelname,
        "logger": record.name,
        "trace_id": getattr(record, "trace_id", None),
        "span_id": getattr(record, "span_id", None),
        "context": getattr(record, "context", None),
    }
    try:
        return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    except Exception as e:  # never let a serialization bug kill the producer
        return json.dumps({"error": str(e), "level": "ERROR"}).encode("utf-8")


def validate_settings(settings: AMQPSettings) -> None:
    """
    Cheap up-front validation. Most validation already happens in
    `AMQPSettings` (Pydantic) — this catches things that Pydantic can't, like
    empty `url` strings.
    """
    if not settings.url:
        raise ValueError("AMQPSettings.url must be non-empty")
    if settings.batch_size < 1:
        raise ValueError("AMQPSettings.batch_size must be >= 1")
    if settings.flush_interval_s <= 0:
        raise ValueError("AMQPSettings.flush_interval_s must be > 0")
