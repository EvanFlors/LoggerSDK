# Changelog

All notable changes to **obserlog** are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [0.1.0] — 2026-06-11

First public release on PyPI. This is the same code that lived
in `github.com/EvanFloresLv/Logger`, rebranded and packaged as
**obserlog** (the original name `obserlogger` was already taken
on PyPI).

### Added

- **DI-based `LoggerFactory`**: no global singletons, multiple
  factories can coexist in one process, test-friendly.
- **Non-blocking `QueueHandler` + `QueueListener`** with
  `OverflowFilter` for back-pressure (drop_oldest / drop_newest /
  block policies).
- **Rotating file handler**: size-based and time-based rotation,
  optional gzip rollover via the `GzipOnRolloverMixin`.
- **RabbitMQ transport**:
  - `AMQPSyncHandler` using `pika` (BlockingConnection, batched).
  - `AMQPAsyncHandler` using `aio-pika` with a dedicated
    event-loop thread, a single long-running consumer
    coroutine, and a drain-barrier event so `close()` never
    has to drain thousands of pending coroutines.
  - `fail_open=True` by default — broker outages log a single
    stderr warning and continue with the file handler.
- **OpenTelemetry integration**: gRPC and HTTP OTLP exporters,
  `LoggingInstrumentor` for stdlib-`logging` correlation,
  `Tracer` facade with `ContextVar` fallback when OTel is not
  installed.
- **Rich exception rendering** (`src/obserlog/core/exception_render.py`):
  boxed traceback (structlog-style), source code with the
  offending line marked by `▶`, locals block per frame. Honors
  the `NO_COLOR` env var. Falls back to plain `traceback`
  on any internal failure so the user never sees a broken
  traceback.
- **Decorators**: `@function_log` and `@class_log` (which wraps
  every public callable of a class).
- **Pydantic v2 `LoggerConfig`** with nested settings models
  (`SamplingSettings`, `RotationSettings`, `QueueSettings`,
  `ConsoleSettings`, `AMQPSettings`, `OTelSettings`) and env
  variable loading (`LOGGER__SERVICE_NAME=…`,
  `LOGGER__OTEL__ENDPOINT=…`).
- **W3C trace_id / span_id** propagation: every log record carries
  a 32-hex trace_id and 16-hex span_id, sourced from OTel when
  available and from an internal `ContextVar` otherwise.

### Fixed

- `SamplingFilter` level guard was inverted (`<` instead of `>=`).
  Records at or above `min_level` were being dropped, the
  opposite of the documented behavior. A regression test
  (`test_sampling_keeps_records_at_or_above_min_level`) prevents
  re-introduction.
- `JSONFormatter` was double-formatting the timestamp, causing
  `AttributeError: 'str' object has no attribute 'strftime'`.
- `AMQPAsyncHandler.flush` was returning an unawaited coroutine
  because `flush()` was `async def` — `logging.Handler.flush`
  must be sync per stdlib's contract. Replaced with a sync
  `flush()` that delegates to a sync `flush_sync()`.
- `AMQPAsyncHandler` was being constructed with a dead
  `asyncio.new_event_loop()` that no thread ever ran. The handler
  now owns a dedicated loop running in a daemon thread
  (`LoopRunner`).

### Changed

- Package renamed from `Logger` (the project) to `obserlog`
  (the distribution). The importable name is now
  `obserlog` everywhere; `from src.xxx` → `from obserlog.xxx`.
- The internal module layout went from a flat `src/` to
  `src/obserlog/` (a proper importable package). Each top-level
  subpackage (`core`, `factory`, `handlers`, `config`,
  `integrations`, `decorators`) is now a real directory.
- `AMQPSettings.fail_open` defaults to `True`. A broker outage
  is no longer fatal.
- The OTel collector is no longer required for the demo:
  Jaeger's built-in OTLP receiver (gRPC :4317) is enough.
  The bundled `docker-compose.yml` was simplified accordingly.
- `caller.py`: the dead frame cache (which was never read) was
  removed. Frame walking is now ~5µs per log call.
- `OverflowFilter`: the dynamic-attribute trick
  (`_size.capacity = ...`) was replaced with a typed
  `QueueCapacityProbe` dataclass.

### Backwards compatibility

The public API is the same as the previous `Logger` branding:

- `from obserlog import LoggerFactory, LoggerConfig, BoundLogger, Tracer`
- `@function_log`, `@class_log` decorators
- `LoggerConfig(amqp=AMQPSettings(...), otel=OTelSettings(...))` shape

Old `from src.xxx` imports are gone. If you have a downstream
project that did `from src.xxx`, replace it with `from obserlog.xxx`.

---

## Release checklist (for maintainers)

Before tagging a release:

- [ ] All tests green: `pytest tests/unit`
- [ ] Lint clean: `ruff check src tests`
- [ ] mypy clean: `mypy src tests`
- [ ] Build artifacts present: `python -m build` produces
      `dist/obserlog-X.Y.Z-py3-none-any.whl` and `dist/obserlog-X.Y.Z.tar.gz`
- [ ] Name still free on PyPI: `curl -s https://pypi.org/simple/obserlog/`
- [ ] Smoke-test from a fresh venv:
      `pip install dist/obserlog-X.Y.Z-py3-none-any.whl` and
      `python -c "import obserlog; print(obserlog.LoggerFactory)"`
- [ ] Tag the release: `git tag -a vX.Y.Z -m "..."`
- [ ] Upload: `twine upload dist/*` (TestPyPI first if it's a
      pre-release).
