# obserlog

Production-grade structured logging for Python: DI factory, non-blocking queue, file rotation, RabbitMQ transport, OpenTelemetry traces, and rich exception rendering.

It gives you a single, unified API for emitting structured logs that are **traceable, sampled, and shippable** — locally to console/file, asynchronously to a queue, over RabbitMQ, or to any OpenTelemetry-compatible backend.

---

## Table of Contents

- [Why](#why)
- [Features](#features)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Core Concepts](#core-concepts)
  - [LoggerFactory (DI)](#loggerfactory-di)
  - [LoggerConfig](#loggerconfig)
  - [BoundLogger](#boundlogger)
  - [Tracer & Trace Context](#tracer--trace-context)
  - [Sampling](#sampling)
  - [Caller Resolution](#caller-resolution)
- [Architecture](#architecture)
- [Configuration Reference](#configuration-reference)
- [Handlers](#handlers)
  - [Console](#console)
  - [Rotating File](#rotating-file)
  - [RabbitMQ (sync & async)](#rabbitmq-sync--async)
- [Decorators](#decorators)
  - [`@function_log`](#function_log)
  - [`@class_log`](#class_log)
- [OpenTelemetry Integration](#opentelemetry-integration)
- [Framework Adapters](#framework-adapters)
- [End-to-End Examples](#end-to-end-examples)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Deployment](#deployment)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Why

Logs in production break for predictable reasons:

- **No structure** — grep-ing free text doesn't scale.
- **Async + threads** lose call-site context.
- **No trace correlation** — you can't link a log line to the request that produced it.
- **Hot loops spam logs** — cost and noise in the log pipeline.
- **Large codebases** need per-module control.
- **Hard to extend** with new sinks (RabbitMQ, OTel, …) without forking.

This library addresses all of these with one API and one config.

---

## Features

- **Structured JSON** output (ELK / GCP / Datadog / Splunk ready)
- **W3C trace_id / span_id** correlation via OpenTelemetry or built-in `ContextVar`
- **Non-blocking** `QueueHandler` + `QueueListener` from day one
- **Rotating file handler** (size + time) with optional gzip rollover
- **RabbitMQ transport** — sync (`pika`) and async (`aio-pika`), batched, fail-open
- **OpenTelemetry** OTLP exporter — gRPC and HTTP
- **Per-module log levels**
- **Deterministic sampling** by `(trace_id, context, message)`
- **Caller resolution** — auto `file:line Class.method()` everywhere, including inside decorators
- **DI-based factory** — no hidden global state
- **Decorators** for functions and classes
- **Async-safe** — works in `asyncio` and thread pools

---

## Installation

```bash
pip install obserlog
```

With optional transports:

```bash
pip install "obserlog[amqp]"   # RabbitMQ (pika + aio-pika)
pip install "obserlog[otel]"   # OpenTelemetry (OTLP gRPC + HTTP)
pip install "obserlog[all]"    # everything
```

From source:

```bash
git clone https://github.com/EvanFloresLv/Logger
cd obserlog
pip install -e ".[all]"
```

Requires Python 3.10+.

---

## Quickstart

```python
from obserlog import LoggerFactory, LoggerConfig

# 1. Build a config
config = LoggerConfig(
    service_name="billing-api",
    level="INFO",
    directory="logs",
    json_logs=True,
    sampling={"rate": 0.1, "deterministic": True, "min_level": "WARNING"},
    rotation={"max_bytes": 10_000_000, "backup_count": 5, "when": "midnight"},
)

# 2. Build a factory (one per process)
factory = LoggerFactory(config)

# 3. Get a bound logger
log = factory.get_logger().bind("startup")
log.info("service ready", extra={"version": "1.0.0"})

# 4. Always shut down at exit to drain the queue and close sinks
factory.shutdown()
```

Console output (colored):

```
[10:55:01] [INFO] [billing-api] [startup] - service ready
```

File output (`logs/billing-api.log`, JSON lines):

```json
{"timestamp":"2026-02-04T10:55:01.140Z","level":"INFO","message":"service ready","logger":"billing-api","service":"billing-api","context":"billing-api | startup","trace_id":"00000000000000000000000000000000","span_id":"0000000000000000","module":"app","function":"<module>","line":12,"process":1234,"thread":140123}
```

---

## Core Concepts

### LoggerFactory (DI)

`LoggerFactory` is the **only** entrypoint. You construct it with a `LoggerConfig`, ask it for a `BoundLogger`, and call `shutdown()` at the end of the process.

```python
factory = LoggerFactory(config)
log = factory.get_logger()
log2 = factory.bind(component="auth")          # shortcut
log2.set_trace()                                # new trace_id
log2.info("login attempt", extra={"user_id": 42})
factory.shutdown()
```

There is no global singleton. Two factories can coexist with different configs. Tests can build throwaway factories.

### LoggerConfig

`LoggerConfig` is a Pydantic v2 `BaseSettings`. It can be built from kwargs, from a `.env` file, or from environment variables prefixed with `LOGGER__` (double underscore for nested keys).

```python
# From kwargs
LoggerConfig(level="DEBUG", json_logs=False)

# From env
#   LOGGER__LEVEL=DEBUG
#   LOGGER__SAMPLING__RATE=0.5
#   LOGGER__AMQP__URL=amqp://prod-rabbit:5672/
```

All sub-settings are typed and validated at construction time.

### BoundLogger

A `logging.LoggerAdapter` subclass. Every method (`info`, `warning`, …) accepts an `extra={…}` dict whose fields are merged into the JSON record.

```python
log = factory.get_logger().bind(request_id="r-123")
log.info("started")
log.info("completed", extra={"duration_ms": 47})
```

`bind()` returns a *new* `BoundLogger` with the new context merged — the original is untouched. Chaining is cheap:

```python
log.bind(a=1).bind(b=2).info("x")  # both a and b are in the record
```

### Tracer & Trace Context

`factory.tracer` (or any `BoundLogger`) exposes:

```python
log.set_trace()                # generate + return a new trace_id
log.set_trace("custom-id")     # use a known id
log.set_span()

# Reading is automatic — every record carries:
#   trace_id (32 hex)
#   span_id  (16 hex)
```

If OpenTelemetry is installed and configured (`otel.enabled=True`), the logger reads the **active OTel span** from the context — so any instrumented code (DB, HTTP, gRPC) automatically correlates with your logs.

If OTel is **not** installed, the logger uses an internal `ContextVar` so the values flow through `asyncio.Tasks` and `concurrent.futures`.

### Sampling

`SamplingSettings(rate, min_level, deterministic)`:

- `rate=0.1` keeps 10% of DEBUG/INFO records.
- `min_level="WARNING"` always keeps WARNING and above (sampling is below the floor).
- `deterministic=True` hashes `(trace_id, context, message)` so the same record is consistently kept or dropped — important so a single trace is never partially sampled.

```python
config = LoggerConfig(
    sampling={"rate": 0.05, "deterministic": True, "min_level": "WARNING"}
)
```

### Caller Resolution

Every record carries `file:line Class.method()` automatically. The library uses `logging.Logger.findCaller` (stdlib-cached) and walks back through frames to enrich with the class name. Decorator wrappers and adapter methods are filtered out, so the line number and method name always point at **your** code, not the framework's.

---

## Architecture

```
                        user code
                            │
                            ▼
                 LoggerFactory.create(config)
                            │
                            ▼
                 BoundLogger (LoggerAdapter)
                  ├── .bind("ctx") → BoundLogger
                  ├── .set_trace() / .set_span()
                  └── emits via stdlib logging
                            │
                            ▼
                  ┌─────────────────────┐
                  │  QueueHandler       │  (in-memory, non-blocking)
                  │  + OverflowFilter   │
                  └──────────┬──────────┘
                             │
                             ▼
                       QueueListener
                  (single background thread)
                             │
       ┌──────────────┬───────┴────────┬──────────────┐
       ▼              ▼                ▼              ▼
  ConsoleHandler  RotatingFile    AMQPSyncHandler  AMQPAsyncHandler
  (colored)       (JSON, rotated)   (pika batch)   (aio-pika)
                                       │
                                       ▼
                                  RabbitMQ
                                       │
                                       ▼
                                OTel Collector
                                       │
                                       ▼
                              OTLPExporter (gRPC or HTTP)
                                       │
                                       ▼
                              Backend (Tempo / Jaeger / ELK)
```

Key properties:

- **One producer path** — your code only ever talks to a `QueueHandler`. Sinks are owned by a single `QueueListener` thread, so a slow file system or a dead broker never blocks the producer.
- **Console is direct** — the console handler is *not* queued, so developers see logs immediately even if a sink is broken.
- **OpenTelemetry is optional** — when enabled, it sets the global `TracerProvider` and instruments stdlib `logging`, so all records (from this library and from third-party code) carry the same `trace_id` / `span_id`.

---

## Configuration Reference

| Field | Type | Default | Notes |
|---|---|---|---|
| `service_name` | `str` | `"app"` | root logger name + OTel `service.name` |
| `level` | `str` | `"INFO"` | global level (`DEBUG`/`INFO`/…) |
| `directory` | `str` | `"logs"` | file handler root |
| `json_logs` | `bool` | `True` | structured file output |
| `date_format` | `str` | ISO 8601 ms | timestamp format |
| `module_levels` | `dict[str, str]` | `{}` | per-logger level overrides |
| `sampling.rate` | `float` | `1.0` | DEBUG/INFO sample ratio |
| `sampling.deterministic` | `bool` | `False` | hash on (trace, ctx, msg) |
| `sampling.min_level` | `str` | `"WARNING"` | never sampled below this |
| `rotation.max_bytes` | `int \| None` | `10_000_000` | size-based rotation |
| `rotation.backup_count` | `int` | `5` | retained rotated files |
| `rotation.when` | `str \| None` | `None` | time-based key (`"midnight"`, `"H"`, …) |
| `rotation.interval` | `int` | `1` | period multiplier |
| `rotation.utc` | `bool` | `False` | use UTC for time rotation |
| `rotation.compress` | `bool` | `True` | gzip rotated files |
| `queue.capacity` | `int` | `10_000` | in-memory queue size |
| `queue.overflow` | `str` | `"drop_oldest"` | `drop_oldest` / `drop_newest` / `block` |
| `queue.flush_on_exit` | `bool` | `True` | flush on `factory.shutdown()` |
| `console.enabled` | `bool` | `True` | |
| `console.colors` | `bool` | `True` | |
| `console.destination` | `str` | `"stdout"` | `"stdout"` or `"stderr"` |
| `amqp` | `AMQPSettings \| None` | `None` | RabbitMQ sink (see below) |
| `otel` | `OTelSettings` | disabled | OTel exporter (see below) |

Environment variable mapping (double underscore = nested key):

```bash
export LOGGER__SERVICE_NAME=billing-api
export LOGGER__LEVEL=DEBUG
export LOGGER__SAMPLING__RATE=0.1
export LOGGER__SAMPLING__DETERMINISTIC=true
export LOGGER__AMQP__URL=amqp://prod-rabbit:5672/
export LOGGER__AMQP__TRANSPORT=async
export LOGGER__OTEL__ENABLED=true
export LOGGER__OTEL__PROTOCOL=grpc
export LOGGER__OTEL__OTLP_ENDPOINT=http://otel-collector:4317
```

---

## Handlers

### Console

Always-on, immediate, colored. Honors `console.destination` so you can route WARNING+ to stderr if you want.

### Rotating File

- **Size-based** when `rotation.when is None` (default) — `RotatingFileHandler` semantics.
- **Time-based** when `rotation.when` is set — `TimedRotatingFileHandler` semantics.
- `rotation.compress=True` gzips rolled files on rollover.

Output is one JSON object per line. The file is named `<directory>/<service_name>.log`.

### RabbitMQ (sync & async)

```python
config = LoggerConfig(
    amqp={
        "url": "amqp://guest:guest@localhost/",
        "exchange": "logs",
        "exchange_type": "fanout",   # direct | topic | fanout | headers
        "routing_key": "",
        "queue": "logs",
        "durable": True,
        "batch_size": 100,
        "flush_interval_s": 1.0,
        "transport": "sync",         # or "async" (aio-pika)
        "fail_open": True,           # degrade to file when broker is down
        "connect_timeout_s": 5.0,
        "max_retries": 5,
    }
)
```

- **Sync** uses `pika.BlockingConnection` with a batched publish loop. Best for worker processes, scripts, CLIs.
- **Async** uses `aio-pika` and is safe to use from an event loop. Best for `asyncio` services.

Both handlers serialize records as JSON, batch up to `batch_size` records or `flush_interval_s` seconds, and flush on close. Connection failures with `fail_open=True` log a single stderr warning and continue with the file handler.

A consumer example lives in [`examples/rabbitmq_consumer.py`](examples/rabbitmq_consumer.py).

---

## Decorators

### `@function_log`

```python
from obserlog.decorators import function_log

@function_log(show_args=False, show_result=False)
def add(x, y):
    return x + y
```

Logs `Executing` and `Finished` entries with timing, the calling module, the function name, and (if present) the enclosing class. Decorator overhead is negligible — `inspect.getmodule` is cached and the resolved context is reused.

#### Exception handling

When the decorated function raises, the decorator emits a minimal `ERROR` record (message is the function name, `extras` carries `{"type": "Error", "function": ...}`), renders the rich boxed `▶` traceback once, and suppresses the duplicated stdlib `Traceback (most recent call last):` print to stderr. The original exception still propagates, so the caller's `try/except` works and the process exits non-zero on unhandled failures — no `try/except` wrapper is needed at the call site:

```python
@function_log(show_args=False, show_result=False)
def divide(x, y):
    return x / y

# No try/except — the decorator renders the rich traceback, the
# exception still propagates, exit code is 1.
divide(5, 0)
```

All exception-handling flags are explicit, per-decorator:

| Flag | Default | Behavior |
|---|---|---|
| `log_exceptions` | `True` | Emit a log record at all on exception. Set to `False` to make the decorator completely silent on errors. |
| `exc_extra_fields` | `False` | Include `exc_type` / `exc_message` in the `extras` dict. The rich boxed traceback already includes them, so this is off by default. |
| `render_rich_traceback` | `True` | Also emit `log.exception(...)` so the rich boxed `▶` traceback renders even without a `try/except` at the call site. |
| `suppress_stdlib_traceback` | `True` | Install a silent `sys.excepthook` and re-raise, so the stdlib `Traceback (most recent call last):` print is suppressed on unhandled exceptions. The hook swap is process-global; call `restore_default_excepthook()` to undo it. |
| `show_decorator_frames` | `False` | Hide the decorator's own wrapper frame from the rich traceback. The user only sees frames inside their own code. Set to `True` to keep the wrapper frame (useful when debugging the decorator). |

```python
from obserlog.decorators import function_log

# Quiet mode: caller is fully responsible for logging.
@function_log(log_exceptions=False, render_rich_traceback=False)
def f(): ...

# Restore the stdlib excepthook if a previous decorated call left
# the silent hook installed.
from obserlog.decorators.functions import restore_default_excepthook
restore_default_excepthook()
```

### `@class_log`

```python
from obserlog.decorators import class_log

@class_log()
class OrderService:
    def place(self, order): ...
    @classmethod
    def from_dict(cls, raw): ...
    @staticmethod
    def _validate(order): ...   # private — skipped
```

Wraps every **public** callable (instance / classmethod / staticmethod) with `function_log`. Private names (starting with `_`) are skipped. The decorator is `__slots__`- and frozen-class-safe: if `setattr` fails, a `RuntimeWarning` is emitted and that method is left untouched. The same exception-handling flags from `@function_log` are forwarded to every method it wraps:

```python
@class_log(
    render_rich_traceback=True,
    suppress_stdlib_traceback=True,
    show_decorator_frames=False,
)
class Service:
    def may_fail(self): ...
```

---

## OpenTelemetry Integration

```python
config = LoggerConfig(
    service_name="billing-api",
    otel={
        "enabled": True,
        "otlp_endpoint": "http://otel-collector:4317",   # gRPC
        "protocol": "grpc",                              # or "http"
        "http_endpoint": "http://otel-collector:4318",   # used when protocol="http"
        "insecure": True,
        "sample_ratio": 0.1,
        "headers": {"x-api-key": "..."},
    },
)
```

When `otel.enabled=True`, the factory:

1. Creates a `TracerProvider` with a `Resource` of `service.name=<service_name>`.
2. Installs a `BatchSpanProcessor` pointing at the chosen OTLP exporter (gRPC port 4317, HTTP port 4318 by default).
3. Applies `TraceIdRatioBased(sample_ratio)`.
4. Calls `LoggingInstrumentor().instrument(set_logging_format=False)` so any log emitted through stdlib `logging` (third-party libs included) also gets the active `trace_id` / `span_id`.

After this, **every** log line — yours and from any library — carries the same `trace_id` and `span_id` as the active span, formatted as 32-hex / 16-hex per W3C TraceContext.

A minimal local stack (Collector + Jaeger) is in [`docker-compose.yml`](docker-compose.yml).

---

## Framework Adapters

### FastAPI

```python
from fastapi import FastAPI, Request
from obserlog import LoggerFactory, LoggerConfig

factory = LoggerFactory(LoggerConfig(
    service_name="api",
    otel={"enabled": True, "otlp_endpoint": "http://otel-collector:4317", "protocol": "grpc"},
))
app = FastAPI(lifespan=factory.lifecycle)

@app.middleware("http")
async def access_log(request: Request, call_next):
    log = factory.get_logger().bind(path=request.url.path, method=request.method)
    log.set_trace()
    log.set_span()
    start = time.perf_counter()
    response = await call_next(request)
    log.info("request", extra={
        "type": "access",
        "status": response.status_code,
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
    })
    return response
```

`factory.lifecycle` is an `asynccontextmanager` that calls `factory.shutdown()` on app exit.

---

## End-to-End Examples

### 1. Local development (console + file)

```python
from obserlog import LoggerFactory, LoggerConfig

factory = LoggerFactory(LoggerConfig(service_name="dev", level="DEBUG"))
log = factory.get_logger().bind(component="auth")
log.debug("checking token")
log.info("user logged in", extra={"user_id": 42})
log.error("db error", extra={"query": "SELECT ..."})
factory.shutdown()
```

### 2. Production with OTel + RabbitMQ

```python
from obserlog import LoggerFactory, LoggerConfig

factory = LoggerFactory(LoggerConfig(
    service_name="billing",
    level="INFO",
    json_logs=True,
    rotation={"max_bytes": 50_000_000, "backup_count": 10, "when": "midnight"},
    amqp={
        "url": "amqp://rabbit:5672/",
        "exchange": "logs.fanout",
        "queue": "billing-logs",
        "transport": "async",
    },
    otel={
        "enabled": True,
        "otlp_endpoint": "http://otel-collector:4317",
        "protocol": "grpc",
        "sample_ratio": 0.1,
    },
))

log = factory.get_logger().bind(component="invoice")
with factory.tracer.start_span("create-invoice") as span:
    span.set_attribute("invoice.id", "inv-123")
    log.info("invoice created", extra={"amount": 999.0})
factory.shutdown()
```

### 3. With decorators

```python
from obserlog import LoggerFactory, LoggerConfig
from obserlog.decorators import function_log, class_log

factory = LoggerFactory(LoggerConfig(service_name="orders"))

@class_log()
class OrderService:
    def place(self, order):
        ...

@function_log(show_args=False)
def notify(order_id):
    ...

svc = OrderService()
svc.place({"id": 1})
notify(1)
factory.shutdown()
```

---

## Project Structure

```
src/
├── __init__.py                       # Public API re-exports
├── errors.py                         # Exception hierarchy (renamed from exceptions.py)
├── exceptions.py                     # Backwards-compat shim → errors.py
├── config/                           # Settings models
│   ├── __init__.py
│   ├── logger_config.py              # LoggerConfig (top-level)
│   ├── config.py                     # Backwards-compat shim
│   └── settings/
│       ├── sampling.py               # SamplingSettings
│       ├── rotation.py               # RotationSettings
│       ├── queue.py                  # QueueSettings
│       ├── console.py                # ConsoleSettings
│       ├── amqp.py                   # AMQPSettings
│       └── otel.py                   # OTelSettings
├── core/
│   ├── tracer.py                     # OTel + ContextVar facade
│   ├── context.py                    # BoundLogger
│   ├── caller.py                     # frame-walking caller resolution
│   ├── filters/
│   │   ├── sampling.py               # SamplingFilter, DeterministicSamplingFilter
│   │   └── overflow.py               # OverflowFilter, QueueCapacityProbe
│   ├── formatters/
│   │   ├── json_formatter.py         # stable JSON for files / structured sinks
│   │   └── colored_formatter.py      # colored console output
│   └── transport/
│       ├── serialize.py              # record_to_json_bytes() — single source of truth
│       └── batch.py                  # BatchBuffer — sync thread-safe buffer
├── handlers/
│   ├── console.py                    # immediate colored handler
│   ├── queue.py                      # QueueHandler + QueueListener pipeline
│   ├── rotating_file.py              # size + time + gzip (GzipOnRolloverMixin)
│   └── amqp/                         # AMQP transport package
│       ├── __init__.py
│       ├── common.py                 # serialize_record + settings validation
│       ├── sync.py                   # AMQPSyncHandler (pika)
│       ├── async_handler.py          # AMQPAsyncHandler (aio-pika + drain barrier)
│       ├── async_loop.py             # LoopRunner — dedicated event-loop thread
│       └── factory.py                # make_amqp_handler dispatch
├── factory/                          # DI entrypoint package
│   ├── __init__.py
│   ├── logger_factory.py             # LoggerFactory class
│   ├── registry.py                   # active-factory registry
│   ├── builder.py                    # build_handlers(config) → HandlerPlan
│   └── factory.py                    # Backwards-compat shim
├── integrations/
│   └── opentelemetry/                # OTel integration package
│       ├── __init__.py
│       ├── provider.py               # configure_opentelemetry()
│       └── exporter.py               # OTLPSettingsAdapter (gRPC / HTTP)
└── decorators/
    ├── __init__.py
    ├── base.py                       # active_factory(), build_context_string()
    ├── functions.py                  # @function_log
    └── classes.py                    # @class_log
```

---

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

The test suite is split into `tests/unit` (fast, no external services) and `tests/integration` (RabbitMQ + OTel collector via `testcontainers`).

```bash
RUN_INTEGRATION=1 pytest tests/integration -v
```

---

## Deployment

The library is a pure-Python package with optional extras. It runs anywhere CPython 3.10+ runs:

- **Python SDK library** — `pip install obserlog[all]`
- **FastAPI / Flask / Starlette** — use the lifespan example above
- **Serverless** — Cloud Run / AWS Lambda / Azure Functions. Configure with `directory="/tmp/logs"` and set `rotation.when=None` (no time rotation) since the filesystem is ephemeral.
- **Workers / CLIs** — `factory.shutdown()` at the end of `main()`.

---

## Roadmap

- Pluggable sinks via entry-points (Datadog, Loki, CloudWatch)
- A `LogQL`/`Grok` examples page
- A `structlog` adapter for users who want to keep that API
- Built-in PII redaction filters

---

## Contributing

PRs welcome. Please run `ruff check`, `mypy src/obserlog`, and `pytest` before submitting. Add tests for new behavior.

---

## License

MIT — see [`LICENSE`](LICENSE).

---

