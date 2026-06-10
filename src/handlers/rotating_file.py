from __future__ import annotations

import gzip
import logging
import logging.handlers
import os
import shutil
from datetime import datetime
from pathlib import Path

from src.config import LoggerConfig
from src.core.filters.sampling import SamplingFilter
from src.core.formatters.json_formatter import JSONFormatter


class _GzipOnRolloverMixin:
    """
    Mixin that gzips the rolled-over file (`*.log.1` or
    `*.log.YYYY-MM-DD` for time rotation) before the next cycle evicts
    it. Set `compress = True` on the subclass to enable.
    """
    compress: bool = True
    baseFilename: str
    when: str
    rolloverAt: int  # present on TimedRotatingFileHandler

    def _gzip_after_rollover(self) -> None:
        if not getattr(self, "compress", False):
            return
        # Pick the right source filename. Time rotation names the rolled
        # file differently depending on `when`.
        candidates: list[str] = []
        if isinstance(self, logging.handlers.TimedRotatingFileHandler):
            if not self.when.startswith("W"):
                candidates.append(f"{self.baseFilename}.1")
            else:
                candidates.append(
                    f"{self.baseFilename}.{datetime.fromtimestamp(self.rolloverAt).strftime('%Y-%m-%d')}"
                )
        else:
            candidates.append(f"{self.baseFilename}.1")
        for src in candidates:
            if os.path.exists(src) and not src.endswith(".gz"):
                gz = src + ".gz"
                with open(src, "rb") as f_in, gzip.open(gz, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                os.remove(src)


class _GzSizeRotatingFileHandler(_GzipOnRolloverMixin, logging.handlers.RotatingFileHandler):
    def doRollover(self) -> None:  # type: ignore[override]
        super().doRollover()
        self._gzip_after_rollover()


class _GzTimedRotatingFileHandler(_GzipOnRolloverMixin, logging.handlers.TimedRotatingFileHandler):
    def doRollover(self) -> None:  # type: ignore[override]
        super().doRollover()
        self._gzip_after_rollover()


def make_rotating_file_handler(cfg: LoggerConfig) -> logging.Handler:
    Path(cfg.directory).mkdir(parents=True, exist_ok=True)
    filename = os.path.join(cfg.directory, f"{cfg.service_name}.log")
    rot = cfg.rotation

    if rot is not None and rot.when is not None:
        h: logging.Handler = _GzTimedRotatingFileHandler(
            filename,
            when=rot.when,
            interval=rot.interval,
            backupCount=rot.backup_count or 5,
            utc=rot.utc,
            encoding="utf-8",
        )
    else:
        h = _GzSizeRotatingFileHandler(
            filename,
            maxBytes=(rot.max_bytes if rot and rot.max_bytes else 10_000_000),
            backupCount=(rot.backup_count if rot and rot.backup_count else 5),
            encoding="utf-8",
        )
    if rot is not None:
        h.compress = rot.compress  # type: ignore[attr-defined]

    h.setLevel(cfg.numeric_level())
    h.setFormatter(JSONFormatter(service_name=cfg.service_name, date_format=cfg.date_format))
    h.addFilter(SamplingFilter(cfg.sampling))
    return h

