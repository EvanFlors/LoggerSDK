from __future__ import annotations

import logging
from typing import Any

from src.core.caller import resolve_caller
from src.core.tracer import Tracer


class BoundLogger(logging.LoggerAdapter):
    """
    LoggerAdapter that injects trace_id, span_id, context and any bound fields
    into every log record. Created via `LoggerFactory.get_logger().bind(...)`.
    """

    def __init__(self, logger: logging.Logger, extra: dict[str, Any], tracer: Tracer) -> None:
        super().__init__(logger, extra)
        self._tracer = tracer

    def bind(self, **fields: Any) -> BoundLogger:
        merged = {**self.extra, **fields}  # type: ignore[dict-item]
        return BoundLogger(self.logger, merged, self._tracer)

    def set_trace(self, trace_id: str | None = None) -> str:
        return self._tracer.set_trace(trace_id)

    def set_span(self, span_id: str | None = None) -> str:
        return self._tracer.set_span(span_id)

    def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:  # type: ignore[override]
        call_extra = kwargs.get("extra")
        if not isinstance(call_extra, dict):
            call_extra = {}
        merged = {**self.extra, **call_extra}  # type: ignore[dict-item]
        merged.setdefault("trace_id", self._tracer.current_trace_id())
        merged.setdefault("span_id", self._tracer.current_span_id())
        if "context" not in merged:
            caller = resolve_caller()
            merged["context"] = f"{self.logger.name} | {caller.render()}"
        kwargs["extra"] = merged
        return msg, kwargs
