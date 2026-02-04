# ---------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------
import random
import hashlib
import logging


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