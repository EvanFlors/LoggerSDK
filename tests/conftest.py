"""
Shared pytest fixtures.

The tests assume `src/` is on `sys.path` so that
`import obserlogger` works. `pytest.ini` is configured for that,
but the conftest also adds the path explicitly for IDEs and
editors that invoke pytest with different working directories.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make `obserlogger` importable no matter where pytest is invoked from.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _REPO_ROOT / "src"
for path in (_REPO_ROOT, _SRC_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture
def tmp_logs_dir(tmp_path: Path) -> Path:
    d = tmp_path / "logs"
    d.mkdir()
    return d


@pytest.fixture
def base_config(tmp_logs_dir: Path):
    from obserlog.config import LoggerConfig
    return LoggerConfig(service_name="test", directory=str(tmp_logs_dir))


@pytest.fixture
def in_memory_otel_exporter():
    try:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )
    except ImportError:
        pytest.skip("OpenTelemetry SDK is not installed")
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider = TracerProvider()
    provider.add_span_processor(processor)
    return provider
