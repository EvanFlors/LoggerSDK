"""Tests for `config.LoggerConfig` and the per-feature settings models."""
from __future__ import annotations

import logging

import pytest

from src.config import LoggerConfig
from src.config.settings.amqp import AMQPSettings
from src.config.settings.otel import OTelSettings
from src.config.settings.sampling import SamplingSettings


def test_default_config_is_valid():
    cfg = LoggerConfig()
    assert cfg.service_name == "app"
    assert cfg.level == "INFO"
    assert cfg.numeric_level() == logging.INFO
    assert cfg.amqp is None
    assert isinstance(cfg.sampling, SamplingSettings)


def test_level_is_coerced_to_uppercase():
    cfg = LoggerConfig(level="debug")
    assert cfg.level == "DEBUG"
    assert cfg.numeric_level() == logging.DEBUG


def test_invalid_level_raises():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        LoggerConfig(level="NOPE")


def test_amqp_optional():
    cfg = LoggerConfig(amqp=None)
    assert cfg.amqp is None


def test_amqp_dict_coerced_to_settings():
    cfg = LoggerConfig(amqp={"url": "amqp://x:1/", "transport": "async"})
    assert isinstance(cfg.amqp, AMQPSettings)
    assert cfg.amqp.transport == "async"
    assert cfg.amqp.url == "amqp://x:1/"


def test_otel_settings_default_disabled():
    cfg = LoggerConfig()
    assert isinstance(cfg.otel, OTelSettings)
    assert cfg.otel.enabled is False


def test_env_var_override(monkeypatch):
    # Top-level fields use the env_prefix directly: `LOGGER_<FIELD>`.
    # Nested fields use the double-underscore delimiter.
    monkeypatch.setenv("LOGGER_SERVICE_NAME", "from-env")
    monkeypatch.setenv("LOGGER_LEVEL", "WARNING")
    cfg = LoggerConfig(_env_file=None)
    assert cfg.service_name == "from-env"
    assert cfg.level == "WARNING"
