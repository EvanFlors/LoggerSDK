"""
Sampling filters.

Two policies:

- `SamplingFilter`: a `logging.Filter` that keeps WARNING+ always and
  randomly keeps DEBUG/INFO at a configured rate. Optionally deterministic
  (hashes `trace_id` so the same record is consistently kept or dropped).
- `DeterministicSamplingFilter`: convenience that forces `deterministic=True`.

The bug fix in this module: the original implementation had
`if record.levelno < self._min_level: return True` — which is the OPPOSITE
of what the docstring promised (and what the rest of the code expects).
The correct condition is `record.levelno >= self._min_level`.
"""
from __future__ import annotations

import hashlib
import logging
import random
from enum import Enum

from src.config import SamplingSettings


class _Decision(Enum):
    KEEP = "keep"
    DROP = "drop"


def _stable_float(s: str) -> float:
    """Deterministic mapping from a string to a float in [0, 1)."""
    digest = hashlib.sha256(s.encode("utf-8")).hexdigest()
    n = int(digest[:16], 16)
    return (n % 10_000_000) / 10_000_000.0


def _stable_key(record: logging.LogRecord) -> str:
    """
    Build the deterministic key. Prefer `trace_id` (so the same trace
    is consistently kept or dropped); fall back to logger+message.
    """
    trace_id = getattr(record, "trace_id", None)
    if trace_id:
        return str(trace_id)
    return f"{record.name}|{record.getMessage()}"


class SamplingFilter(logging.Filter):
    """
    Always passes through records at or above the configured `min_level`.
    For records below, applies the configured `rate` either randomly
    or deterministically.
    """

    def __init__(self, settings: SamplingSettings) -> None:
        super().__init__()
        self._settings = settings
        self._min_level = logging._nameToLevel[settings.min_level]

    def should_keep(self, record: logging.LogRecord) -> _Decision:
        """
        Pure decision function. Returns whether this record should be
        emitted. Public so it can be unit-tested without instantiating
        a full filter pipeline.
        """
        # Always keep high-signal records.
        if record.levelno >= self._min_level:
            return _Decision.KEEP
        rate = self._settings.rate
        if rate >= 1.0:
            return _Decision.KEEP
        if rate <= 0.0:
            return _Decision.DROP
        if self._settings.deterministic:
            return _Decision.KEEP if _stable_float(_stable_key(record)) < rate else _Decision.DROP
        return _Decision.KEEP if random.random() < rate else _Decision.DROP

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        return self.should_keep(record) is _Decision.KEEP


class DeterministicSamplingFilter(SamplingFilter):
    """
    Always hashes `(trace, ctx, msg)` for the decision. Useful for
    "drop the same trace everywhere or keep it everywhere".
    """

    def __init__(self, rate: float, min_level: int = logging.WARNING) -> None:
        super().__init__(
            SamplingSettings(
                rate=rate,
                min_level=logging.getLevelName(min_level),  # type: ignore[arg-type]
                deterministic=True,
            )
        )
