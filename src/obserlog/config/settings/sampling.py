"""Sampling settings: rate, floor, determinism."""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Pydantic Literals are case-sensitive. We normalize to the upper-case
# form via the validator below.
_ValidLogLevels = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def _to_level(value: str) -> int:
    name = value.upper()
    if name not in logging._nameToLevel:
        raise ValueError(f"Invalid log level: {value}")
    return logging._nameToLevel[name]


class SamplingSettings(BaseModel):
    # `rate=0.0` is a valid setting: it means "drop everything below
    # `min_level`". `ge=0.0` allows it; `le=1.0` caps the upper end.
    rate: float = Field(default=1.0, ge=0.0, le=1.0)
    min_level: _ValidLogLevels = "WARNING"
    deterministic: bool = False

    @field_validator("min_level", mode="before")
    @classmethod
    def _normalize_min_level(cls, v):
        if isinstance(v, str):
            upper = v.upper()
            if upper in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
                return upper
        return v
