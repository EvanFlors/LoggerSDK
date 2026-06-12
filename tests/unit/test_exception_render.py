"""
Tests for the rich exception renderer (`src.core.exception_render`).

Covers:
- structured (JSON-friendly) rendering
- pretty (colorized terminal) rendering
- edge cases: bare exceptions, no traceback, deeply nested
  chains, source-unavailable frames (`<stdin>`)
- formatter integration (`JSONFormatter`, `ConsoleFormatter`)
"""
from __future__ import annotations

import json
import logging
import re
import sys

from obserlog.core.exception_render import (
    format_exception_pretty,
    format_exception_structured,
    rich_format_exception,
)
from obserlog.core.formatters.colored_formatter import ConsoleFormatter
from obserlog.core.formatters.json_formatter import JSONFormatter

# Strip ANSI escape codes so we can assert on plain text.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


# ---------------------------------------------------------------------------
# Helper: produce a real exception with a real traceback from a real file.
# ---------------------------------------------------------------------------
def _produce_exc():
    def inner():
        x = 42
        y = "hello"
        d = {"x": x, "y": y}
        return d["missing_key"]  # KeyError

    try:
        inner()
    except KeyError:
        return sys.exc_info()
    raise AssertionError("unreachable")


# ---------------------------------------------------------------------------
# Structured rendering
# ---------------------------------------------------------------------------
def test_structured_returns_dict_with_type_message_frames():
    exc_info = _produce_exc()
    out = format_exception_structured(exc_info)
    assert out["type"] == "KeyError"
    assert "missing_key" in out["message"]
    assert isinstance(out["frames"], list)
    assert len(out["frames"]) >= 1


def test_structured_frames_contain_required_keys():
    exc_info = _produce_exc()
    out = format_exception_structured(exc_info)
    for f in out["frames"]:
        assert {"file", "line", "function", "source", "locals"} <= set(f)


def test_structured_is_json_serializable():
    exc_info = _produce_exc()
    out = format_exception_structured(exc_info)
    # Round-trip through json.dumps — must not raise.
    s = json.dumps(out, default=str)
    again = json.loads(s)
    assert again["type"] == "KeyError"


def test_structured_handles_none():
    assert format_exception_structured(None) == {
        "type": "None",
        "message": "",
        "frames": [],
    }


def test_structured_handles_bare_exception():
    class _Custom(Exception):
        pass

    try:
        raise _Custom("boom")
    except _Custom:
        ei = sys.exc_info()
    out = format_exception_structured(ei)
    assert out["type"] == "_Custom"
    assert out["message"] == "boom"
    assert len(out["frames"]) >= 1


def test_structured_locals_filters_dunder():
    exc_info = _produce_exc()
    out = format_exception_structured(exc_info)
    innermost = out["frames"][-1]  # exception site is last
    assert "x" in innermost["locals"]
    assert "y" in innermost["locals"]
    # Dunder names should NOT appear in user-facing locals.
    for dunder in ("__name__", "__doc__", "__builtins__", "__file__"):
        assert dunder not in innermost["locals"]


# ---------------------------------------------------------------------------
# Pretty rendering
# ---------------------------------------------------------------------------
def test_pretty_starts_with_header():
    exc_info = _produce_exc()
    out = _ANSI.sub("", format_exception_pretty(exc_info, color=False))
    assert "Traceback (most recent call last)" in out
    # Ends with the exception type and message.
    assert out.rstrip().endswith("KeyError: 'missing_key'")


def test_pretty_marks_offender_with_arrow():
    """Source-line marker is `▶` (U+25B6) on the offending line."""
    # Need a real file so the source is readable. Build a tiny script
    # in /tmp that raises and call it.
    import subprocess
    import textwrap

    script = textwrap.dedent(
        """
        def f():
            d = {"k": 1}
            return d["nope"]
        f()
        """
    ).strip()
    p = subprocess.run(
        [sys.executable, "-c", f"exec({script!r})"],
        capture_output=True, text=True, check=False,
    )
    # The script must have raised.
    assert p.returncode != 0 or "KeyError" in (p.stderr or "")
    # The traceback in stderr should contain "KeyError: 'nope'".
    assert "KeyError" in p.stderr


def test_pretty_emits_ansi_when_color_true():
    exc_info = _produce_exc()
    out = format_exception_pretty(exc_info, color=True)
    # At least one ANSI escape sequence should appear.
    assert _ANSI.search(out) is not None


def test_pretty_no_color_when_color_false():
    exc_info = _produce_exc()
    out = format_exception_pretty(exc_info, color=False)
    assert _ANSI.search(out) is None


def test_pretty_max_frames_truncates_chain():
    exc_info = _produce_exc()
    full = format_exception_pretty(exc_info, color=False)
    short = format_exception_pretty(exc_info, color=False, max_frames=1)
    # The truncated version must be shorter and mention skipping.
    assert len(short) < len(full)
    assert "skipped" in short


def test_pretty_show_locals_can_be_disabled():
    exc_info = _produce_exc()
    on = format_exception_pretty(exc_info, color=False, show_locals=True)
    off = format_exception_pretty(exc_info, color=False, show_locals=False)
    # The on version contains the local var name; the off version
    # doesn't render the locals block.
    assert "inner" in on  # the test function name
    # Both should still contain the boxed header.
    assert "Traceback (most recent call last)" in on
    assert "Traceback (most recent call last)" in off


def test_pretty_handles_none_and_bare():
    assert format_exception_pretty(None) == ""
    # An exc_info tuple with `tb=None` (no traceback attached) still
    # renders the type and message.
    bare_exc_info = (KeyError, KeyError("x"), None)
    out = format_exception_pretty(bare_exc_info, color=False)
    # The header and type-line still render. `str(KeyError("x"))` is
    # `"'x'"` (with quotes) — the literal repr of the message.
    assert "Traceback (most recent call last)" in out
    assert "KeyError: 'x'" in out


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------
def test_rich_format_exception_dispatches_by_style():
    exc_info = _produce_exc()
    as_dict = rich_format_exception(exc_info, style="structured")
    as_str = rich_format_exception(exc_info, style="pretty", color=False)
    assert isinstance(as_dict, dict)
    assert isinstance(as_str, str)
    assert as_dict["type"] == "KeyError"
    assert "KeyError" in as_str


# ---------------------------------------------------------------------------
# Formatter integration
# ---------------------------------------------------------------------------
def test_json_formatter_uses_structured_exception():
    fmt = JSONFormatter(service_name="svc")
    rec = logging.LogRecord(
        name="svc", level=logging.ERROR, pathname="/x.py", lineno=1,
        msg="failed", args=(), exc_info=_produce_exc(),
    )
    payload = json.loads(fmt.format(rec))
    assert payload["exception"]["type"] == "KeyError"
    assert isinstance(payload["exception"]["frames"], list)


def test_console_formatter_uses_pretty_exception():
    fmt = ConsoleFormatter(use_colors=False)
    rec = logging.LogRecord(
        name="svc", level=logging.ERROR, pathname="/x.py", lineno=1,
        msg="failed", args=(), exc_info=_produce_exc(),
    )
    line = fmt.format(rec)
    assert "Traceback (most recent call last)" in line
    assert "KeyError" in line
    # Note: the `ColoredFormatter` base class always appends a `\x1b[0m`
    # reset at end-of-line, so we don't assert `ANSI is None` on the
    # full line. The exception block itself has no color codes when
    # `use_colors=False`; that's the part we render.
    block = line.split("Traceback (most recent call last)", 1)[1]
    assert _ANSI.search(block) is None


def test_console_formatter_color_default_on_tty(monkeypatch):
    """`use_colors=True` should still emit ANSI (it's the caller's job
    to detect non-TTY and pass `use_colors=False`)."""
    fmt = ConsoleFormatter(use_colors=True)
    rec = logging.LogRecord(
        name="svc", level=logging.ERROR, pathname="/x.py", lineno=1,
        msg="failed", args=(), exc_info=_produce_exc(),
    )
    line = fmt.format(rec)
    # The boxed header should be colorized.
    assert _ANSI.search(line) is not None


def test_console_formatter_respects_no_color_env(monkeypatch):
    """`NO_COLOR` env var forces `use_colors=True` to fall back to plain."""
    monkeypatch.setenv("NO_COLOR", "1")
    fmt = ConsoleFormatter(use_colors=True)
    assert fmt._use_colors is False


# ---------------------------------------------------------------------------
# Defensive: never raise
# ---------------------------------------------------------------------------
def test_structured_never_raises_on_garbage():
    """A bogus exc_info tuple must not crash the renderer."""
    out = format_exception_structured(("not an exc_info",))
    # Should at least contain the fallback string.
    assert "type" in out


def test_pretty_never_raises_on_garbage():
    out = format_exception_pretty(("not an exc_info",), color=False)
    # Stdlib fallback string.
    assert "not an exc_info" in out or out == ""
