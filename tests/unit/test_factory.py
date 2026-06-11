"""Tests for the factory."""
from __future__ import annotations

import pytest

from obserlog.config import LoggerConfig
from obserlog.errors import ShutdownError
from obserlog.factory import LoggerFactory


def test_factory_constructs_and_creates_logger(tmp_path):
    cfg = LoggerConfig(service_name="factory-test", directory=str(tmp_path))
    f = LoggerFactory(cfg)
    try:
        log = f.get_logger()
        assert log is not None
        log.info("hi")
    finally:
        f.shutdown()


def test_factory_shutdown_is_idempotent():
    f = LoggerFactory(LoggerConfig(service_name="idem", directory="/tmp"))
    f.shutdown()
    f.shutdown()  # no error


def test_factory_get_logger_after_shutdown_raises():
    f = LoggerFactory(LoggerConfig(service_name="after", directory="/tmp"))
    f.shutdown()
    with pytest.raises(ShutdownError):
        f.get_logger()


def test_factory_context_manager(tmp_path):
    cfg = LoggerConfig(service_name="ctx", directory=str(tmp_path))
    with LoggerFactory(cfg) as f:
        log = f.get_logger()
        log.info("from context")
    with pytest.raises(ShutdownError):
        f.get_logger()


def test_factory_publishes_to_registry():
    from obserlog.factory.registry import active

    before = active()
    f = LoggerFactory(LoggerConfig(service_name="reg", directory="/tmp"))
    try:
        assert active() is f
    finally:
        f.shutdown()
    assert active() is before
