"""Tests for `@function_log` and `@class_log`."""
from __future__ import annotations

import logging
import subprocess
import sys
import textwrap
import time

import pytest

from obserlog.config import LoggerConfig
from obserlog.factory import LoggerFactory


def test_function_log_passes_through_when_no_factory():
    from obserlog.decorators.functions import function_log

    @function_log(show_args=False, show_result=False)
    def add(x, y):
        return x + y

    assert add(2, 3) == 5


def test_function_log_logs_entry_and_exit(tmp_path):
    from obserlog.decorators.functions import function_log

    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    cfg = LoggerConfig(service_name="dec-test", directory=str(tmp_path))
    f = LoggerFactory(cfg)
    try:
        # Attach our capture to the root of the factory.
        f._root.addHandler(_Capture())
        f._root.setLevel(logging.DEBUG)

        @function_log()
        def slow(x, y):
            time.sleep(0.001)
            return x + y

        assert slow(1, 2) == 3
        # Two records: entry + result.
        types = [getattr(r, "type", None) for r in captured]
        assert "Execution" in types
        assert "Result" in types
    finally:
        f.shutdown()


def test_function_log_logs_exception_and_reraises(tmp_path):
    from obserlog.decorators.functions import function_log

    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    cfg = LoggerConfig(service_name="dec-err", directory=str(tmp_path))
    f = LoggerFactory(cfg)
    try:
        f._root.addHandler(_Capture())
        f._root.setLevel(logging.DEBUG)

        @function_log()
        def boom():
            raise RuntimeError("kaboom")

        with pytest.raises(RuntimeError, match="kaboom"):
            boom()

        # Find the ERROR record. By default the message is the function
        # name only (no "Exception: ..." text) and extras only carry
        # `type` + `function`.
        errors = [r for r in captured if r.levelno == logging.ERROR]
        assert errors, "expected an ERROR log record"
        msg = errors[0].getMessage()
        assert msg == "boom failed"
        assert "Exception:" not in msg
        assert "kaboom" not in msg
        assert getattr(errors[0], "type", None) == "Error"
        assert getattr(errors[0], "function", None) == "boom"
        assert "exception" not in errors[0].__dict__
    finally:
        f.shutdown()


def test_function_log_exc_extra_fields_includes_type_and_message(tmp_path):
    from obserlog.decorators.functions import function_log

    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    cfg = LoggerConfig(service_name="dec-extra", directory=str(tmp_path))
    f = LoggerFactory(cfg)
    try:
        f._root.addHandler(_Capture())
        f._root.setLevel(logging.DEBUG)

        @function_log(exc_extra_fields=True)
        def boom():
            raise RuntimeError("kaboom")

        with pytest.raises(RuntimeError, match="kaboom"):
            boom()

        errors = [r for r in captured if r.levelno == logging.ERROR]
        assert errors
        # The minimal record (before the rich log.exception) carries the
        # type/message when exc_extra_fields is on.
        first = errors[0]
        assert getattr(first, "exc_type", None) == "RuntimeError"
        assert getattr(first, "exc_message", None) == "kaboom"
        # The record's rendered message is still the clean function-name form.
        assert first.getMessage() == "boom failed"
    finally:
        f.shutdown()


def test_function_log_log_exceptions_false_is_silent(tmp_path):
    from obserlog.decorators.functions import function_log

    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    cfg = LoggerConfig(service_name="dec-silent", directory=str(tmp_path))
    f = LoggerFactory(cfg)
    try:
        f._root.addHandler(_Capture())
        f._root.setLevel(logging.DEBUG)

        @function_log(log_exceptions=False)
        def boom():
            raise RuntimeError("kaboom")

        with pytest.raises(RuntimeError, match="kaboom"):
            boom()

        # The decorator is silent on errors. The only record is the
        # entry INFO one (which is emitted before the raise).
        errors = [r for r in captured if r.levelno == logging.ERROR]
        assert not errors
    finally:
        f.shutdown()


def test_function_log_render_rich_traceback_sets_exc_info(tmp_path):
    from obserlog.decorators.functions import function_log

    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    cfg = LoggerConfig(service_name="dec-rich", directory=str(tmp_path))
    f = LoggerFactory(cfg)
    try:
        f._root.addHandler(_Capture())
        f._root.setLevel(logging.DEBUG)

        @function_log()
        def boom():
            raise RuntimeError("kaboom")

        with pytest.raises(RuntimeError, match="kaboom"):
            boom()

        # The decorator emits two ERROR records: the minimal one and the
        # rich traceback one (log.exception -> ERROR with exc_info set).
        errors = [r for r in captured if r.levelno == logging.ERROR]
        assert len(errors) >= 2
        rich = [r for r in errors if r.exc_info]
        assert rich, "expected an ERROR record with exc_info set"
    finally:
        f.shutdown()


def test_function_log_hides_decorator_frames_by_default(tmp_path):
    """
    By default, the rich traceback emitted by the decorator must
    NOT include the wrapper's own frame. The user only sees the
    frames in their code.

    The wrapper builds a synthetic `exc_info` tuple with the
    wrapper frame unlinked, and passes that to `log.error(...)`.
    The `record.exc_info` of the resulting log record is what
    the rich renderer reads — that's what we assert on. The
    exception's own `__traceback__` is *not* mutated (bare `raise`
    would re-raise with the original chain anyway).
    """
    from obserlog.decorators.functions import function_log

    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    cfg = LoggerConfig(service_name="dec-rewind", directory=str(tmp_path))
    f = LoggerFactory(cfg)
    try:
        f._root.addHandler(_Capture())
        f._root.setLevel(logging.DEBUG)

        @function_log()
        def boom():
            raise RuntimeError("kaboom")

        with pytest.raises(RuntimeError, match="kaboom"):
            boom()

        # Find the rich traceback ERROR record (the one with exc_info set
        # and the message equal to "boom failed").
        rich_records = [
            r for r in captured
            if r.levelno == logging.ERROR and r.exc_info is not None
        ]
        assert rich_records, "expected a rich traceback ERROR record"
        rec = rich_records[0]
        # The exc_info tuple on the record should NOT include a
        # decorator frame.
        exc_info = rec.exc_info
        assert exc_info is not None
        _, _, tb = exc_info
        assert tb is not None, "rewind produced an empty traceback"
        cur = tb
        while cur is not None:
            assert "decorators/functions.py" not in cur.tb_frame.f_code.co_filename, (
                f"decorator frame leaked into rich traceback: "
                f"{cur.tb_frame.f_code.co_filename}"
            )
            cur = cur.tb_next
        # The tail of the chain should be the user's `boom` method.
        tail = tb
        while tail.tb_next is not None:
            tail = tail.tb_next
        assert tail.tb_frame.f_code.co_name == "boom", (
            f"expected tail to be 'boom', got {tail.tb_frame.f_code.co_name!r}"
        )
    finally:
        f.shutdown()


def test_function_log_show_decorator_frames_opt_in(tmp_path):
    """
    With `show_decorator_frames=True`, the wrapper's frame is
    preserved in the rich traceback's chain — useful for debugging
    the decorator itself.
    """
    from obserlog.decorators.functions import function_log

    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    cfg = LoggerConfig(service_name="dec-keep", directory=str(tmp_path))
    f = LoggerFactory(cfg)
    try:
        f._root.addHandler(_Capture())
        f._root.setLevel(logging.DEBUG)

        @function_log(show_decorator_frames=True)
        def boom():
            raise RuntimeError("kaboom")

        with pytest.raises(RuntimeError, match="kaboom"):
            boom()

        rich_records = [
            r for r in captured
            if r.levelno == logging.ERROR and r.exc_info is not None
        ]
        assert rich_records
        _, _, tb = rich_records[0].exc_info
        # Find the wrapper frame in the chain.
        saw_wrapper = False
        cur = tb
        while cur is not None:
            if cur.tb_frame.f_code.co_name == "wrapper" and \
               cur.tb_frame.f_code.co_filename.endswith("decorators/functions.py"):
                saw_wrapper = True
                break
            cur = cur.tb_next
        assert saw_wrapper, "wrapper frame should be present when show_decorator_frames=True"
    finally:
        f.shutdown()


def test_class_log_hides_decorator_frames(tmp_path):
    """
    `@class_log` should also hide the wrapper's frame, even though
    the wrapper is two levels deep (class_log → function_log).
    """
    from obserlog.decorators.classes import class_log

    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    cfg = LoggerConfig(service_name="class-rewind", directory=str(tmp_path))
    f = LoggerFactory(cfg)
    try:
        f._root.addHandler(_Capture())
        f._root.setLevel(logging.DEBUG)

        @class_log()
        class Svc:
            def boom(self):
                raise RuntimeError("kaboom")

        s = Svc()
        with pytest.raises(RuntimeError, match="kaboom"):
            s.boom()

        rich_records = [
            r for r in captured
            if r.levelno == logging.ERROR and r.exc_info is not None
        ]
        assert rich_records
        _, _, tb = rich_records[0].exc_info
        # The TAIL of the chain is the user's `boom` method.
        tail = tb
        while tail.tb_next is not None:
            tail = tail.tb_next
        assert tail.tb_frame.f_code.co_name == "boom", (
            f"expected tail to be 'boom', got {tail.tb_frame.f_code.co_name!r}"
        )
        # No decorator frame anywhere in the chain.
        cur = tb
        while cur is not None:
            filename = cur.tb_frame.f_code.co_filename
            assert "decorators/" not in filename, (
                f"decorator frame leaked: {filename}"
            )
            cur = cur.tb_next
    finally:
        f.shutdown()


def test_function_log_suppress_does_not_affect_caller_catch(tmp_path):
    from obserlog.decorators.functions import (
        _silent_excepthook,
        function_log,
        restore_default_excepthook,
    )

    cfg = LoggerConfig(service_name="dec-catch", directory=str(tmp_path))
    f = LoggerFactory(cfg)
    try:
        # Save and restore the real excepthook around this test so the
        # global side effect doesn't leak into other tests.
        real = sys.__excepthook__
        sys.excepthook = real
        try:
            @function_log()  # suppress_stdlib_traceback=True is the default
            def boom():
                raise RuntimeError("kaboom")

            with pytest.raises(RuntimeError, match="kaboom"):
                boom()

            # The silent hook is left installed (documented behavior).
            assert sys.excepthook is _silent_excepthook

            # But the caller-catch path still worked: the original
            # exception was raised and caught normally.
        finally:
            restore_default_excepthook()
    finally:
        f.shutdown()


@pytest.mark.slow
def test_function_log_suppress_stdlib_traceback_subprocess(tmp_path):
    """
    Run an unhandled-exception scenario in a subprocess and assert
    that:
    - the rich boxed traceback is printed once (via the logger),
    - the wrapper's own frame is hidden from the rich traceback,
    - the plain stdlib `Traceback (most recent call last):` print
      is suppressed on stderr.

    The default `ConsoleSettings` write to stdout with the rich
    renderer, so the `▶` markers appear in `proc.stdout`. The
    stdlib excepthook writes to stderr — that's where the
    suppression is tested.

    The script is written to a real file (not `-c`) so the source
    context is available and the rich renderer can show the
    offending line with a `▶` marker.
    """
    src_dir = "/Users/efloresp06/Documents/GitHub/Logger/src"
    script_path = tmp_path / "boom.py"
    script_path.write_text(
        textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {src_dir!r})

            from obserlog.config import LoggerConfig
            from obserlog.factory import LoggerFactory
            from obserlog.decorators.functions import function_log

            cfg = LoggerConfig(service_name='subproc', directory={str(tmp_path)!r})
            factory = LoggerFactory(cfg)

            @function_log()
            def boom():
                raise RuntimeError('kaboom')

            # Unhandled path: do NOT catch. The decorator's excepthook swap
            # should suppress the duplicated stdlib traceback on stderr.
            boom()
            """
        )
    )

    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        timeout=15,
    )

    # The unhandled exception still makes Python exit non-zero.
    assert proc.returncode != 0, (
        f"expected non-zero exit, got {proc.returncode}\n"
        f"stdout: {proc.stdout[-1000:]}\n"
        f"stderr: {proc.stderr[-1000:]}"
    )

    # The rich boxed traceback (▶ markers) appears in stdout, written
    # by the default console handler.
    assert "▶" in proc.stdout, (
        "rich renderer's ▶ marker not found in stdout:\n"
        + proc.stdout[-2000:]
    )

    # The wrapper's own frame is hidden — the rich traceback should
    # NOT mention `decorators/functions.py` or the `wrapper` function.
    assert "decorators/functions.py" not in proc.stdout, (
        "wrapper frame leaked into the rich traceback:\n"
        + proc.stdout[-2000:]
    )
    assert ", in wrapper" not in proc.stdout, (
        "wrapper function name leaked into the rich traceback:\n"
        + proc.stdout[-2000:]
    )

    # The stdlib-form header is "Traceback (most recent call last):"
    # (with a trailing colon, no box-drawing). The rich renderer uses
    # the same words but inside a `┌─ ... ─...─┐` line, so it doesn't
    # match the trailing-colon pattern. Count occurrences of the stdlib
    # form in stderr — there should be exactly zero, because the
    # decorator's excepthook swap silenced it.
    stdlib_header_lines = [
        line for line in proc.stderr.splitlines()
        if line.rstrip() == "Traceback (most recent call last):"
    ]
    assert not stdlib_header_lines, (
        "stdlib traceback leaked through (found "
        f"{len(stdlib_header_lines)} header line(s)):\n"
        + "\n".join(stdlib_header_lines)
    )


def test_class_log_wraps_public_methods(tmp_path):
    from obserlog.decorators.classes import class_log

    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    cfg = LoggerConfig(service_name="class-test", directory=str(tmp_path))
    f = LoggerFactory(cfg)
    try:
        f._root.addHandler(_Capture())
        f._root.setLevel(logging.DEBUG)

        @class_log()
        class Svc:
            def m(self, x, y):
                return x + y
            @classmethod
            def cm(cls, x, y):
                return x + y
            @staticmethod
            def sm(x, y):
                return x + y
            def _priv(self):
                return "nope"

        s = Svc()
        assert s.m(1, 2) == 3
        assert Svc.cm(1, 2) == 3
        assert s.sm(1, 2) == 3
        assert s._priv() == "nope"
        # Two records per public method call (entry + result).
        assert len(captured) >= 6
    finally:
        f.shutdown()


def test_class_log_propagates_exception_flags(tmp_path):
    """
    `@class_log` should forward the exception-handling flags to every
    method it wraps.
    """
    from obserlog.decorators.classes import class_log

    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    cfg = LoggerConfig(service_name="class-err", directory=str(tmp_path))
    f = LoggerFactory(cfg)
    try:
        f._root.addHandler(_Capture())
        f._root.setLevel(logging.DEBUG)

        @class_log(log_exceptions=False)
        class Svc:
            def boom(self):
                raise RuntimeError("kaboom")

        s = Svc()
        with pytest.raises(RuntimeError, match="kaboom"):
            s.boom()

        # With log_exceptions=False on @class_log, the decorator emits
        # no ERROR records (the entry INFO is fine).
        errors = [r for r in captured if r.levelno == logging.ERROR]
        assert not errors
    finally:
        f.shutdown()
