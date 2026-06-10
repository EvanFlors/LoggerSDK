"""Rotation settings: size + time, optional gzip on rollover."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

_RotationWhen = Literal[
    "S", "M", "H", "D", "MIDNIGHT",
    "W0", "W1", "W2", "W3", "W4", "W5", "W6",
]


class RotationSettings(BaseModel):
    max_bytes: int | None = 10_000_000
    backup_count: int | None = 5
    when: _RotationWhen | None = None
    interval: int = 1
    utc: bool = False
    compress: bool = True
