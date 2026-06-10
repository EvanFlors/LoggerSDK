"""
Structured JSON formatter for log files and structured sinks.

Stable shape:

  {
    "timestamp": ISO 8601 with microseconds, UTC,
    "level": "INFO" | ...,
    "message": <formatted message>,
    "logger": <logger name>,
    "service": <service name from config>,
    "context": <file:line Class.method() or user-provided>,
    "trace_id": <32-hex or zeros>,
    "span_id":  <16-hex or zeros>,
    "module": <record.module>,
    "function": <record.funcName>,
    "line": <record.lineno>,
    "pathname": <record.pathname>,
    "process": <record.process>,
    "thread": <record.thread>,
    ...user-supplied `extra` fields
  }
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

# Pre-compute the set of standard LogRecord attribute names once at import
# time. Anything outside this set is "extra" and goes into the `extras` block.
_RESERVED = set(
    logging.LogRecord(
        name="x", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None,
    ).__dict__.keys()
)


class JSONFormatter(logging.Formatter):
    """Stable, reserved-key-aware JSON formatter."""

    def __init__(
        self,
        service_name: str,
        date_format: str = "%Y-%m-%dT%H:%M:%S.%fZ",
    ) -> None:
        super().__init__()
        self._service = service_name
        self._date_format = date_format

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            self._date_format
        )
        payload: dict[str, Any] = {
            "timestamp": ts,
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "service": self._service,
            "context": getattr(record, "context", None),
            "trace_id": getattr(record, "trace_id", None),
            "span_id": getattr(record, "span_id", None),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "pathname": record.pathname,
            "process": record.process,
            "thread": record.thread,
        }
        for key in ("type", "result", "cur_args", "cur_kwargs"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "otel_status"):
            payload["otel_status"] = record.otel_status

        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in _RESERVED and k not in payload
        }
        if extras:
            payload["extras"] = extras

        return json.dumps(payload, ensure_ascii=False, default=str)
