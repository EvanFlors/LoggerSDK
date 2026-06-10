from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from colorlog import ColoredFormatter

_RESERVED = set(
    logging.LogRecord(
        name="x",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__.keys()
)


class JSONFormatter(logging.Formatter):
    """
    Stable, reserved-key-aware JSON formatter. W3C trace_id/span_id are always
    emitted as 32-hex / 16-hex strings.
    """

    def __init__(self, service_name: str, date_format: str = "%Y-%m-%dT%H:%M:%S.%fZ") -> None:
        super().__init__()
        self._service = service_name
        self._date_format = date_format

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(self._date_format)

        payload: dict[str, Any] = {
            "timestamp": ts.strftime(self._date_format),
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

class ExtrasColoredFormatter(ColoredFormatter):
    base = "[%(asctime)s] [%(levelname)s] [%(context)s] %(extras)s - %(message)s"
    log_colors = {  # noqa: RUF012
        "DEBUG": "cyan",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold_red",
    }

    def __init__(self, date_format: str = "%Y-%m-%dT%H:%M:%S.%fZ", use_colors: bool = True) -> None:
        fmt = ("%(log_color)s" + self.base + "%(reset)s") if use_colors else self.base
        super().__init__(fmt=fmt, datefmt=date_format, log_colors=self.log_colors if use_colors else {})

    def format(self, record: logging.LogRecord) -> str:
        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in _RESERVED
            and k not in ("context", "trace_id", "span_id")
        }
        record.extras = (" | extras=" + json.dumps(extras, default=str)) if extras else ""
        return super().format(record)