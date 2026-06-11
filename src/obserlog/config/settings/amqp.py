"""AMQP transport settings."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

_ExchangeType = Literal["direct", "topic", "fanout", "headers"]
_Transport = Literal["sync", "async"]


class AMQPSettings(BaseModel):
    url: str = "amqp://guest:guest@localhost:5672/"
    exchange: str = "logs"
    exchange_type: _ExchangeType = "fanout"
    routing_key: str = ""
    queue: str = "logs"
    durable: bool = True
    batch_size: int = 100
    flush_interval_s: float = 1.0
    transport: _Transport = "sync"
    fail_open: bool = True
    connect_timeout_s: float = 5.0
    max_retries: int = 5
