from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any

from config import OTelSettings

_trace_var: ContextVar[str | None] = ContextVar("logger_trace_id", default=None)
_span_var: ContextVar[str | None] = ContextVar("logger_span_id", default=None)

_NO_TRACE = "0" * 32
_NO_SPAN = "0" * 16

class Tracer:
    """
    Trace/span facade. Uses OpenTelemetry when configured, falls back to ContextVar
    """

    def __init__(self, settings: OTelSettings) -> None:
        self.settings = settings
        self._otel_tracer: Any = None

        if self.settings.enabled:
            from integrations.opentelemetry import configure_opentelemetry
            configure_opentelemetry(settings, service_name_hint=settings.service_name or "")

            try:
                from opentelemetry import trace
                self._otel_tracer = trace.get_tracer(__name__)
            except Exception:
                self._otel_tracer = None

    # --- Read --- #
    def current_trace_id(self) -> str:
        if self._otel_tracer:
            try:
                from opentelemetry import trace
                span = trace.get_current_span()
                ctx = span.get_span_context() if span else None
                if ctx and ctx.is_valid:
                    return f"{ctx.trace_id:032x}"
            except Exception:
                pass
        return _trace_var.get() or _NO_TRACE

    def current_span_id(self) -> str:
        if self._otel_tracer:
            try:
                from opentelemetry import trace
                span = trace.get_current_span()
                ctx = span.get_span_context() if span else None
                if ctx and ctx.is_valid:
                    return f"{ctx.span_id:016x}"
            except Exception:
                pass
        return _span_var.get() or _NO_SPAN

    # --- Write --- #
    def set_trace(self, trace_id: str | None = None) -> str:
        trace_id = trace_id or uuid.uuid4().hex
        _trace_var.set(trace_id)
        return trace_id

    def set_span(self, span_id: str | None = None) -> str:
        span_id = span_id or uuid.uuid4().hex
        _span_var.set(span_id)
        return span_id

    def clear(self) -> None:
        _trace_var.set(None)
        _span_var.set(None)

    # --- Span lifecycle (OTel-only no-op otherwise)  ---
    def start_span(self, name: str, **attrs: Any) -> Any:
        if self._otel_tracer is None:
            return _NoopSpan()
        return self._otel_tracer.start_as_current_span(name, attributes=attrs)


class _NoopSpan:
    def __enter__(self) -> _NoopSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, *a, **kw):
        pass

    def set_status(self, *a, **kw):
        pass

    def record_exception(self, *a, **kw):
        pass
