"""Tests for the formatters."""
from __future__ import annotations

import json
import logging

from src.core.formatters.colored_formatter import ConsoleFormatter
from src.core.formatters.json_formatter import JSONFormatter


def _record(**overrides) -> logging.LogRecord:
    r = logging.LogRecord(
        name="svc", level=logging.INFO, pathname="/x.py", lineno=42,
        msg="hello %s", args=("world",), exc_info=None,
    )
    # ConsoleFormatter needs `context` on the record. Default it.
    overrides.setdefault("context", None)
    for k, v in overrides.items():
        setattr(r, k, v)
    return r


# ---------------------------------------------------------------------------
# JSONFormatter
# ---------------------------------------------------------------------------
def test_json_formatter_emits_well_formed_json():
    f = JSONFormatter(service_name="svc")
    line = f.format(_record(trace_id="a" * 32, span_id="b" * 16))
    payload = json.loads(line)
    assert payload["service"] == "svc"
    assert payload["level"] == "INFO"
    assert payload["message"] == "hello world"
    assert payload["trace_id"] == "a" * 32
    assert payload["span_id"] == "b" * 16
    assert payload["pathname"] == "/x.py"
    assert payload["line"] == 42


def test_json_formatter_emits_utc_timestamp():
    f = JSONFormatter(service_name="svc")
    payload = json.loads(f.format(_record()))
    assert "T" in payload["timestamp"]
    assert payload["timestamp"].endswith("Z")


def test_json_formatter_attaches_exception():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        rec = logging.LogRecord(
            name="svc", level=logging.ERROR, pathname="/x.py", lineno=1,
            msg="failed", args=(), exc_info=sys.exc_info(),
        )
    f = JSONFormatter(service_name="svc")
    payload = json.loads(f.format(rec))
    # New shape: a structured dict, not a string.
    assert payload["exception"]["type"] == "ValueError"
    assert payload["exception"]["message"] == "boom"
    assert isinstance(payload["exception"]["frames"], list)
    assert len(payload["exception"]["frames"]) >= 1


def test_json_formatter_collects_extras():
    f = JSONFormatter(service_name="svc")
    payload = json.loads(f.format(_record(user_id=42, op="login")))
    assert payload["extras"] == {"user_id": 42, "op": "login"}


# ---------------------------------------------------------------------------
# ConsoleFormatter
# ---------------------------------------------------------------------------
def test_console_formatter_includes_context():
    f = ConsoleFormatter(use_colors=False)
    rec = _record(context="api.py:1 calculate()")
    line = f.format(rec)
    assert "api.py:1 calculate()" in line


def test_console_formatter_omits_extras_when_none():
    f = ConsoleFormatter(use_colors=False)
    line = f.format(_record())
    assert "extras=" not in line


def test_console_formatter_appends_extras_when_present():
    f = ConsoleFormatter(use_colors=False)
    line = f.format(_record(user_id=7))
    assert "extras=" in line
    assert "user_id" in line
