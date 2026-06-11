"""Rotation settings: size + time, optional gzip on rollover."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

# Pydantic Literals are case-sensitive. We normalize to the upper-case
# form expected by stdlib's `TimedRotatingFileHandler`.
_RotationWhen = Literal[
    "S", "M", "H", "D", "MIDNIGHT",
    "W0", "W1", "W2", "W3", "W4", "W5", "W6",
]

# Lower-case aliases accepted from kwargs. We coerce them to the
# upper-case form via the validator below.
_VALID_WHEN_LOWER = {
    "s": "S", "m": "M", "h": "H", "d": "D", "midnight": "MIDNIGHT",
    "w0": "W0", "w1": "W1", "w2": "W2", "w3": "W3",
    "w4": "W4", "w5": "W5", "w6": "W6",
}


class RotationSettings(BaseModel):
    max_bytes: int | None = 10_000_000
    backup_count: int | None = 5
    when: _RotationWhen | None = None
    interval: int = 1
    utc: bool = False
    compress: bool = True

    @field_validator("when", mode="before")
    @classmethod
    def _normalize_when(cls, value):
        if isinstance(value, str):
            upper = value.upper()
            if upper in {"S", "M", "H", "D", "MIDNIGHT", "W0", "W1", "W2", "W3", "W4", "W5", "W6"}:
                return upper
            if value.lower() in _VALID_WHEN_LOWER:
                return _VALID_WHEN_LOWER[value.lower()]
        return value
