# Logger Framework Source Code Documentation

This document provides a comprehensive line-by-line explanation of the logging framework's source code, showing relationships between files and how components work together.

## High-Level Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           LoggerFactory                                    │
│  (Composition Root - DI Container)                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Root Logger (no propagation)                                       │   │
│  │  ├── Console Handler (immediate, colored)                           │   │
│  │  │        │                                                         │   │
│  │  │        ▼ (user sees immediately)                                 │   │
│  │  │   stdout/stderr                                                  │   │
│  │  │                                                                  │   │
│  │  └── QueueHandler (deferred)                                        │   │
│  │       │                                                             │   │
│  │       ▼                                                             │   │
│  │   Queue (thread-safe)                                               │   │
│  │       │                                                             │   │
│  │       ▼                                                             │   │
│  │  QueueListener Thread                                               │   │
│  │       │                                                             │   │
│  │       ├──► RotatingFileHandler (JSON, sampled)                      │   │
│  │       │                                                             │   │
│  │       └──► AMQP Handler (sync/async)                                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  BoundLogger (LoggerAdapter)                                               │
│  ├── bind(**fields) - Add context to logger                                │
│  ├── set_trace() / set_span() - Set tracing IDs                            │
│  └── process() - Injects trace_id, span_id, context into every record      │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  Tracer (supports dual mode)                                               │
│  ├── OpenTelemetry mode: reads from OTel context                           │
│  └── Standalone mode: uses ContextVars                                     │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Core Components (`src/core/`)

### 1.1 `src/core/context.py` - BoundLogger

This is the primary logger interface that users interact with. It's a `LoggerAdapter` that automatically injects trace context into every log record.

```python
1: from __future__ import annotations
```

Postpones type hint evaluation to avoid circular import issues and allows forward references.

```python
3: import logging
4: from typing import Any
```

Imports the standard logging module and typing utilities.

```python
5: from src.core.caller import resolve_caller
6: from src.core.tracer import Tracer
```

Imports resolve_caller (for getting caller info) and Tracer (for trace IDs).

```python
10: class BoundLogger(logging.LoggerAdapter):
11:     """
12:     LoggerAdapter that injects trace_id, span_id, context and any bound fields
13:     into every log record. Created via `LoggerFactory.get_logger().bind(...)`.
14:     """
```

**Purpose**: Extends Python's `LoggerAdapter` to inject trace context automatically into every log record. This is the main interface users interact with.

```python
16:     def __init__(self, logger: logging.Logger, extra: dict[str, Any], tracer: Tracer) -> None:
17:         super().__init__(logger, extra)
18:         self._tracer = tracer
```

**Parameters**:
- `logger`: The underlying Python logger
- `extra`: Bound fields to include in every log
- `tracer`: Tracer instance for getting trace_id/span_id

The constructor calls the parent LoggerAdapter constructor and stores the tracer reference.

```python
20:     def bind(self, **fields: Any) -> BoundLogger:
21:         merged = {**self.extra, **fields}  # type: ignore[dict-item]
22:         return BoundLogger(self.logger, merged, self._tracer)
```

Creates a new BoundLogger with additional fields merged in. This allows creating contextual loggers:

```python
# Usage:
logger = factory.get_logger()
payment_logger = logger.bind(request_id="abc123", user_id="user1")
payment_logger.info("Payment processed")  # Includes request_id and user_id in every log
```

The bind method merges the existing bound fields with new ones and returns a new BoundLogger instance.

```python
24:     def set_trace(self, trace_id: str | None = None) -> str:
25:         return self._tracer.set_trace(trace_id)
```

Sets the current trace ID. If None is provided, generates a new UUID. Returns the trace ID that was set.

```python
27:     def set_span(self, span_id: str | None = None) -> str:
28:         return self._tracer.set_span(span_id)
```

Sets the current span ID. If None is provided, generates a short UUID (16 hex chars). Returns the span ID that was set.

```python
30:     def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
31:         call_extra = kwargs.get("extra")
32:         if not isinstance(call_extra, dict):
33:             call_extra = {}
34:         merged = {**self.extra, **call_extra}  # type: ignore[dict-item]
35:         merged.setdefault("trace_id", self._tracer.current_trace_id())
36:         merged.setdefault("span_id", self._tracer.current_span_id())
37:         if "context" not in merged:
38:             caller = resolve_caller()
39:             merged["context"] = f"{self.logger.name} | {caller.render()}"
40:         kwargs["extra"] = merged
41:         return msg, kwargs
```

**This is the heart of the logging system**. Every log call goes through `process()`:

1. **Lines 31-33**: Merge extra fields from both bound fields and call-time extra
2. **Lines 35-36**: Inject trace_id and span_id (defaults to zeros if not set)
3. **Lines 37-39**: If no context provided, resolve the caller's location (file:line function())
4. **Line 40**: Attach the merged context to kwargs["extra"]

The process method is called by Python's logging framework before any handler processes the record. This is where all the magic happens - trace IDs, span IDs, and context are injected into every log record automatically.

---

### 1.2 `src/core/tracer.py` - Tracer

Provides trace/span context management with dual-mode support (OpenTelemetry or standalone).

```python
1: """
2: Trace/span facade.
3:
4: Two modes:
5:
6: - **OpenTelemetry mode** (when `OTelSettings.enabled=True` and the OTel
7:   packages are installed): the active span from the global OTel
8:   `TracerProvider` is the source of truth.
9:
10: - **Standalone mode** (no OTel): two `ContextVar`s — `_trace_var` and
11:   `_span_var` — carry the ids.
12: """
```

This dual-mode design allows the same API to work with or without OpenTelemetry. The tracer provides a consistent interface for getting and setting trace/span IDs regardless of whether OpenTelemetry is available.

```python
19: from __future__ import annotations
20:
21: import uuid
22: from contextvars import ContextVar
23: from typing import Any
```

**Key imports**: ContextVar for thread-safe async/threading context storage, uuid for generating IDs.

```python
27: _trace_var: ContextVar[str | None] = ContextVar("logger_trace_id", default=None)
28: _span_var: ContextVar[str | None] = ContextVar("logger_span_id", default=None)
```

**Thread-safe context storage**: ContextVars work correctly across threads and async contexts, unlike thread-local storage. Each ContextVar is independent and maintains its value separately for each context (thread/coroutine).

```python
30: _NO_TRACE = "0" * 32
31: _NO_SPAN = "0" * 16
```

Default values when no trace/span is active. Trace IDs are 32 hex characters (16 bytes), span IDs are 16 hex characters (8 bytes), following W3C trace context specification.

```python
34: class _NoopSpan:
35:     """Returned by `Tracer.start_span` when OTel is not available."""
36:
37:     def __enter__(self) -> _NoopSpan:
38:         return self
39:
40:     def __exit__(self, *args: Any) -> None:
41:         return None
42:
43:     def set_attribute(self, *a: Any, **kw: Any) -> None:
44:         return None
45:
46:     def set_status(self, *a: Any, **kw: Any) -> None:
47:        return None
```

No-op span returned when OTel is disabled. Allows code to use `start_span()` without checking if OTel is enabled. This is a Null Object pattern implementation.

```python
53: class Tracer:
56:     def __init__(self, settings: OTelSettings) -> None:
57:         self._settings = settings
58:         self._otel_tracer: Any = None
59:         if settings.enabled:
60:             self._init_otel()
```

**Initialization**: If OTel is enabled in settings, initialize OpenTelemetry integration. Otherwise, remains in standalone mode.

```python
62:     def _init_otel(self) -> None:
63:         try:
64:             from src.integrations.opentelemetry import configure_opentelemetry
65:             configure_opentelemetry(self._settings, self._settings.service_name or "")
66:             from opentelemetry import trace
67:             self._otel_tracer = trace.get_tracer("logger")
68:         except Exception:
69:             # OTel is optional; if anything goes wrong we silently
70:             # downgrade to ContextVar mode.
71:             self._otel_tracer = None
```

**Graceful degradation**: If OTel initialization fails (package not installed, connection issues, etc.), fall back to standalone ContextVar mode. This ensures the logger works even without OTel.

```python
77:     def current_trace_id(self) -> str:
78:         if self._otel_tracer is not None:
79:             ctx = self._otel_span_context()
80:             if ctx is not None and ctx.is_valid:
81:                 return f"{ctx.trace_id:032x}"
82:         return _trace_var.get() or _NO_TRACE
```

**Read trace ID**: First tries OTel context (if available), then falls back to ContextVar. Formats the ID as a 32-character hex string (zero-padded).

```python
84:     def current_span_id(self) -> str:
85:         if self._otel_tracer is not None:
86:             ctx = self._otel_span_context()
87:             if ctx is not None and ctx.is_valid:
88:                 return f"{ctx.span_id:016x}"
89:         return _span_var.get() or _NO_SPAN
```

Same pattern for span ID - 16-character hex string.

```python
100:    def set_trace(self, trace_id: str | None = None) -> str:
101:        tid = trace_id or uuid.uuid4().hex
102:        _trace_var.set(tid)
103:        return tid
```

**Set trace ID**: Uses provided ID or generates UUID if not provided. Sets the value in the ContextVar for the current context.

```python
105:    def set_span(self, span_id: str | None = None) -> str:
106:        sid = span_id or uuid.uuid4().hex[:16]
107:        _span_var.set(sid)
108:        return sid
```

**Set span ID**: Uses provided ID or generates 16-character hex string. Span IDs don't need full UUID uniqueness, so a shorter string is used.

```python
118:    def start_span(self, name: str, **attrs: Any) -> Any:
119:        if self._otel_tracer is None:
120:            return _NoopSpan()
121:        return self._otel_tracer.start_as_current_span(name, attributes=attrs)
```

**Start span**: Returns OTel span context manager or no-op if OTel not available. This allows code to create spans without checking the OTel state.

---

### 1.3 `src/core/caller.py` - Caller Resolution

Walks back the call stack to find the actual user's call site, skipping stdlib logging and internal modules.

```python
1: """
2: Frame-walking caller resolution.
3:
4: Walks back from the current frame to find the user's call site, skipping
5: the stdlib `logging` module and this package's own modules.
6: """
```

**Purpose**: Provides context about where in user code a log call originated. This helps developers understand where logs come from in their codebase.

```python
24: _SKIP_NAMES: frozenset[str] = frozenset({
25:     "process", "_log", "log", "debug", "info", "warning", "warn",
26:     "error", "exception", "critical", "fatal", "emit", "handle",
27:     "callHandlers", "handleError", "findCaller", "_log_recursion_lock",
28: })
```

Function names that indicate stdlib logging internals - these are skipped during frame walk. These are all internal functions in Python's logging module.

```python
30: _SKIP_PATHS: tuple[str, ...] = ("/logging/__init__.py", "/logging/")
```

Path patterns for stdlib logging module - frames from these paths are skipped. Any file path containing these strings is considered internal.

```python
35: _THIS_PKG = os.path.dirname(os.path.abspath(__file__))
36: _SKIP_PATHS = (*_SKIP_PATHS, _THIS_PKG)
```

Also skip this package's own frames by adding the package directory to skip paths. This ensures the frame walk stops at user code, not internal logging code.

```python
39: @dataclass(frozen=True)
40: class CallerInfo:
41:     file: str
42:     line: int
43:     func: str
44:     qualname: str
45:
46:     def render(self) -> str:
47:         return f"{self.file}:{self.line} {self.qualname}()"
```

Immutable dataclass (frozen=True) holding caller information. The render method creates a formatted string like "main.py:42 MyClass.method()".

```python
50: def _class_from_frame(frame: FrameType) -> str | None:
51:     self_obj = frame.f_locals.get("self")
52:     if self_obj is not None and hasattr(self_obj, "__class__"):
53:         cls = self_obj.__class__
54:        return cls.__name__
55:     cls = frame.f_locals.get("cls")
56:     if isinstance(cls, type):
57:         return cls.__name__
58:    return None
```

Extracts class name from frame's local variables. Handles both instance methods (checks "self") and class methods (checks "cls"). Returns the class name or None if not a method.

```python
71: def resolve_caller() -> CallerInfo:
72:    """Walk back from this function's caller to the first user frame."""
73:    try:
74:        frame: FrameType | None = sys._getframe(1)
75:        while frame is not None:
76:            code = frame.f_code
77:            file_name = code.co_filename.replace("\\", "/")
78:            func_name = code.co_name
79:            short = os.path.basename(file_name)
80:            if not _is_skippable(file_name, func_name):
81:                class_name = _class_from_frame(frame)
82:                qualname = f"{class_name}.{func_name}" if class_name else func_name
83:                return CallerInfo(
84:                    file=short, line=frame.f_lineno, func=func_name, qualname=qualname
85:                )
86:            frame = frame.f_back
87:    except Exception:
88:        pass
89:    return CallerInfo(file="unknown", line=0, func="unknown", qualname="unknown")
```

**Core frame walking algorithm**:
1. Get current frame (skip `resolve_caller` itself by using frame(1))
2. Walk back through frames using f_back
3. Skip stdlib logging frames and this package's frames using _is_skippable
4. Return first user code frame with class name if applicable
5. If anything fails, return "unknown" caller info

---

### 1.4 `src/core/formatters/` - Output Formatting

#### `src/core/formatters/json_formatter.py`

Structured JSON logging for files and structured sinks.

```python
40: class JSONFormatter(logging.Formatter):
41:    """Stable, reserved-key-aware JSON formatter."""
42:
43:    def __init__(self, service_name: str, date_format: str = ...) -> None:
44:        super().__init__()
45:        self._service = service_name
46:        self._date_format = date_format
```

**Purpose**: Creates stable JSON output with a consistent schema. This is used for file logging and any structured output.

```python
52:    def format(self, record: logging.LogRecord) -> str:
53:        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
54:            self._date_format
55:        )
56:        payload: dict[str, Any] = {
57:            "timestamp": ts,
58:            "level": record.levelname,
59:            "message": record.getMessage(),
60:            "logger": record.name,
61:            "service": self._service,
62:            "context": getattr(record, "context", None),
63:            "trace_id": getattr(record, "trace_id", None),
64:            "span_id": getattr(record, "span_id", None),
65:            "module": record.module,
66:            "function": record.funcName,
67:            "line": record.lineno,
68:            "pathname": record.pathname,
69:            "process": record.process,
70:            "thread": record.thread,
71:        }
```

**Output schema** (lines 56-70): Core fields including trace context injected by BoundLogger:
- timestamp: ISO 8601 formatted time
- level: Log level (INFO, WARNING, etc.)
- message: The log message
- logger: Logger name
- service: Service name from config
- context: Caller context (file:line func())
- trace_id: Trace ID from BoundLogger
- span_id: Span ID from BoundLogger
- module: Python module name
- function: Function name
- line: Line number
- pathname: Full file path
- process: Process ID
- thread: Thread ID

```python
72:        for key in ("type", "result", "cur_args", "cur_kwargs"):
73:            if hasattr(record, key):
74:                payload[key] = getattr(record, key)
```

Decorator-specific fields from @function_log decorator (type=Execution/Result/Error, result, cur_args, cur_kwargs).

```python
75:        if record.exc_info:
76:            payload["exception"] = self.formatException(record.exc_info)
```

Exception information if an exception is being logged.

```python
80:        extras = {
81:            k: v for k, v in record.__dict__.items()
82:            if k not in _RESERVED and k not in payload
83:        }
84:        if extras:
85:            payload["extras"] = extras
```

User-provided extra fields that aren't part of the standard schema go into the "extras" object.

#### `src/core/formatters/colored_formatter.py`

Colored console output for developer readability.

```python
16: _BASE = "[%(asctime)s] [%(levelname)s] [%(name)s] [%(context)s] %(extras)s - %(message)s"
17: _LOG_COLORS: dict[str, str] = {
18:     "DEBUG": "cyan",
19:     "INFO": "green",
20:     "WARNING": "yellow",
21:     "ERROR": "red",
22:     "CRITICAL": "bold_red",
23: }
```

ANSI color mapping for log levels. Uses colorlog library's color codes.

```python
26: class ConsoleFormatter(ColoredFormatter):
27:    def __init__(self, date_format: str = "%H:%M:%S", use_colors: bool = True) -> None:
28:        fmt = ("%(log_color)s[%(asctime)s] [%(levelname)s]%(reset)s [%(name)s] [%(context)s]%(extras)s - %(message)s") if use_colors else _BASE
```

**Format**: `[HH:MM:SS] [LEVEL] [logger] [context] extras - message`

When use_colors is True, adds color codes. When False (e.g., for piped output), uses plain format.

```python
40:    def format(self, record: logging.LogRecord) -> str:
41:        if not hasattr(record, "context"):
42:            record.context = "<no-context>"
43:        extras: dict[str, Any] = {...}
44:        record.extras = ...
45:        return super().format(record)
```

Fills in missing context with placeholder and formats extras for display.

---

### 1.5 `src/core/filters/` - Log Filtering

#### `src/core/filters/sampling.py`

Random or deterministic log sampling to reduce log volume under high load.

```python
49: class SamplingFilter(logging.Filter):
50:    """
51:    Always passes through records at or above the configured `min_level`.
52:    For records below, applies the configured `rate` either randomly
53:    or deterministically.
54:    """
55:
56:    def __init__(self, settings: SamplingSettings) -> None:
57:        super().__init__()
58:        self._settings = settings
59:        self._min_level = logging._nameToLevel[settings.min_level]
```

**Purpose**: Drop low-priority logs under high load while preserving important ones. Default min_level is WARNING, so INFO/DEBUG are subject to sampling.

```python
61:    def should_keep(self, record: logging.LogRecord) -> _Decision:
62:        # Always keep high-signal records.
63:        if record.levelno >= self._min_level:
64:            return _Decision.KEEP
65:        rate = self._settings.rate
66:        if rate >= 1.0:
67:            return _Decision.KEEP
68:        if rate <= 0.0:
69:            return _Decision.DROP
70:        if self._settings.deterministic:
71:            return _Decision.KEEP if _stable_float(_stable_key(record)) < rate else _Decision.DROP
72:        return _Decision.KEEP if random.random() < rate else _Decision.DROP
```

**Decision logic**:
1. Always keep logs at or above min_level (default: WARNING)
2. If rate is 1.0, keep everything below min_level
3. If rate is 0.0, drop everything below min_level
4. If deterministic, hash trace_id for consistent decisions (same trace always kept or dropped)
5. Otherwise, random sampling with random.random()

```python
31: def _stable_float(s: str) -> float:
32:    """Deterministic mapping from a string to a float in [0, 1)."""
33:    digest = hashlib.sha256(s.encode("utf-8")).hexdigest()
34:    n = int(digest[:16], 16)
35:    return (n % 10_000_000) / 10_000_000.0
```

Deterministic hash function that maps a string to a float in [0, 1). Used for deterministic sampling.

#### `src/core/filters/overflow.py`

Queue capacity-based filtering for when the queue is full.

```python
14: @dataclass
15: class QueueCapacityProbe:
16:    """Snapshot of the queue's current state."""
17:    size_fn: Callable[[], int]
18:    capacity: int
```

Probe encapsulates queue state for the filter. The size_fn is a callable that returns current queue size.

```python
25: class OverflowFilter(logging.Filter):
26:    def __init__(self, probe: QueueCapacityProbe, policy: str = "drop_oldest") -> None:
27:        self._probe = probe
28:        self._policy: Literal["drop_oldest", "drop_newest", "block"] = policy
```

**Policies**:
- `drop_oldest`: Always admit (queue handles eviction internally)
- `drop_newest`: Reject new records when queue is full
- `block`: Admit and let producer block on put (back-pressure)

---

## 2. Configuration (`src/config/`)

### 2.1 `src/config/logger_config.py` - Main Configuration

```python
18: class LoggerConfig(BaseSettings):
20:    """
21:    The single, full logger configuration. Read from kwargs, from
22:    environment variables prefixed with `LOGGER_` (nested keys use
23:    `__`), and from a `.env` file.
24:    """
```

**Configuration sources** (priority order, highest to lowest):
1. Explicit kwargs passed to constructor
2. Environment variables (LOGGER_*)
3. .env file

```python
25:    model_config = SettingsConfigDict(
26:        env_file=".env",
27:        env_prefix="LOGGER_",
28:        env_nested_delimiter="__",
29:        extra="ignore",
30:    )
```

- env_file: Look for .env file
- env_prefix: All env vars start with LOGGER_
- env_nested_delimiter: Use __ for nested keys (LOGGER__AMQP__URL=...)
- extra="ignore": Don't raise on unknown fields

```python
32:    service_name: str = "app"
33:    level: str = "INFO"
34:    directory: str = "logs"
35:    json_logs: bool = True
36:    date_format: str = "%Y-%m-%dT%H:%M:%S.%fZ"
37:    module_levels: dict[str, str] = Field(default_factory=dict)
```

**Core settings**:
- service_name: Identifier for this service (used in JSON output)
- level: Global log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- directory: Where to write log files
- json_logs: Use JSON format for files (vs plain text)
- date_format: ISO 8601 timestamp format
- module_levels: Per-module log levels (e.g., {"sqlalchemy": "WARNING"})

```python
39:    sampling: SamplingSettings = Field(default_factory=SamplingSettings)
40:    rotation: RotationSettings = Field(default_factory=RotationSettings)
41:    queue: QueueSettings = Field(default_factory=QueueSettings)
42:    console: ConsoleSettings = Field(default_factory=ConsoleSettings)
43:    amqp: AMQPSettings | None = None
44:    otel: OTelSettings = Field(default_factory=OTelSettings)
```

**Feature-specific settings**:
- sampling: Log sampling configuration
- rotation: File rotation settings
- queue: Queue capacity and overflow policy
- console: Console output settings
- amqp: RabbitMQ settings (optional, None by default)
- otel: OpenTelemetry settings

---

## 3. Handlers (`src/handlers/`)

Handlers are the final destinations for log records. The framework uses a pipeline pattern where console logs go directly (immediate) while file and AMQP logs go through a queue (deferred).

### 3.1 `src/handlers/console.py`

```python
14: def make_console_handler(cfg: LoggerConfig) -> logging.Handler:
15:    stream = sys.stdout if cfg.console.destination == "stdout" else sys.stderr
16:    h = logging.StreamHandler(stream)
17:    h.setLevel(cfg.numeric_level())
18:    h.setFormatter(ConsoleFormatter(date_format="%H:%M:%S", use_colors=cfg.console.colors))
19:    return h
```

**Purpose**: Immediate console output for developer visibility. Always synchronous (never queued) so developers see logs even if sinks are broken.

- Creates a StreamHandler writing to stdout or stderr
- Uses the ConsoleFormatter for colored output
- Uses short time format (HH:MM:SS) for console

### 3.2 `src/handlers/rotating_file.py`

```python
16: class _GzipOnRolloverMixin:
17:    """
18:    Mixin that gzips the rolled-over file (`*.log.1` or
19:    `*.log.YYYY-MM-DD` for time rotation) before the next cycle evicts it.
20:    """
21:    compress: bool = True
22:    baseFilename: str
23:    when: str
24:    rolloverAt: int
25:
26:    def _gzip_after_rollover(self) -> None:
27:        if not getattr(self, "compress", False):
28:            return
29:        # Pick the right source filename...
30:        candidates: list[str] = []
31:        if isinstance(self, logging.handlers.TimedRotatingFileHandler):
32:            if not self.when.startswith("W"):
33:                candidates.append(f"{self.baseFilename}.1")
34:            else:
35:                candidates.append(
36:                    f"{self.baseFilename}.{datetime.fromtimestamp(self.rolloverAt).strftime('%Y-%m-%d')}"
37:                )
38:        else:
39:            candidates.append(f"{self.baseFilename}.1")
40:        for src in candidates:
41:            if os.path.exists(src) and not src.endswith(".gz"):
42:                gz = src + ".gz"
43:                with open(src, "rb") as f_in, gzip.open(gz, "wb") as f_out:
44:                    shutil.copyfileobj(f_in, f_out)
45:                os.remove(src)
```

**Gzip compression**: After rotation, compress the old log file to save disk space. This runs automatically after each rollover:
- For size rotation: compresses app.log.1
- For time rotation: compresses app.log.YYYY-MM-DD

```python
62: def make_rotating_file_handler(cfg: LoggerConfig) -> logging.Handler:
63:    Path(cfg.directory).mkdir(parents=True, exist_ok=True)
64:    filename = os.path.join(cfg.directory, f"{cfg.service_name}.log")
65:    rot = cfg.rotation
66:
67:    if rot is not None and rot.when is not None:
68:        h: logging.Handler = _GzTimedRotatingFileHandler(...)
69:    else:
70:        h = _GzSizeRotatingFileHandler(...)
```

**File handler creation**:
- Creates log directory if it doesn't exist
- Names file after service name (e.g., app.log)
- Chooses time-based or size-based rotation based on config

### 3.3 `src/handlers/queue.py`

```python
15: def build_queue_pipeline(
16:    cfg: LoggerConfig,
17:    sinks: list[logging.Handler],
18: ) -> tuple[logging.Handler, logging.handlers.QueueListener]:
19:    qcfg = cfg.queue
20:    q: _queue.Queue = _queue.Queue(maxsize=qcfg.capacity)
21:    listener = logging.handlers.QueueListener(q, *sinks, respect_handler_level=True)
22:
23:    probe = QueueCapacityProbe(size_fn=q.qsize, capacity=qcfg.capacity)
24:    qh = logging.handlers.QueueHandler(q)
25:    qh.addFilter(OverflowFilter(probe, qcfg.overflow))
26:    return qh, listener
```

**Queue pipeline**:
1. Create bounded queue with configured capacity (default 10,000)
2. Create QueueListener with all sinks (file, AMQP)
3. Create QueueHandler with OverflowFilter
4. Returns (handler, listener) - caller must start listener thread

This design prevents application threads from blocking on disk writes or network operations. The queue acts as a buffer, and a separate listener thread handles the actual writing.

---

## 4. Factory (`src/factory/`)

### 4.1 `src/factory/logger_factory.py` - Main Entry Point

This is the composition root - the central piece that wires everything together. It's essentially a Dependency Injection (DI) container for the logging system.

```python
25: class LoggerFactory:
26:    """
27:    Construct once with a `LoggerConfig`, call `get_logger()`, and call
28:    `shutdown()` (or use the `with` form) at the end of the process.
29: """
```

**Lifecycle**:
1. `__init__()`: Build handlers, start queue listener
2. `get_logger()`: Return BoundLogger instance
3. `shutdown()`: Stop listener, close handlers

```python
34:    def __init__(self, config: LoggerConfig | None = None) -> None:
35:        self._config = config or LoggerConfig()
36:        self._shutdown = False
37:        self._lock = threading.Lock()
38:        self._queue_handler = None
39:        self._listener = None
40:        self.tracer = Tracer(self._config.otel)
```

**Initialization**:
- Use provided config or create defaults
- Track shutdown state with lock (thread-safe)
- Create Tracer (initializes OTel if enabled)

```python
42:        self._root = logging.getLogger(self._config.service_name)
43:        self._root.setLevel(self._config.numeric_level())
44:        self._root.propagate = False
```

**Root logger setup**:
- Get/create logger for service name
- Set log level (converts string "INFO" to numeric 20)
- Disable propagation (prevents duplicate logs - important!)

Without propagate=False, messages might appear twice in handlers.

```python
47:        for mod, lvl in self._config.module_levels.items():
48:            logging.getLogger(mod).setLevel(logging.getLevelName(lvl.upper()))
```

**Per-module levels**: Allow different log levels for specific modules. For example:
- "sqlalchemy": "WARNING" - reduces noise from SQLAlchemy
- "uvicorn": "ERROR" - only show errors from uvicorn

```python
52:        plan = build_handlers(self._config)
53:        for h in plan.immediate:
54:            self._root.addHandler(h)
55:        if plan.queue is not None:
56:            qh, listener = plan.queue
57:            self._queue_handler = qh
58:            self._listener = listener
59:            self._root.addHandler(qh)
60:            listener.start()
```

**Handler attachment**:
- Immediate handlers (console) go directly to root logger
- Queue handler goes to root logger
- Queue listener starts in background thread

```python
63:        publish(self)
```

Register factory for decorator discovery. This allows @function_log and @class_log decorators to find the active factory.

```python
66:    def get_logger(self) -> BoundLogger:
67:        if self._shutdown:
68:            raise ShutdownError("LoggerFactory is shut down")
69:        return BoundLogger(self._root, {}, self.tracer)
```

**Get logger**: Returns BoundLogger bound to root logger with tracer. Raises ShutdownError if factory is shut down.

```python
74:    def flush(self, timeout: float = 5.0) -> None:
75:        for h in list(self._root.handlers):
76:            flush_sync = getattr(h, "flush_sync", None)
77:        if callable(flush_sync):
78:            flush_sync(timeout=timeout)
79:        else:
80:            h.flush()
```

**Flush**: Drain in-memory queue to sinks. Supports both sync flush and async flush_sync (for AMQP async handler). Useful for tests and ensuring records hit sinks before exit.

```python
97:    def shutdown(self) -> None:
98:        with self._lock:
99:            if self._shutdown:
100:               return
101:           self._shutdown = True
102:           if self._listener is not None:
103:               self._listener.stop()
104:           for h in list(self._root.handlers):
105:               h.close()
106:               self._root.removeHandler(h)
107:           withdraw(self)
```

**Shutdown**:
1. Acquire lock (prevent concurrent shutdown)
2. Check if already shutdown (idempotent)
3. Mark as shutdown
4. Stop queue listener thread (stops background processing)
5. Close and remove all handlers (flushes buffers, closes files/sockets)
6. Unregister from decorator lookup

### 4.2 `src/factory/builder.py`

```python
33: def build_handlers(config: LoggerConfig) -> HandlerPlan:
```

Translates config into handler instances. This is separated from the factory to keep the factory focused on lifecycle management.

```python
40:    if config.console.enabled:
41:        immediate.append(make_console_handler(config))
```

Console handler (always immediate). Even if file/AMQP are configured, console can still be enabled.

```python
48:    if config.directory:
49:        sinks.append(make_rotating_file_handler(config))
```

File sink: Always added when directory is set, regardless of AMQP config. The two transports are independent - user may want both for redundancy.

```python
51:    if config.amqp:
52:        try:
53:            from src.handlers.amqp import make_amqp_handler
54:            sinks.append(make_amqp_handler(config.amqp))
55:        except Exception as e:
56:            if not config.amqp.fail_open:
57:               raise
58:           sys.stderr.write(f"[logger] AMQP disabled: {e}\n")
```

**AMQP sink**: With fail-open logic - if RabbitMQ is down and fail_open=True, print warning and continue without AMQP. If fail_open=False, raise exception (fails application startup).

---

## 5. AMQP Handlers (`src/handlers/amqp/`)

### 5.1 `src/handlers/amqp/factory.py`

```python
15: def make_amqp_handler(settings: AMQPSettings) -> logging.Handler:
16:    if settings.transport == "sync":
17:        return AMQPSyncHandler(settings)
18:    try:
19:        loop = asyncio.get_running_loop()
20:        return AMQPAsyncHandler(settings, loop=loop)
21:    except RuntimeError:
22:        return AMQPAsyncHandler(settings)
```

**Factory**: Picks sync or async based on config:
- sync: Uses pika BlockingConnection, safe anywhere
- async: Uses aio-pika. If there's a running loop, attaches to it; otherwise creates a dedicated loop in a daemon thread

### 5.2 `src/handlers/amqp/sync.py` - Synchronous AMQP

```python
19: class AMQPSyncHandler(logging.Handler):
20:    """
21:    Blocking-connection (`pika`) AMQP handler. One connection per process;
22:    one in-memory buffer guarded by a `threading.Lock`.
23:    """
```

**Thread-safe batching**: Uses lock and buffer for batching. The connection is shared across all log calls.

```python
27:    def __init__(self, settings: AMQPSettings) -> None:
28:        super().__init__()
29:        validate_settings(settings)
30:        self._settings = settings
31:        self._buffer: list[bytes] = []
32:        self._lock = threading.Lock()
33:        self._conn: Any = None
34:        self._chan: Any = None
35:        self._last_flush = time.monotonic()
36:        self._closed = False
37:        self._connect()
```

**Initialization**:
- Validate settings
- Create buffer and lock
- Connect to AMQP on construction (blocking)

```python
40:    def _connect(self) -> None:
41:        try:
42:            import pika
43:        except ImportError as e:
44:            raise AMQPError("install 'pika' (logger[amqp])") from e
45:        params = pika.URLParameters(self._settings.url)
46:        params.socket_timeout = self._settings.connect_timeout_s
47:        self._conn = pika.BlockingConnection(params)
48:        self._chan = self._conn.channel()
49:        self._chan.exchange_declare(...)
50:        if self._settings.queue:
51:            self._chan.queue_declare(...)
52:            self._chan.queue_bind(...)
```

**Connect**: Creates connection, channel, declares exchange and queue.

```python
63:    def emit(self, record: logging.LogRecord) -> None:
64:        if self._closed:
65:            return
66:        payload = serialize_record(record) + b"\n"
67:        with self._lock:
68:            self._buffer.append(payload)
69:            if (
70:                len(self._buffer) >= self._settings.batch_size
71:                or (time.monotonic() - self._last_flush) >= self._settings.flush_interval_s
72:            ):
73:                self._flush_locked()
```

**Emit**: Add to buffer, flush if batch size OR flush interval threshold reached. This batching reduces network round trips.

```python
94:    def flush(self) -> None:
95:        if self._closed:
96:            return
97:        with self._lock:
98:            self._flush_locked()
```

**Flush**: Manual flush, called during shutdown or explicitly.

### 5.3 `src/handlers/amqp/async_handler.py` - Asynchronous AMQP

```python
76: class AMQPAsyncHandler(logging.Handler):
```

**Async design**: Uses sync SimpleQueue to bridge sync emit() to async consumer. This is a common pattern for mixing sync and async code.

```python
91:        # Sync side: producer drops records here.
92:        self._inbox: _queue.SimpleQueue[bytes] = _queue.SimpleQueue()
```

**Bridge**: SimpleQueue is thread-safe and works across the sync/async boundary. emit() is sync, consumer is async.

```python
201:    def emit(self, record: logging.LogRecord) -> None:
202:        if self._closing or self._closed:
203:            return
204:        payload = serialize_record(record) + b"\n"
205:        try:
206:            self._inbox.put_nowait(payload)
207:        except Exception:
208:            return
209:        if self._wake_event is not None:
210:            with contextlib.suppress(RuntimeError):
211:                self._loop.call_soon_threadsafe(self._wake_event.set)
```

**Emit**: Put payload in inbox, wake async consumer. Non-blocking (put_nowait).

```python
219:    async def _consumer(self) -> None:
220:        """
221:        Long-running coroutine. Reads from `_inbox`, batches, and publishes.
222:        """
223:        while True:
224:            await asyncio.wait_for(self._wake_event.wait(), timeout=...)
225:            self._wake_event.clear()
226:            while True:
227:                try:
228:                    msg = self._inbox.get_nowait()
229:                except Exception:
230:                    break
231:                buffer.append(msg)
232:            if buffer:
233:                await self._publish_buffer(buffer)
234:            self._drained_event.set()
```

**Consumer loop**:
1. Wait for wake event or timeout
2. Drain all items from inbox
3. Publish batch to AMQP
4. Signal flush completion (for flush_sync barrier)

---

## 6. Decorators (`src/decorators/`)

### 6.1 `src/decorators/functions.py` - @function_log

```python
34: def function_log(*, show_args: bool = True, show_result: bool = True):
```

Decorator factory for automatic function logging. Options to show/hide args and results.

```python
39:        def wrapper(*args: Any, **kwargs: Any) -> Any:
40:            factory = active_factory()
41:            if factory is None:
42:                return func(*args, **kwargs)
```

If no factory is active, transparent pass-through. This makes the decorator optional - code works with or without a logger factory.

```python
43:            log = bound_logger_for_call(factory, func, args)
44:            start = time.perf_counter()
45:            try:
46:                if show_args:
47:                    log.info(f"Executing {func.__name__}", extra={...})
48:                result = func(*args, **kwargs)
49:                elapsed = time.perf_counter() - start
50:                if show_result:
51:                    log.info(f"Finished {func.__name__} in {elapsed:.4f}s", extra={...})
52:                return result
53:            except Exception as exc:
54:                log.error(f"Exception: {exc}", extra={...})
55:                raise
```

**Logging**:
- Log entry with function name and args/kwargs
- Log exit with result and elapsed time
- Log exceptions with full traceback
- Re-raises the exception after logging

### 6.2 `src/decorators/classes.py` - @class_log

```python
29: def class_log(*, show_args: bool = True, show_result: bool = True):
```

Applies @function_log to all public methods of a class.

```python
32:        def decorator(cls: type) -> type:
33:            if active_factory() is None:
34:                return cls
35:            for name, value in list(cls.__dict__.items()):
36:                if name.startswith("_"):
37:                    continue
38:                func, is_static, is_class = _unwrap(value)
39:                if func is None:
40:                    continue
41:                wrapped = function_log(show_args=show_args, show_result=show_result)(func)
42:                setattr(cls, name, wrapped)
43:            return cls
```

Iterates over class __dict__, wraps all public methods (not starting with _). Handles staticmethod, classmethod, and regular methods correctly.

---

## 7. Exception Hierarchy (`src/errors.py`)

```python
10: class LoggerError(Exception):
    """Base for all logger errors."""

14: class ConfigError(LoggerError):
    """Invalid configuration."""

18: class HandlerError(LoggerError):
    """Generic handler failure."""

22: class HandlerBuildError(HandlerError):
    """A handler could not be constructed at factory-build time."""

26: class AMQPError(HandlerError):
    """An AMQP handler raised during connect, publish, or shutdown."""

30: class OTelError(LoggerError):
    """An OpenTelemetry integration raised."""

34: class ShutdownError(LoggerError):
    """Operation attempted after the factory is shut down."""
```

---

## 8. File Relationships and Dependencies

```
src/
├── config/
│   ├── logger_config.py          # Main config (aggregates all settings)
│   └── settings/
│       ├── amqp.py               # AMQP connection settings
│       ├── console.py           # Console output settings
│       ├── otel.py               # OpenTelemetry settings
│       ├── queue.py              # Queue capacity settings
│       ├── rotation.py           # File rotation settings
│       └── sampling.py          # Log sampling settings
│
├── core/
│   ├── caller.py                 # Frame walking for context
│   ├── context.py                # BoundLogger (user-facing API)
│   ├── tracer.py                 # Trace/span management
│   ├── filters/
│   │   ├── overflow.py          # Queue overflow filter
│   │   └── sampling.py          # Log sampling filter
│   ├── formatters/
│   │   ├── colored_formatter.py # Console formatting
│   │   └── json_formatter.py   # File formatting
│   └── transport/
│       ├── batch.py             # Batch buffer
│       └── serialize.py         # Record serialization
│
├── decorators/
│   ├── base.py                  # Shared decorator utilities
│   ├── classes.py               # @class_log decorator
│   └── functions.py             # @function_log decorator
│
├── factory/
│   ├── builder.py               # Builds handlers from config
│   ├── logger_factory.py        # Main entry point (composition root)
│   └── registry.py              # Factory registry for decorators
│
├── handlers/
│   ├── amqp/
│   │   ├── async_handler.py    # Async AMQP (aio-pika)
│   │   ├── async_loop.py       # Async event loop runner
│   │   ├── common.py           # Shared utilities
│   │   ├── factory.py          # Handler factory
│   │   └── sync.py             # Sync AMQP (pika)
│   ├── console.py              # Console handler
│   ├── queue.py                # Queue pipeline builder
│   └── rotating_file.py        # File handler with rotation
│
└── errors.py                    # Exception hierarchy
```

---

## 9. End-to-End Flow

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Application Code                                                           │
│ ```python                                                                  │
│ factory = LoggerFactory(config)                                            │
│ logger = factory.get_logger()                                              │
│ logger.info("Payment accepted")                                            │
│ ```                                                                        │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ BoundLogger.process()                                                      │
│ - Merges bound fields                                                      │
│ - Injects trace_id from Tracer                                             │
│ - Injects span_id from Tracer                                              │
│ - Resolves caller context (file:line func())                               │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ Python Logger (root)                                                       │
│                                                                            │
│ ├── Console Handler (immediate)                                            │
│ │   └── ConsoleFormatter (colored) → stdout/stderr                         │
│ │                                                                          │
│ └── QueueHandler                                                           │
│     └── Queue (bounded, thread-safe)                                       │
│         │                                                                  │
│         ▼ (QueueListener thread)                                           │
│         ├── RotatingFileHandler (JSON, sampled, rotated) → logs/app.log    │
│         │                                                                  │
│         └── AMQP Handler (sync/async) → RabbitMQ                           │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Usage Examples

### Basic Usage

```python
from src.factory import LoggerFactory
from src.config import LoggerConfig

config = LoggerConfig(
    service_name="payments",
    level="INFO",
    directory="logs"
)

factory = LoggerFactory(config)
logger = factory.get_logger()

logger.info("Application started")
logger.warning("Something went wrong")
logger.error("Payment failed", extra={"amount": 100})

factory.shutdown()
```

### With Context Binding

```python
logger = factory.get_logger()

# Create bound loggers with context
payment_logger = logger.bind(request_id="req_123", user_id="user_456")
payment_logger.info("Processing payment")

order_logger = logger.bind(order_id="ord_789")
order_logger.info("Order created")
```

### With Tracing

```python
logger = factory.get_logger()

# Set trace/span IDs
trace_id = logger.set_trace()  # Generate new trace
span_id = logger.set_span()    # Generate new span

logger.info("Processing request")
# Logs include trace_id and span_id
```

### With Decorators

```python
from src.decorators import function_log, class_log

@function_log()
def process_payment(amount: float, currency: str) -> str:
    # Automatically logs entry, exit with timing, and exceptions
    if amount < 0:
        raise ValueError("Amount must be positive")
    return f"Processed {currency} {amount}"

@class_log()
class PaymentService:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def process(self, amount: float) -> dict:
        # All public methods are automatically logged
        return {"status": "success", "amount": amount}
```

### With OpenTelemetry

```python
from src.config import LoggerConfig, OTelSettings

config = LoggerConfig(
    service_name="payments",
    otel=OTelSettings(
        enabled=True,
        otlp_endpoint="http://localhost:4317",
        sample_ratio=0.5  # Sample 50% of traces
    )
)

factory = LoggerFactory(config)
# Trace IDs automatically integrated with OpenTelemetry
```

### With AMQP

```python
from src.config import LoggerConfig, AMQPSettings

config = LoggerConfig(
    service_name="payments",
    amqp=AMQPSettings(
        url="amqp://guest:guest@localhost:5672/",
        exchange="logs",
        exchange_type="fanout",
        fail_open=True  # Continue if RabbitMQ is down
    )
)

factory = LoggerFactory(config)
# Logs go to both file and RabbitMQ
```

---

## 11. Key Design Patterns

1. **Composition Root**: LoggerFactory is the central wiring point that creates and connects all components.

2. **Logger Adapter**: BoundLogger extends Python's LoggerAdapter to inject context automatically.

3. **Decorator Pattern**: @function_log and @class_log add logging behavior without modifying original code.

4. **Queue Pipeline**: QueueHandler + QueueListener decouple application threads from slow I/O operations.

5. **Fail-Open**: AMQP handler continues without crashing if RabbitMQ is unavailable.

6. **Dual-Mode**: Tracer works with or without OpenTelemetry, providing consistent API.

7. **Context Variables**: Uses ContextVars instead of thread-local for better async support.

8. **Factory Pattern**: make_console_handler, make_rotating_file_handler, make_amqp_handler create appropriate handlers.

---

This comprehensive documentation covers the entire logging framework. The design follows clean separation of concerns with clear boundaries between:

- **Configuration**: All settings in one place
- **Core**: BoundLogger, Tracer, Filters
- **Handlers**: Different output destinations
- **Factory**: Lifecycle management and wiring
- **Decorators**: Automatic function/class logging
