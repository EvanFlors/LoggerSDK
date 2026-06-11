"""Tests for `@function_log` and `@class_log`."""
from __future__ import annotations

import logging
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

    cfg = LoggerConfig(service_name="dec-err", directory=str(tmp_path))
    f = LoggerFactory(cfg)
    try:
        @function_log()
        def boom():
            raise RuntimeError("kaboom")

        with pytest.raises(RuntimeError, match="kaboom"):
            boom()
    finally:
        f.shutdown()


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
