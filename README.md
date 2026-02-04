# Project logger

A production-ready Python logging framework designed for modern backends and AI pipelines.

It supports:
- Structured JSON logs (ELK / GCP Logging / Datadog ready)
- Trace + Span IDs (contextvars, async-safe)
- Automatic context (file:line Class.method())
- Per-module log levels
- Sampling filters for hot paths (reduce noise + cost)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Development](#development)
- [Testing](#testing)
- [Deployment](#deployment)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)

---

## Overview

This project provides a clean, extensible logging layer for Python services.

It’s built to solve common production pain points:
- Logs without structure are hard to search
- Async + threads break context
- Trace correlation is missing
- Hot loops spam logs and increase cloud costs
- Large codebases need per-module control

This logger provides a single unified API for:
- console logs (pretty + colored)
- file logs (JSON structured)
- trace/span correlation
- sampling

---

## Architecture

```
LoggerConfig
    ↓
Logger (singleton)
    ↓
logging.Logger (stdlib)
    ↓
Handlers
    ├── Console handler (colored)
    └── File handler (.log or .json)
    ↓
Filters
    └── SamplingFilter
    └── DeterministicFilter
    ↓
ContextLogger (LoggerAdapter)
    ├── context
    ├── trace_id
    └── span_id
```

### Core Components:

1. **API Layer:** Interfaces (CLI, SDK, REST) for uploading and managing files
2. **Service Layer:** Business logic for versioning and lifecycle rules
3. **Repository Layer:** Abstract persistence interfaces for storage and metadata
4. **Infrastructure Layer:** Cloud storage providers and NoSQL database adapters

---

## Features

1. Structured JSON logging
    - Compatible with ELK, GCP Logging, Datadog, Splunk
    - Includes context, trace_id, span_id, module, function, line, exception

2. Trace + Span IDs
    - Uses contextvars (async-safe)
    - Supports manual trace/span injection

3. Automatic context resolution
    - Adds file:line Class.method() automatically
    - Works for functions, methods, decorators

4. Per-module log levels
    - Example: src.core=WARNING while the rest stays INFO

5. Sampling filter
    - Sample DEBUG/INFO logs for noisy paths
    - Always keep WARNING/ERROR/CRITICAL

6. Singleton logger factory
    - Global configuration
    - Safe Logger.configure(...) entrypoint

---

## Installation
```bash
pip install <url>
```


Or install from source:

```bash
git clone <url>
cd project-name
pip install -e .
```

---

### Usage

Basic setup
```python
import logging
from src.logger import Logger
from src.config import LoggerConfig

Logger.configure(
    LoggerConfig(
        name="app",
        level=logging.INFO,
        directory="logs",
        json_logs=True,
        sample_rate=0.2,
        module_levels={
            "src.core": logging.WARNING,
        },
    )
)

logger = Logger().bind("startup")
logger.info("Service initialized")
```

Trace + ID span

```python
from src.logger import Logger

log = Logger()
log.set_trace()
log.set_span()

logger = log.bind("request")
logger.info("Request started")
```

JSON logs example output
```json
{
  "timestamp": "2026-02-04T10:55:01.140Z",
  "level": "INFO",
  "message": "Request started",
  "logger": "app",
  "context": "api.py:88 EDDController.calculate()",
  "trace_id": "a1f29c...",
  "span_id": "91c77d...",
  "module": "api",
  "function": "calculate",
  "line": 88
}
```

---

### Configuration

Configuration is done through LoggerConfig.

Example:

```python
from src.config import LoggerConfig

config = LoggerConfig(
    name="service",
    directory="logs",
    json_logs=True,
    sample_rate=0.1,
    level=logging.INFO,
    module_levels={
        "src.core": logging.WARNING,
        "google": logging.ERROR,
        "httpx": logging.ERROR,
    },
)
```

Key settings

| Field          | Meaning                                        |
|----------------|------------------------------------------------|
| json_logs      | Output JSON logs for file handler              |
| directory      | Where log files are stored                     |
| deterministic  | Enable deterministic logging                   |
| sample_rate    | Sampling probability for INFO/DEBUG            |
| module_levels  | Per-module log level override                  |
| level          | Global log level                               |
| name           | Logger name                                    |

---

### Project Structure

```
src/
 ├── logger.py              # Logger singleton + ContextLogger
 ├── config.py              # LoggerConfig + JSONFormatter + SamplingFilter
 ├── core/
 │    └── tracer.py         # contextvars trace_id/span_id
 └── decorators/
      ├── functions.py      # function_log decorator
      └── classes.py        # class_log decorator

```
---

### Development
```bash
pip install -r requirements-dev.txt
```

---

### Testing
```
pytest tests/
```

---

### Deployment

The service can be deployed as:

```
Python SDK library
FastAPI microservice
Serverless function (Cloud Run / Lambda / Azure Functions)
Internal data platform component
```

---

### Roadmap

1. Request middleware integration for Flask/FastAPI
2. Deterministic sampling by trace_id (avoid partial traces)
3. Rotating file handler support
4. OpenTelemetry bridge
5. Log batching / async writer for high throughput

---

### Contributing

Contributions are welcome.
Please follow the coding standards and submit PRs with tests and documentation updates.

---

### License

MIT License.

---

### Contact

Maintainer: Evan Flores
Email: *efloresp06@liverpool.com.mx*
Organization: **Liverpool**