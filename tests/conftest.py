import pytest
from pathlib import Path
from config import LoggerConfig

@pytest.fixture
def tmp_logs_dir(tmp_path: Path) -> Path:
    d = tmp_path / "logs"
    d.mkdir()
    return d

@pytest.fixture
def base_config(tmp_logs_dir: Path) -> LoggerConfig:
    return LoggerConfig(service_name="test", directory=str(tmp_logs_dir))

@pytest.fixture
def in_memory_otel_exporter():
    try:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    except ImportError:
        pytest.skip("OpenTelemetry SDK is not installed")
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider = TracerProvider()
    provider.add_span_processor(processor)

    return provider