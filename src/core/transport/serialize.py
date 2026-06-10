"""
Single source of truth for converting a `LogRecord` to a JSON byte
payload. Used by the AMQP handler and any future transport (Kafka, NATS,
Redis Streams, …).
"""
from __future__ import annotations

import json
import logging
from typing import Any


def record_to_json_bytes(record: logging.LogRecord) -> bytes:
    """
    Stable JSON shape. Returns UTF-8 bytes with no trailing newline —
    the publisher decides on framing.
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
    except Exception as e:
        return json.dumps({"error": str(e), "level": "ERROR"}).encode("utf-8")
