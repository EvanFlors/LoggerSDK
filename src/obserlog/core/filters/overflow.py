"""
Drops records when the producer-side queue is over capacity. The probe
encapsulates queue size + capacity as a single dataclass so the filter
itself doesn't need dynamic attribute trickery.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal


@dataclass
class QueueCapacityProbe:
    """
    Snapshot of the queue's current state. The factory builds one of these
    per `LoggerFactory` and passes it to the filter.
    """

    size_fn: Callable[[], int]
    capacity: int


class OverflowFilter(logging.Filter):
    """
    Drops records when the queue is over capacity.

    Policies:
    - `drop_oldest`: the stdlib `Queue` is bounded; new records are still
      admitted and the oldest get evicted by the consumer. This filter
      always returns `True`.
    - `drop_newest`: reject the record. The producer sees the drop.
    - `block`: always admit. The producer will block on `put` because the
      `Queue` is bounded, applying natural back-pressure.
    """

    def __init__(self, probe: QueueCapacityProbe, policy: str = "drop_oldest") -> None:
        super().__init__()
        self._probe = probe
        self._policy: Literal["drop_oldest", "drop_newest", "block"] = policy  # type: ignore[assignment]

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        size = self._probe.size_fn()
        if size < self._probe.capacity:
            return True
        # `drop_newest` rejects; `drop_oldest` and `block` both admit
        # (the queue evicts internally for the former; the producer
        # blocks on `put` for the latter).
        return self._policy != "drop_newest"
