"""
Trace/span facade.

Two modes:

- **OpenTelemetry mode** (when `OTelSettings.enabled=True` and the OTel
  packages are installed): the active span from the global OTel
  `TracerProvider` is the source of truth. The W3C `trace_id` and
  `span_id` are read from the current span and formatted as 32-hex /
  16-hex strings.

- **Standalone mode** (no OTel): two `ContextVar`s — `_trace_var` and
  `_span_var` — carry the ids. This keeps the same `current_trace_id()` /
  `current_span_id()` API working in async code and in thread pools.

The facade has no awareness of `BoundLogger`; it only knows how to read
and write ids. Logs pick up the ids via the `BoundLogger.process` hook.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any

from obserlog.config import OTelSettings

_trace_var: ContextVar[str | None] = ContextVar("logger_trace_id", default=None)
_span_var: ContextVar[str | None] = ContextVar("logger_span_id", default=None)

_NO_TRACE = "0" * 32
_NO_SPAN = "0" * 16


class _NoopSpan:
    """Returned by `Tracer.start_span` when OTel is not available."""

    def __enter__(self) -> _NoopSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def set_attribute(self, *a: Any, **kw: Any) -> None:
        return None

    def set_status(self, *a: Any, **kw: Any) -> None:
        return None

    def record_exception(self, *a: Any, **kw: Any) -> None:
        return None


class Tracer:
    """Trace/span facade. See module docstring for the two modes."""

    def __init__(self, settings: OTelSettings) -> None:
        self._settings = settings
        self._otel_tracer: Any = None
        if settings.enabled:
            self._init_otel()

    def _init_otel(self) -> None:
        try:
            from obserlog.integrations.opentelemetry import configure_opentelemetry
            configure_opentelemetry(
                self._settings,
                service_name_hint=self._settings.service_name or "",
            )
            from opentelemetry import trace
            self._otel_tracer = trace.get_tracer("logger")
        except Exception:
            # OTel is optional; if anything goes wrong we silently
            # downgrade to ContextVar mode.
            self._otel_tracer = None

    # --- read -----------------------------------------------------------
    def current_trace_id(self) -> str:
        if self._otel_tracer is not None:
            ctx = self._otel_span_context()
            if ctx is not None and ctx.is_valid:
                return f"{ctx.trace_id:032x}"
        return _trace_var.get() or _NO_TRACE

    def current_span_id(self) -> str:
        if self._otel_tracer is not None:
            ctx = self._otel_span_context()
            if ctx is not None and ctx.is_valid:
                return f"{ctx.span_id:016x}"
        return _span_var.get() or _NO_SPAN

    def _otel_span_context(self) -> Any:
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            return span.get_span_context() if span else None
        except Exception:
            return None

    # --- write ----------------------------------------------------------
    def set_trace(self, trace_id: str | None = None) -> str:
        tid = trace_id or uuid.uuid4().hex
        _trace_var.set(tid)
        return tid

    def set_span(self, span_id: str | None = None) -> str:
        # W3C span_id is 16 hex chars (8 bytes). `uuid.uuid4().hex[:16]`
        # gives us that. We don't need cryptographic uniqueness here —
        # collision probability is acceptable for tracing.
        sid = span_id or uuid.uuid4().hex[:16]
        _span_var.set(sid)
        return sid

    def clear(self) -> None:
        _trace_var.set(None)
        _span_var.set(None)

    # --- span lifecycle (OTel-only no-op otherwise) --------------------
    def start_span(self, name: str, **attrs: Any) -> Any:
        if self._otel_tracer is None:
            return _NoopSpan()
        return self._otel_tracer.start_as_current_span(name, attributes=attrs)
