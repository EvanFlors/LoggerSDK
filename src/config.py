# ---------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------
import json
import random
import logging
import hashlib
from typing import Dict
from datetime import datetime
from dataclasses import dataclass, field

# ---------------------------------------------------------------------
# Third party libraries
# ---------------------------------------------------------------------
from colorlog import ColoredFormatter


class SamplingFilter(logging.Filter):

    def __init__(self, rate: float = 1.0, min_level: int = logging.WARNING):
        self.rate = rate
        self.min_level = min_level


    def filter(self, record: logging.LogRecord) -> bool:
        # Always keep high signal logs
        if record.levelno >= self.min_level:
            return True

        # Sample everything below that
        return random.random() < self.rate


class DeterministicSamplingFilter(logging.Filter):

    def __init__(
        self,
        rate: float = 1.0,
        random: float = 1.0,
        min_level: int = logging.WARNING
    ):
        self.rate = rate
        self.min_level = min_level
        self.random = random


    def _stable_float(self, value: str) -> float:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        n = int(digest[:16], 16)
        return (n % 10_000_000) / 10_000_000.0


    def filter(self, record: logging.LogRecord) -> bool:
        # Always keep WARNING+
        if record.levelno >= self.min_level:
            return True

        # Sample only DEBUG/INFO
        if self.rate >= 1.0:
            return True
        if self.rate <= 0.0:
            return False

        trace_id = getattr(record, "trace_id", None)
        context = getattr(record, "context", "")
        key = trace_id or f"{record.name}|{context}|{record.getMessage()}"

        return self._stable_float(str(key)) < self.rate


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
            k: v for k, v in record.__dict__.items()
            if k not in self._reserved and k not in payload
        }
        if extras:
            payload["extra"] = extras

        return json.dumps(payload, ensure_ascii=False)


@dataclass
class LoggerConfig:
    directory: str = "logs"
    name: str = "app"
    json_logs: bool = False

    module_levels: dict[str, int] = field(default_factory=dict)
    sample_rate: float = 1.0
    deterministic: bool = False

    level: int = logging.INFO
    date: str = "%d-%m-%y_%H:%M:%S"

    base: str = (
        "[%(asctime)s] [%(levelname)s] "
        "[%(context)s] "
        "- %(message)s%(extras)s"
    )

    log_colors: Dict[str, str] = field(default_factory=lambda: {
        "DEBUG": "cyan",
        "INFO": "blue",
        "WARNING": "bold_yellow",
        "ERROR": "red",
        "CRITICAL": "bold_red",
    })

    def formatter(self) -> ColoredFormatter:
        return ExtrasColoredFormatter(
            fmt="%(log_color)s" + self.base + "%(reset)s",
            datefmt=self.date,
            log_colors=self.log_colors,
        )


class ExtrasColoredFormatter(ColoredFormatter):
    _reserved = set(logging.LogRecord(
        name="x", level=0, pathname="",
        lineno=0, msg="", args=(), exc_info=None
    ).__dict__.keys())

    def format(self, record: logging.LogRecord) -> str:
        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in self._reserved
        }

        extras.pop("context", None)
        extras.pop("trace_id", None)
        extras.pop("span_id", None)

        record.extras = (
            " | extras=" + json.dumps(extras, ensure_ascii=False, default=str)
            if extras else ""
        )

        return super().format(record)
