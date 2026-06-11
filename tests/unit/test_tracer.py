"""Tests for the tracer (ContextVar fallback path — no OTel)."""
from __future__ import annotations

from obserlog.config.settings.otel import OTelSettings
from obserlog.core.tracer import Tracer


def test_tracer_uses_contextvars_when_otel_disabled():
    t = Tracer(OTelSettings(enabled=False))
    # Initial values are the W3C zero trace/span.
    assert t.current_trace_id() == "0" * 32
    assert t.current_span_id() == "0" * 16


def test_tracer_set_trace_returns_value_and_reads_back():
    t = Tracer(OTelSettings(enabled=False))
    tid = t.set_trace()
    assert isinstance(tid, str) and len(tid) == 32
    assert t.current_trace_id() == tid

    sid = t.set_span()
    assert isinstance(sid, str) and len(sid) == 16
    assert t.current_span_id() == sid


def test_tracer_set_trace_with_explicit_id():
    t = Tracer(OTelSettings(enabled=False))
    t.set_trace("cafebabe" * 4)
    assert t.current_trace_id() == "cafebabe" * 4


def test_tracer_clear_resets_both():
    t = Tracer(OTelSettings(enabled=False))
    t.set_trace("a" * 32)
    t.set_span("b" * 16)
    t.clear()
    assert t.current_trace_id() == "0" * 32
    assert t.current_span_id() == "0" * 16


def test_tracer_start_span_returns_noop_when_otel_disabled():
    t = Tracer(OTelSettings(enabled=False))
    span = t.start_span("work")
    # `_NoopSpan` is a context manager; the user can call `with` on it.
    with span as s:
        s.set_attribute("foo", "bar")
        s.set_status("ok")
        s.record_exception(RuntimeError("x"))
