from __future__ import annotations

import gzip
import logging
import logging.handlers
import os
import shutil
from datetime import datetime
from pathlib import Path

from config import LoggerConfig
from core.filters import SamplingFilter
from core.formatters import JSONFormatter


class _GzRotatingFileHandler(logging.handlers.RotatingFileHandler):
    def doRollover(self) -> None:  # type: ignore[override]
        super().doRollover()
        if getattr(self, "compress", False):
            src = f"{self.baseFilename}.1"
            if os.path.exists(src) and not src.endswith(".gz"):
                gz = src + ".gz"
                with open(src, "rb") as f_in, gzip.open(gz, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                os.remove(src)


class _GzTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    def doRollover(self) -> None:  # type: ignore[override]
        super().doRollover()
        if getattr(self, "compress", False):
            src = f"{self.baseFilename}.1" if not self.when.startswith("W") else \
                  f"{self.baseFilename}.{datetime.strftime(self.rolloverAt, '%Y-%m-%d')}"
            if os.path.exists(src) and not src.endswith(".gz"):
                gz = src + ".gz"
                with open(src, "rb") as f_in, gzip.open(gz, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                os.remove(src)


def make_rotating_file_handler(cfg: LoggerConfig) -> logging.Handler:
    Path(cfg.directory).mkdir(parents=True, exist_ok=True)
    filename = os.path.join(cfg.directory, f"{cfg.service_name}.log")
    rot = cfg.rotation

    if rot is not None and rot.when is not None:
        h = _GzTimedRotatingFileHandler(
            filename,
            when=rot.when,
            interval=rot.interval,
            backupCount=rot.backup_count,
            utc=rot.utc,
            encoding="utf-8",
        )
    else:
        h = _GzRotatingFileHandler(
            filename,
            maxBytes=(rot.max_bytes if rot else 10_000_000) or 10_000_000,
            backupCount=(rot.backup_count if rot else 5),
            encoding="utf-8",
        )
    if rot is not None:
        h.compress = rot.compress  # type: ignore[attr-defined]

    h.setLevel(cfg.numeric_level())
    h.setFormatter(JSONFormatter(service_name=cfg.service_name, date_format=cfg.date_format))
    h.addFilter(SamplingFilter(cfg.sampling))
    return h
