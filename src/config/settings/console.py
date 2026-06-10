"""Console handler settings."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ConsoleSettings(BaseModel):
    enabled: bool = True
    colors: bool = True
    destination: Literal["stdout", "stderr"] = "stdout"
