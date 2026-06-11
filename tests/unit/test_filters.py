"""
Tests for the sampling and overflow filters.

Includes a regression test for the bug in the original `SamplingFilter`:
the level guard was inverted (`<` instead of `>=`), which silently disabled
sampling for everything *below* the configured `min_level`.
"""
from __future__ import annotations

import logging
import random

from obserlog.config.settings.sampling import SamplingSettings
from obserlog.core.filters.overflow import OverflowFilter, QueueCapacityProbe
from obserlog.core.filters.sampling import (
    DeterministicSamplingFilter,
    SamplingFilter,
    _Decision,
    _stable_float,
)


def _record(level: int, msg: str = "x", trace_id: str | None = None) -> logging.LogRecord:
    r = logging.LogRecord(
        name="x", level=level, pathname="x.py", lineno=1, msg=msg, args=(), exc_info=None
    )
    if trace_id is not None:
        r.trace_id = trace_id
    return r


# ---------------------------------------------------------------------------
# Regression: the `levelno <` bug.
# ---------------------------------------------------------------------------
def test_sampling_keeps_records_at_or_above_min_level():
    """
    With `min_level=WARNING` and `rate=0.0`, every record at WARNING or
    above must be kept regardless of rate. The original bug inverted the
    comparison and dropped all of them.
    """
    f = SamplingFilter(SamplingSettings(rate=0.0, min_level="WARNING", deterministic=False))
    for level in (logging.WARNING, logging.ERROR, logging.CRITICAL):
        assert f.filter(_record(level)) is True, f"level={level} should be kept"


def test_sampling_drops_records_below_min_level_when_rate_zero():
    f = SamplingFilter(SamplingSettings(rate=0.0, min_level="WARNING", deterministic=False))
    assert f.filter(_record(logging.DEBUG)) is False
    assert f.filter(_record(logging.INFO)) is False


def test_sampling_keeps_everything_when_rate_one():
    f = SamplingFilter(SamplingSettings(rate=1.0, min_level="WARNING", deterministic=False))
    for level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR):
        assert f.filter(_record(level)) is True


# ---------------------------------------------------------------------------
# Random sampling: stable around the expected rate.
# ---------------------------------------------------------------------------
def test_sampling_random_rate_approximates_configured_value():
    f = SamplingFilter(SamplingSettings(rate=0.5, min_level="WARNING", deterministic=False))
    random.seed(1234)
    n_kept = sum(1 for _ in range(10_000) if f.filter(_record(logging.DEBUG)))
    # Should be roughly 5000; allow generous slack for the small N.
    assert 4500 < n_kept < 5500


# ---------------------------------------------------------------------------
# Deterministic sampling: same key → same decision.
# ---------------------------------------------------------------------------
def test_sampling_deterministic_is_stable():
    f = SamplingFilter(SamplingSettings(rate=0.5, min_level="WARNING", deterministic=True))
    r1 = _record(logging.DEBUG, msg="hello", trace_id="trace-1")
    r2 = _record(logging.DEBUG, msg="hello", trace_id="trace-1")
    assert f.filter(r1) == f.filter(r2)


def test_sampling_deterministic_falls_back_to_message_when_no_trace_id():
    f = SamplingFilter(SamplingSettings(rate=0.5, min_level="WARNING", deterministic=True))
    r1 = _record(logging.DEBUG, msg="hello")
    r2 = _record(logging.DEBUG, msg="hello")
    assert f.filter(r1) == f.filter(r2)


# ---------------------------------------------------------------------------
# should_keep: pure decision, separate from the filter() round-trip.
# ---------------------------------------------------------------------------
def test_should_keep_returns_enum_decision():
    f = SamplingFilter(SamplingSettings(rate=0.0, min_level="WARNING", deterministic=False))
    assert f.should_keep(_record(logging.DEBUG)) is _Decision.DROP
    assert f.should_keep(_record(logging.WARNING)) is _Decision.KEEP


# ---------------------------------------------------------------------------
# DeterministicSamplingFilter: convenience alias forces determinism.
# ---------------------------------------------------------------------------
def test_deterministic_filter_alias():
    f = DeterministicSamplingFilter(rate=0.5)
    r = _record(logging.DEBUG, msg="x", trace_id="t1")
    # The decision is fully determined by `t1`; check it doesn't change
    # across multiple calls.
    first = f.filter(r)
    for _ in range(5):
        assert f.filter(r) == first


# ---------------------------------------------------------------------------
# OverflowFilter: respects the probe + policy.
# ---------------------------------------------------------------------------
def test_overflow_filter_admits_below_capacity():
    probe = QueueCapacityProbe(size_fn=lambda: 5, capacity=10)
    f = OverflowFilter(probe, "drop_oldest")
    assert f.filter(_record(logging.INFO)) is True


def test_overflow_filter_drops_newest_when_full():
    probe = QueueCapacityProbe(size_fn=lambda: 10, capacity=10)
    f = OverflowFilter(probe, "drop_newest")
    assert f.filter(_record(logging.INFO)) is False


def test_overflow_filter_block_admits_when_full():
    probe = QueueCapacityProbe(size_fn=lambda: 10, capacity=10)
    f = OverflowFilter(probe, "block")
    assert f.filter(_record(logging.INFO)) is True


def test_overflow_filter_drop_oldest_admits_when_full():
    probe = QueueCapacityProbe(size_fn=lambda: 10, capacity=10)
    f = OverflowFilter(probe, "drop_oldest")
    assert f.filter(_record(logging.INFO)) is True


# ---------------------------------------------------------------------------
# Helper: _stable_float is in [0, 1) and deterministic.
# ---------------------------------------------------------------------------
def test_stable_float_is_in_unit_interval():
    for s in ("", "a", "hello world", "trace-1234"):
        v = _stable_float(s)
        assert 0.0 <= v < 1.0


def test_stable_float_is_deterministic():
    assert _stable_float("hello") == _stable_float("hello")
    assert _stable_float("hello") != _stable_float("world")
