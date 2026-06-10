# OpenTelemetry + Jaeger Zero-to-Hero

A hands-on, no-prior-knowledge walkthrough of **distributed tracing** —
using the `Logger` library as the running example so every concept is
grounded in something you'll actually use.

By the end of this guide you'll know:

- What tracing is and why it's different from logging
- The three pillars of observability (logs, metrics, traces) and how
  they fit together
- The vocabulary: **span**, **trace**, **context**, **propagation**
- How a request flows through a distributed system as a tree of spans
- How OpenTelemetry (OTel) standardizes all of this
- How Jaeger stores and visualizes the data
- How the `Logger` library auto-injects the active `trace_id` and
  `span_id` into every log record
- How to start and customize spans inside your own code
- How to read a trace in the Jaeger UI to find the slow DB call
- Common production pitfalls (sampling, head-based vs tail-based,
  context loss across boundaries)

> **Time**: ~30 min reading + ~15 min hands-on.

---

## Table of Contents

1. [What is tracing?](#1-what-is-tracing)
2. [Logs vs metrics vs traces](#2-logs-vs-metrics-vs-traces)
3. [The vocabulary: trace, span, context](#3-the-vocabulary-trace-span-context)
4. [How a request becomes a tree of spans](#4-how-a-request-becomes-a-tree-of-spans)
5. [OpenTelemetry: the standard](#5-opentelemetry-the-standard)
6. [Jaeger: the storage and UI](#6-jaeger-the-storage-and-ui)
7. [Run Jaeger locally](#7-run-jaeger-locally)
8. [Your first trace in 30 seconds](#8-your-first-trace-in-30-seconds)
9. [Wiring the Logger library to OTel](#9-wiring-the-logger-library-to-otel)
10. [Reading the Jaeger UI](#10-reading-the-jaeger-ui)
11. [Custom spans: instrumenting your own code](#11-custom-spans-instrumenting-your-own-code)
12. [Trace context propagation across boundaries](#12-trace-context-propagation-across-boundaries)
13. [Sampling: which traces to keep](#13-sampling-which-traces-to-keep)
14. [Common production pitfalls](#14-common-production-pitfalls)
15. [Where to go next](#15-where-to-go-next)

---

## 1. What is tracing?

Logging tells you *what happened*. Tracing tells you *how the time was
spent* and *which components were involved*.

Imagine a single user request that:
1. Hits your **API gateway** (5 ms)
2. Forwards to the **billing service** (15 ms)
3. Calls the **payment service** (200 ms — slow!)
4. Writes to the **audit log** (10 ms)

In your logs you see four entries, each on a different service, with
different timestamps and different request IDs. To figure out **which
one was slow**, you have to manually join the logs by request ID and
read the timestamps.

**Tracing does that join for you.** A single click in Jaeger shows the
whole tree:

```
                       /api/charge (230 ms)              ← the trace
                       ├─ POST /pay (215 ms)              ← spans, nested
                       │   └─ DB INSERT  (180 ms)         ← the slow bit
                       └─ audit.write  (10 ms)
```

You immediately see: "the payment call took 215 ms because of an
180 ms DB write. Look at that query." **That's the value of tracing.**

### What tracing is *not*

- **Not logging.** Logs are human-readable text events. Traces are
  structured spans with timings.
- **Not metrics.** Metrics are aggregate counters ("requests/sec",
  "p99 latency"). A single trace is one specific request.
- **Not APM (Application Performance Monitoring).** APM tools *use*
  tracing under the hood, but they also add profiling, error
  tracking, etc. Tracing is the data; APM is the dashboard.

---

## 2. Logs vs metrics vs traces

The "three pillars of observability":

| Pillar | Question it answers | Example |
|---|---|---|
| **Logs** | What happened, in detail, for one event? | `"user 42 charged $99.00; txn=txn-12345"` |
| **Metrics** | How is the system doing, aggregated? | `http_requests_total{service="billing", status="200"} = 15423` |
| **Traces** | Where did the time go for one request? | the tree above |

**They reinforce each other.** A trace tells you *the payment call was
slow*; a log entry from inside that call tells you *it timed out
connecting to Stripe*; a metric tells you *this is the 47th timeout
in the last 5 minutes*. With all three you go from "something is
wrong" to "I know exactly what" in seconds.

The `Logger` library's `OTelSettings` makes this loop tight: every log
record carries the active `trace_id` and `span_id`, so clicking a log
line in your log UI takes you straight to the matching trace in
Jaeger.

---

## 3. The vocabulary: trace, span, context

### Trace

A trace represents **one logical operation** — usually one user
request, one background job, or one scheduled task. Every trace has a
unique 128-bit ID (the `trace_id`), usually rendered as 32 hex
characters: `ba37f26a98168a52912ff49c28b9adcc`.

### Span

A trace is a **tree of spans**. Each span is a single unit of work
(an HTTP request, a DB query, a function call) and has:

| Field | What it is | Example |
|---|---|---|
| `name` | A human-readable label | `POST /pay`, `db.query`, `make_invoice` |
| `trace_id` | The trace it belongs to | `ba37...` |
| `span_id` | Its own 64-bit ID (16 hex chars) | `4afe...` |
| `parent_span_id` | The span that started it | `27e8...` (the parent) |
| `start` / `end` | Timestamps | `2026-06-10T16:28:48.000Z` |
| `attributes` | Key-value metadata | `http.status_code=200` |
| `events` | Timestamped log entries inside the span | `{"name": "cache.miss", "time": ...}` |
| `status` | OK / ERROR | `{"code": "ERROR", "message": "timeout"}` |

### Context (the magic part)

When span A starts span B, B "inherits" A's `trace_id` and stores A's
`span_id` as its `parent_span_id`. This works **across process and
thread boundaries** via two pieces of magic:

1. **In-process**: an `Otel ContextVar` (similar to a Python
   `contextvars.ContextVar`) holds the current span. New spans
   automatically pick it up as their parent.
2. **Across the wire**: when you make an HTTP call, the OTel SDK
   injects HTTP headers (`traceparent`, `tracestate`, `baggage`) into
   the request. The receiving service reads those headers and
   continues the trace.

This **propagation** is what makes distributed tracing work. You
didn't write a single line of code to thread a request ID through
four services, but you get end-to-end visibility.

---

## 4. How a request becomes a tree of spans

```
   Time ─────────────────────────────────────────────────────►

   ┌─── API gateway: GET /charge (root span) ────────────┐
   │                                                     │
   │   ┌─── billing: charge() ──────────────────────┐    │
   │   │   ├─ payment: charge_card()                │    │
   │   │   │   └─ db: INSERT payments               │    │
   │   │   └─ audit: write_event()                  │    │
   │   └────────────────────────────────────────────┘    │
   │                                                     │
   └──┘  t=230ms                                              ▼
```

Every box is a span. The tree structure is implicit in the
`parent_span_id` of each span. The UI (Jaeger) renders it as a tree on
the left, with a horizontal timeline on the right showing what ran
in parallel and what ran sequentially.

Notice that `db: INSERT payments` ran *inside* `payment: charge_card()`.
That's because OTel auto-instruments popular libraries
(`requests`, `boto3`, `psycopg2`, ...) — you don't write span code for
them, you just install the right `opentelemetry-instrumentation-*`
package.

---

## 5. OpenTelemetry: the standard

[OpenTelemetry](https://opentelemetry.io) (OTel) is the CNCF-backed
standard for traces, metrics, and logs. Before OTel (2019), every
tracing vendor had a proprietary SDK: Datadog had `ddtrace`, New Relic
had `newrelic`, Jaeger had its own client. **OTel unified them.**

Today: write your code against the OTel API once, point it at
*any* backend (Jaeger, Zipkin, Datadog, Tempo, Honeycomb) by
swapping the exporter. The `Logger` library does exactly this.

### The OTel API in 30 seconds

```python
from opentelemetry import trace

tracer = trace.get_tracer("my-app")

# Start a span — the SDK automatically uses the current active span
# as the parent (or "no parent" if this is the first span).
with tracer.start_as_current_span("work") as span:
    span.set_attribute("customer.id", 42)
    span.add_event("cache.miss")
    # ... do work ...
    # When the `with` block exits, the span is exported to the backend.
```

That's the entire surface. Three things to know:

| Concept | How to use it |
|---|---|
| Get a tracer | `trace.get_tracer(name)` — one per module/file is fine |
| Start a span | `tracer.start_as_current_span(name)` — context manager is the safe form |
| Add metadata | `span.set_attribute(key, value)` and `span.add_event(name, attrs=...)` |

### OTel SDK vs API

The **API** is the code you write. The **SDK** is the runtime that
actually does something: it batches spans, samples them, and ships
them to a backend. **If you import the API but never configure the
SDK, your spans are no-ops.** This is a common gotcha — your code
"works" but no traces appear.

The `Logger` library's `OTelSettings.enabled=True` is what flips the
SDK on.

---

## 6. Jaeger: the storage and UI

[Jaeger](https://www.jaegertracing.io) is one of several
open-source tracing backends (others: Zipkin, Tempo, SigNoz, Grafana
Pyroscope). It's the most popular for self-hosted deployments.

What Jaeger does:

1. **Receives** spans over OTLP/gRPC (port 4317) or OTLP/HTTP (4318).
2. **Stores** them in a database (in-memory for dev, Cassandra /
   Elasticsearch / Badger for production).
3. **Indexes** them by service, operation, tag, duration, so you can
   search.
4. **Visualizes** the trace tree in a web UI on port 16686.

### Versions and protocols

Jaeger has gone through several protocol generations:

- **Jaeger Thrift** (legacy, port 14250) — the original, now in
  maintenance mode.
- **OTLP/gRPC** (port 4317) — the modern, OTel-native way. **Use
  this.**
- **OTLP/HTTP** (port 4318) — same as above, HTTP/1.1 + protobuf.

The `Logger` library's `OTelSettings` defaults to `protocol="grpc"` and
points at port 4317. That's the right default for Jaeger ≥ 1.35 (and
all current versions).

---

## 7. Run Jaeger locally

The repo's `docker-compose.yml` brings up Jaeger with the OTLP
receiver enabled:

```yaml
services:
  jaeger:
    image: jaegertracing/all-in-one:1.59
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
      COLLECTOR_OTLP_GRPC_HOST_PORT: "0.0.0.0:4317"
    ports:
      - "16686:16686"   # UI
      - "4317:4317"     # OTLP gRPC
      - "4318:4318"     # OTLP HTTP
```

Start it:

```bash
docker compose up -d jaeger
sleep 3
docker ps | grep jaeger
# logger-jaeger-1  jaegertracing/all-in-one:1.59  Up  ...  0.0.0.0:16686->16686, 0.0.0.0:4317->4317

# Open the UI
open http://localhost:16686
```

The UI looks like a search box with no data. That's expected — we
haven't sent any traces yet.

### Two env vars that matter

| Env var | Effect |
|---|---|
| `COLLECTOR_OTLP_ENABLED=true` | Enables the OTLP receiver. **Off by default** in the all-in-one image, surprisingly. |
| `COLLECTOR_OTLP_GRPC_HOST_PORT=0.0.0.0:4317` | Binds the OTLP gRPC port to all interfaces. Default is `localhost:4317`, which is unreachable from outside the container. |

If you see "connection refused" in your OTel client's logs, the most
likely culprit is one of these two env vars being wrong.

---

## 8. Your first trace in 30 seconds

```bash
. venv/bin/activate
pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc
python <<'PY'
import time
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# 1. Configure the SDK
provider = TracerProvider(resource=Resource.create({"service.name": "my-first-app"}))
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
))
trace.set_tracer_provider(provider)

# 2. Use it
tracer = trace.get_tracer("my-first-app")
with tracer.start_as_current_span("hello-world") as span:
    span.set_attribute("user.id", 42)
    time.sleep(0.5)  # pretend to do work

# 3. Flush before exit
provider.shutdown()
print("Span sent!")
PY
```

Open `http://localhost:16686`, select service **`my-first-app`**,
click **Find Traces**. You should see one trace, one span
(`hello-world`), 500 ms duration.

**You just shipped a trace end-to-end.**

What happened:

```
your code
   │
   ▼
TracerProvider (the SDK)
   │
   │  BatchSpanProcessor buffers spans for 5s OR 512 spans,
   │  whichever comes first
   ▼
OTLPSpanExporter
   │
   │  gRPC POST to http://localhost:4317
   ▼
Jaeger (running in docker)
   │
   ▼
Stored. Visible in the UI.
```

---

## 9. Wiring the Logger library to OTel

The `Logger` library exposes OTel through `OTelSettings`:

```python
from src import LoggerConfig
from src.config.settings.otel import OTelSettings

config = LoggerConfig(
    service_name="billing-api",
    otel=OTelSettings(
        enabled=True,                          # ← turns the SDK on
        service_name="billing-api",            # ← used as service.name
        protocol="grpc",                        # ← "grpc" or "http"
        otlp_endpoint="http://localhost:4317",  # ← Jaeger default
        insecure=True,                          # ← no TLS for local dev
        sample_ratio=0.1,                       # ← 10% of traces
    ),
)
```

What the `Logger` library does on `LoggerFactory(config)`:

1. Calls `configure_opentelemetry(settings, ...)` from
   `src/integrations/opentelemetry.py`. This sets up a
   `TracerProvider` with a `Resource` of `{"service.name":
   service_name}` and a `BatchSpanProcessor` pointing at your
   `otlp_endpoint`.
2. Wraps the `bound logger` so every `info()`, `warning()`, etc.
   call gets `trace_id` and `span_id` from the **active OTel
   context** (via `opentelemetry.trace.get_current_span()`) and
   stuffs them into the log record's `extra` dict.
3. Also calls `LoggingInstrumentor().instrument(...)` so any
   third-party `logging` call (from `requests`, `boto3`, ...) also
   gets the active trace context.

The result: every log line carries the W3C trace id, and clicking a
log in your log UI takes you straight to the matching trace in
Jaeger. **The two tools are finally on speaking terms.**

### The four knobs

| Knob | Default | What it controls |
|---|---|---|
| `enabled` | `False` | Master switch. **Off by default** so the library is OTel-optional. |
| `protocol` | `"grpc"` | OTLP transport. `"http"` for HTTP/protobuf. |
| `otlp_endpoint` | `http://localhost:4317` | Where to ship spans. |
| `sample_ratio` | `1.0` | 0.0–1.0; fraction of traces to keep. |

The endpoint is **gRPC by default** because gRPC is more efficient
(multiplexed, smaller payloads, streaming). Use `protocol="http"`
when you need to talk through a corporate HTTP proxy or have
firewalls that block HTTP/2.

---

## 10. Reading the Jaeger UI

Open `http://localhost:16686` after running the demo:

1. **Service dropdown** — pick the service name. Your `Logger`
   `OTelSettings.service_name` becomes this label.
2. **Operation dropdown** — pick a span name (e.g. `process-invoices`)
   or "all".
3. **Time range** — last 1h is the default.
4. **Tags** — search by tag value. `error=true` finds failed traces;
   `http.status_code=500` finds HTTP errors; `customer.id=42`
   finds everything that happened to one customer.
5. **Lookback / Min/Max Duration** — `min=1s` finds slow traces.
6. **Limit** — how many results to return (default 20).

Click a trace to see:

- **Left**: a tree of spans, parent-child relationships visible
  through indentation
- **Right**: a horizontal timeline; each bar is a span, the bar's
  length is its duration, the offset is when it started
- **Bottom**: the span's tags, events, process info, and **Logs**
  tab (the magic button)

### The Logs tab — the killer feature

When the `Logger` library is configured with OTel, every log record
carries the active `trace_id` and `span_id`. Jaeger's Logs tab
shows **all log records that happened inside this span** as a
chronological list:

```
span: POST /pay  (215 ms)
  ├─ DB INSERT     (180 ms)
  └─ audit.write    (10 ms)

  Logs emitted during this span:
  16:28:48.557 INFO  payment: charge_card starting  (customer_id=42)
  16:28:48.557 INFO  payment: stripe.charge starting  (amount=99.00)
  16:28:48.736 WARN  payment: stripe.charge retrying  (attempt=1)
  16:28:48.737 INFO  payment: stripe.charge succeeded
  16:28:48.737 INFO  audit: write_event starting
  16:28:48.747 INFO  audit: write_event succeeded
```

**You never had to write a single line of code to correlate the logs
with the spans.** That correlation is the killer feature of OTel +
`Logger`.

### How to find a slow trace

1. Pick your service in the dropdown.
2. Set **Min Duration** to `1s` (or whatever's "slow" for you).
3. Click the slowest trace.
4. Look at the timeline — the longest bar is your suspect.
5. Click that bar to see its tags and logs.

In a well-instrumented app, the longest span will often be a DB
query (auto-instrumented by `opentelemetry-instrumentation-psycopg2`)
or an HTTP call (auto-instrumented by `requests`). The fix is usually
at one of those two layers, not in your own code.

---

## 11. Custom spans: instrumenting your own code

OTel auto-instruments most popular libraries. For your own code, you
create spans manually. The `Logger` library's `factory.tracer`
exposes the OTel tracer:

```python
with LoggerFactory(config) as factory:
    log = factory.get_logger()

    # No OTel span? trace_id and span_id are zero (W3C "no trace").
    log.info("no span here")
    # {"trace_id": "00000000000000000000000000000000", "span_id": "0000000000000000", ...}

    # Start a span — every log line inside gets the same trace/span ids.
    with factory.tracer.start_span("process-invoice") as span:
        span.set_attribute("invoice.amount", 99.00)
        span.set_attribute("customer.id", 42)
        log.info("processing invoice")
        # {"trace_id": "ba37f26a98168a52912ff49c28b9adcc", "span_id": "4afe13018a01793f", ...}

        # Nested spans get the parent's trace_id but their own span_id.
        with factory.tracer.start_span("call-stripe") as sub:
            sub.set_attribute("stripe.amount", 99.00)
            log.info("calling stripe")
            # Same trace_id, different span_id.
```

The span tree in Jaeger:

```
process-invoice (root)
   └─ call-stripe
```

When the `with` block exits, the span is closed and the SDK ships it
to Jaeger. If you forget `provider.shutdown()` (or
`factory.shutdown()`) on shutdown, the last batch of spans is lost —
`BatchSpanProcessor` flushes every 5 seconds (default), so anything
within 5 s of `kill` is at risk.

### Recording exceptions

`start_as_current_span` accepts a `record_exception` flag:

```python
from opentelemetry.trace import Status, StatusCode

try:
    with factory.tracer.start_span("risky-op") as span:
        do_thing()
except Exception as e:
    log.error("failed", extra={"error.type": type(e).__name__})
    raise
```

For full automatic exception capture, use the lower-level
`tracer.start_as_current_span(..., record_exception=True,
set_status_on_exception=True)`. The OTel SDK then attaches the
exception as a span event **and** sets the span's status to
`ERROR`.

### A common pattern: the "trace every request" decorator

```python
def traced(name: str):
    def deco(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            factory = factory_registry.active()
            with factory.tracer.start_span(name) as span:
                span.set_attribute("function.name", func.__name__)
                return func(*args, **kwargs)
        return wrapper
    return deco
```

The `Logger` library's `@function_log` decorator already starts a
span around the function call (via `LoggingInstrumentor`). You
don't need a separate `@traced` unless you want manual attribute
control.

---

## 12. Trace context propagation across boundaries

This is the section most people skip. **Don't.**

### The problem

```
   Service A
     │
     │  HTTP call to service B
     ▼
   Service B
     │
     │  DB query
     ▼
   Postgres
```

For the trace to stitch together across these boundaries, **service A
must inject the trace context into the HTTP request, and service B
must extract it.** OTel auto-instrumentation does this for you for
`requests`, `httpx`, `urllib3`, `boto3`, `grpc`, and many others —
as long as both sides have the right `opentelemetry-instrumentation-*`
package installed.

### The headers

When service A makes a call, OTel adds these headers to the request:

```
traceparent: 00-ba37f26a98168a52912ff49c28b9adcc-4afe13018a01793f-01
tracestate:  (vendor-specific extensions, often empty)
```

The format is W3C [Trace Context](https://www.w3.org/TR/trace-context/):

```
00-<trace_id 32hex>-<span_id 16hex>-<flags 2hex>
   |              |                |    |
   |              |                |    └ 01 = sampled, 00 = not
   |              |                └─────── parent span id
   |              └────────────────────── this span's id (in receiver)
   └──────────────────────────────────── version
```

When service B receives the request, OTel's `WSGI`/`ASGI`
middleware extracts the headers and sets the trace context. Any span
started inside service B will have the same `trace_id` and the
parent's `span_id` as its `parent_span_id`.

### The message-broker case (RabbitMQ)

The same idea applies to AMQP messages. The `Logger` library's
`AMQPSettings` doesn't auto-inject trace headers, so the trace ends
at the producer. To continue it across the broker, you'd need to
manually inject the trace context into the message properties:

```python
from opentelemetry import trace
from opentelemetry.propagate import inject

properties = pika.BasicProperties(
    headers=inject({}),   # injects {traceparent, tracestate, ...}
)
ch.basic_publish(exchange="...", routing_key="...", body=...,
                 properties=properties)
```

And on the consumer side, extract:

```python
from opentelemetry.propagate import extract

def on_message(ch, method, properties, body):
    ctx = extract(properties.headers or {})
    with tracer.start_as_current_span("consume", context=ctx):
        process(body)
```

This is straightforward to add to `Logger` in a follow-up; the current
focus is on getting the AMQP pipe right. **Until then, the trace
stops at the producer**, and the AMQP consumer's records get a
fresh trace id.

### The async case (asyncio)

OTel's context propagation works with `asyncio` via the
`opentelemetry-instrumentation-asyncio` package. The TL;DR: the
`ContextVar`-based context flows through `await` boundaries
natively. **You don't have to do anything** for traces to
propagate across `await` calls — but you do need to start the spans
yourself (or use the auto-instrumentation).

### The thread / process case (threading, multiprocessing)

Context propagation **does not** cross thread or process boundaries
automatically. To pass a trace from one thread to another:

```python
import contextvars
from opentelemetry import context

# In thread A:
ctx = context.get_current()
# Pass `ctx` to thread B (e.g. via a queue)

# In thread B:
token = context.attach(ctx)
try:
    # Your work here. Spans start with the right parent.
    ...
finally:
    context.detach(token)
```

The `Logger` library's `Tracer` class already uses `ContextVar` under
the hood (via `contextvars.ContextVar`), so this is a manual
orchestration you do once per "context boundary" in your code.

---

## 13. Sampling: which traces to keep

Storing every trace is expensive. At 1% of a busy service (say
10,000 req/s) you produce 100 traces/s — manageable. At 100% (10,000
traces/s), Jaeger chokes.

### Two flavors of sampling

| Type | When decided | Pros | Cons |
|---|---|---|---|
| **Head-based** | At the start of the trace (root span) | Simple; cheap; works at the edge | Drops interesting slow traces |
| **Tail-based** | After the trace is complete | Keeps all slow / failed traces | Needs to buffer all spans; expensive |

The `Logger` library's `sample_ratio` is head-based: at the root
span, flip a coin; if the coin says "drop", don't record the rest
of the trace.

```python
otel=OTelSettings(
    enabled=True,
    sample_ratio=0.05,  # keep 5% of traces
)
```

### Picking the right ratio

| Traffic | Suggested ratio | Reasoning |
|---|---|---|
| < 100 req/s | 1.0 (keep all) | Storage is cheap; debugging is invaluable |
| 100 – 1000 req/s | 0.1 – 0.5 | Plenty of traces for percentiles; storage ~ 10GB/day |
| 1000 – 10000 req/s | 0.01 – 0.1 | Storage ~ 10GB/day at 0.01; alert on tail-based sampling for errors |
| > 10000 req/s | 0.001 – 0.01 | Storage is the bottleneck; rely on metrics for aggregates and traces for samples |

For dev: 1.0. For prod: start at 0.1 and adjust based on Jaeger's
storage cost.

### The "keep all errors" trick

Head-based sampling is dumb about errors. The workaround: **emit
every error as a metric, then have a tail-sampler read those metrics
and decide what to keep**. This is what services like Datadog APM
do internally. The `Logger` library exposes only the head-based
sampler today; tail-based is a future feature.

The `Logger` library's `SamplingSettings` (a different setting) is
for **logs**, not traces:

```python
sampling=SamplingSettings(rate=0.1, min_level="WARNING", deterministic=True)
```

This keeps 100% of WARNING+ and 10% of INFO/DEBUG. Independent of
the OTel trace sampler.

---

## 14. Common production pitfalls

### 14.1 "I enabled OTel but no traces appear in Jaeger"

In order:

1. **Is the SDK actually configured?** Check
   `trace.get_tracer_provider()` returns a `TracerProvider`, not the
   `NoOp` default. The `Logger` library's `enabled=True` is what
   triggers this.
2. **Is the endpoint reachable?** `curl http://localhost:4317`
   (gRPC servers will return a 415/400 — that's normal, it's HTTP/2
   only). If the connection is refused, Jaeger isn't listening, or
   `COLLECTOR_OTLP_GRPC_HOST_PORT` is set to `localhost:4317` (won't
   accept non-localhost connections).
3. **Is sampling too aggressive?** Set `sample_ratio=1.0` for
   debugging.
4. **Is `provider.shutdown()` called?** If your process exits
   without calling it, the last batch of spans is lost.
5. **Check Jaeger's logs** (`docker logs logger-jaeger-1`) for
   connection errors or storage issues.

### 14.2 "My traces are split across services"

The most common cause: the `traceparent` header isn't being
propagated. Check:

- Is `opentelemetry-instrumentation-requests` (or `httpx` /
  `urllib3` / `boto3` / `grpc`) installed on **both** sides?
- Is the receiving service running OTel's WSGI/ASGI middleware
  (`opentelemetry-instrumentation-wsgi` / `opentelemetry-instrumentation-asgi`)?
- For RabbitMQ / Kafka: are you injecting the trace context into
  message properties and extracting on the consumer?

### 14.3 "Jaeger is using too much memory / disk"

- Lower the sampling rate.
- Set a TTL on the storage backend (Jaeger's `SPAN_STORAGE_TTL` env
  var defaults to ~2 days).
- For high-throughput services, move to a tail-based sampler so
  you only keep slow / failed traces.
- Configure [Badger](https://github.com/dgraph-io/badger) as the
  storage backend (single-binary, no Cassandra/ES dep).

### 14.4 "Spans are nested wrong / wrong parent"

You have two `TracerProvider`s in the same process. This happens
when you create a tracer manually somewhere AND the SDK is
configured. The `Logger` library's OTel setup is idempotent — it
checks `isinstance(trace.get_tracer_provider(), TracerProvider)`
before configuring — so re-importing is safe. But if some other
code does `TracerProvider(...)` directly, you'll have two
providers and parent-child relationships break.

The fix: always go through `Logger`'s OTel config; never create a
`TracerProvider` directly.

### 14.5 "Clock skew is making spans look weird"

Jaeger doesn't enforce ordering, so a span starting at `t=10s` may
appear after one that started at `t=5s` if the second machine's
clock is ahead. Run NTP on every host. The `Logger` library's logs
include a `timestamp` field for the same reason.

---

## 15. Where to go next

You've now seen every primitive the `Logger` library uses to push
traces to Jaeger. From here:

- **Add the `LoggingInstrumentor` for your HTTP framework.** Run
  `examples/fastapi_middleware.py` and watch the trace tree
  populate with auto-instrumented spans for `requests`, `httpx`,
  `boto3`, etc.
- **Add `opentelemetry-instrumentation-*` packages** for the
  libraries you use (`psycopg2`, `boto3`, `redis`, `kafka-python`,
  ...). Each adds auto-spans around calls to that library.
- **Configure sampling per environment.** Dev: 1.0. Staging:
  0.1. Prod: 0.01 with tail-based for errors.
- **Add resource attributes.** `Resource.create({"service.name":
  ..., "service.version": ..., "deployment.environment": ...})`
  shows up in Jaeger as columns you can filter on.
- **Read the OTel spec.** <https://opentelemetry.io/docs/specs/otel/>
  — long, but well-organized.
- **Compare with alternatives.** [Grafana Tempo](https://grafana.com/oss/tempo/)
  is cheaper to store at scale (object storage only); [SigNoz](https://signoz.io)
  combines traces + metrics + logs in one UI; [Honeycomb](https://honeycomb.io)
  is a SaaS with great bubble-up debugging.

Happy tracing.
