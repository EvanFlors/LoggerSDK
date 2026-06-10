import hashlib
import logging
import random

from config import SamplingSettings


def _stable_float(s: str) -> float:
    digest = hashlib.sha256(s.encode()).hexdigest()
    n = int(digest[:16], 16)
    return (n % 10_000_000) / 10_000_000.0

class SamplingFilter(logging.Filter):
    def __init__(self, settings: SamplingSettings) -> None:
        super().__init__()
        self._settings = settings
        self._min_level = logging._nameToLevel[settings.min_level]

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < self._min_level:
            return True

        rate = self._settings.rate
        if rate >= 1.0:
            return True

        if rate < 0.0:
            return False

        if self._settings.deterministic:
            key = getattr(record, "trace_id", "") or f"{record.name}|{record.getMessage()}"
            return _stable_float(key) < rate

        return random.random() < rate

class DeterministicSamplingFilter(SamplingFilter):
    """
    Convenience alias. Always hashes (trace, ctx, msg).
    """

    def __init__(self, rate: float, min_level: int = logging.WARNING) -> None:
        super().__init__(SamplingSettings(rate=rate, min_level=logging.getLevelName(min_level), deterministic=True))

class OverflowFilter(logging.Filter):
    """
    Drops records when the global queue is over capacity.
    The actual queue length is queried lazily via a callable (set by factory).
    """

    def __init__(self, capacity_fn, policy: str = "drop_oldest") -> None:
        super().__init__()
        self._capacity_fn = capacity_fn
        self._policy = policy

    def filter(self, record: logging.LogRecord) -> bool:
        size = self._capacity_fn()
        cap = self._capacity_fn.capacity

        if size < cap:
            return True

        if self._policy == "block":
            return False

        if self._policy == "drop_newest":
            return False

        return True

class OverflowFilter(logging.Filter):
    """
    Drops records when the global queue is over capacity.
    The actual queue length is queried lazily via a callable (set by factory).
    """

    def __init__(self, capacity_fn: callable, policy: str = "drop_oldest") -> None:
        super().__init__()
        self._capacity_fn = capacity_fn
        self._policy = policy

    def filter(self, record: logging.LogRecord) -> bool:
        size = self._capacity_fn()
        cap = self._capacity_fn.capacity

        if size < cap:
            return True

        if self._policy == "block":
            return False

        if self._policy == "drop_newest":
            return False

        return True

