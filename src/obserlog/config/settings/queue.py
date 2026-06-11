"""Queue settings: capacity + overflow policy."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

_OverflowPolicy = Literal["drop_oldest", "drop_newest", "block"]


class QueueSettings(BaseModel):
    capacity: int = 10_000
    overflow: _OverflowPolicy = "drop_oldest"
    flush_on_exit: bool = True
