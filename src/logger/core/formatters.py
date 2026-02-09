# ---------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------
import json
from datetime import datetime
import logging
from typing import Dict

# ---------------------------------------------------------------------
# Third party libraries
# ---------------------------------------------------------------------
from colorlog import ColoredFormatter


class JSONFormatter(logging.Formatter):

    # Standard LogRecord keys (anything outside this is "extra")
    _reserved = set(logging.LogRecord(
        name="x", level=0, pathname="", lineno=0,
        msg="", args=(), exc_info=None
    ).__dict__.keys())


    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,

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

        # Optional structured fields
        if hasattr(record, "type"):
            payload["type"] = record.type
        if hasattr(record, "result"):
            payload["result"] = record.result
        if hasattr(record, "cur_args"):
            payload["args"] = record.cur_args
        if hasattr(record, "cur_kwargs"):
            payload["kwargs"] = record.cur_kwargs

        # Attach exception if present
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Capture any custom extra fields
        extras = {
            key: v for key, v in record.__dict__.items()
            if key not in self._reserved and key not in payload
        }
        if extras:
            payload["extra"] = extras

        return json.dumps(payload, ensure_ascii=False, default=str)


class ExtrasColoredFormatter(ColoredFormatter):
    _reserved = set(logging.LogRecord(
        name="x", level=0, pathname="",
        lineno=0, msg="", args=(), exc_info=None
    ).__dict__.keys())

    def format(self, record: logging.LogRecord) -> str:
        extras = {
            key: value for key, value in record.__dict__.items()
            if key not in self._reserved
        }

        extras.pop("context", None)
        extras.pop("trace_id", None)
        extras.pop("span_id", None)

        record.extras = (
            " | extras=" + json.dumps(extras, ensure_ascii=False, default=str)
            if extras else ""
        )

        return super().format(record)


class BaseFormatter(logging.Formatter):

    base: str = (
        "[%(asctime)s] [%(levelname)s] "
        "[%(context)s] "
        "- %(message)s %(extras)s"
    )

    log_colors: Dict[str, str] = {
        "DEBUG": "cyan",
        "INFO": "blue",
        "WARNING": "bold_yellow",
        "ERROR": "red",
        "CRITICAL": "bold_red",
    }

    def formatter(self, date: str) -> ColoredFormatter:
        return ExtrasColoredFormatter(
            fmt="%(log_color)s" + self.base + "%(reset)s",
            datefmt=date,
            log_colors=self.log_colors,
        )