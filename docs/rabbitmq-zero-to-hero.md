# RabbitMQ Zero-to-Hero

A hands-on, no-prior-knowledge walkthrough of RabbitMQ — using the
`Logger` library as the running example so every concept is grounded in
something you'll actually use.

By the end of this guide you'll know:

- What a message broker is and why you'd use one
- The three things every RabbitMQ program needs: **connection,
  channel, queue**
- How the four exchange types route messages (`direct`, `topic`,
  `fanout`, `headers`)
- How to make messages survive a broker restart (`durable`, `persistent`)
- How to consume messages safely (acks, prefetch, redelivery)
- How to run RabbitMQ locally with the included `docker-compose.yml`
- How to wire the `Logger` library to publish to RabbitMQ
- How to consume those messages into another service
- Common production pitfalls and how to spot them

> **Time**: ~30 min reading + ~15 min hands-on.

---

## Table of Contents

1. [What is RabbitMQ?](#1-what-is-rabbitmq)
2. [Run RabbitMQ locally](#2-run-rabbitmq-locally)
3. [The mental model: connection, channel, queue](#3-the-mental-model-connection-channel-queue)
4. [Your first message in 30 seconds](#4-your-first-message-in-30-seconds)
5. [Exchanges: how messages find their queue](#5-exchanges-how-messages-find-their-queue)
6. [Durability: surviving broker restarts](#6-durability-surviving-broker-restarts)
7. [Acknowledgement: don't lose messages on the consumer side](#7-acknowledgement-dont-lose-messages-on-the-consumer-side)
8. [Routing patterns: direct, topic, fanout, headers](#8-routing-patterns-direct-topic-fanout-headers)
9. [Putting it together: the Logger AMQP transport](#9-putting-it-together-the-logger-amqp-transport)
10. [Consuming Logger messages](#10-consuming-logger-messages)
11. [The management UI](#11-the-management-ui)
12. [Common production pitfalls](#12-common-production-pitfalls)
13. [Where to go next](#13-where-to-go-next)

---

## 1. What is RabbitMQ?

RabbitMQ is a **message broker**. Instead of one process calling another
directly (and waiting for a response), one process drops a message into
RabbitMQ and another process picks it up whenever it can.

```
   without RabbitMQ                    with RabbitMQ
   ----------------                   ----------------
   ┌──────┐   call    ┌──────┐        ┌──────┐  put  ┌──────────┐  get  ┌──────┐
   │ app  │ ────────► │ log │        │ app  │ ────► │ RabbitMQ │ ────► │ log  │
   │      │  waits    │ API  │        │      │       │          │       │ ship │
   └──────┘  ◄────── └──────┘        └──────┘       └──────────┘       └──────┘
             400ms                              immediate
```

### Why you'd want one

| Use case | Why RabbitMQ helps |
|---|---|
| Ship logs to an aggregator (Datadog, ELK, Splunk) | The app doesn't wait for the network; the broker buffers. |
| Decouple a web request from a slow background job | Request returns 202; job runs whenever the worker is free. |
| Fan-out the same event to many consumers | Bind multiple queues to one exchange. |
| Retry on failure | The broker holds the message until the consumer acks. |

In this guide we'll focus on the first case: **log shipping**, because
that's the `Logger` library's specialty.

### What makes RabbitMQ different from Kafka / NATS / Redis

| Broker | Strength | Weakness |
|---|---|---|
| **RabbitMQ** | Mature, easy to operate, flexible routing, good AMQP 0-9-1 story | Lower throughput than Kafka; needs Erlang node |
| Kafka | Very high throughput, durable, replayable log | More complex; overkill for log shipping |
| NATS | Tiny, fast, simple | At-most-once by default; less mature clustering |
| Redis Pub/Sub | Already in your stack | No persistence; no replay |

For log shipping with the `Logger` library, RabbitMQ is the right default:
high enough throughput for a single service, durable, easy to run via
the included `docker-compose.yml`.

---

## 2. Run RabbitMQ locally

The repo already includes a `docker-compose.yml` that brings up RabbitMQ
and Jaeger. Let's use just RabbitMQ for this tutorial.

```bash
# Start RabbitMQ (and a management UI on :15672)
docker compose up -d rabbitmq

# Verify it's up
docker ps | grep rabbitmq
# logger-rabbitmq-1  rabbitmq:3.13-management  Up  ...  0.0.0.0:5672->5672, 0.0.0.0:15672->15672

# Open the management UI in your browser
open http://localhost:15672
# (login: guest / guest)
```

The two ports:

| Port | What it is |
|---|---|
| `5672` | **AMQP** — the actual broker port that apps connect to |
| `15672` | **Management UI / HTTP API** — for humans and tooling |

If `docker compose up -d rabbitmq` failed, the most common cause is
that another container is already on those ports. Check with
`docker ps -a` and remove the conflicting one with
`docker rm -f <name>`.

### Verify from Python

You don't need to install anything yet — the `pika` library will be
available once we install the AMQP extras in a moment. For now, just
confirm you can reach the broker with `nc`:

```bash
# Should print something like: AMQP\x00\x00\x09\x01
nc -w 1 localhost 5672 | head -c 8 | xxd
```

If you see `AMQP` in the output, the broker is reachable.

---

## 3. The mental model: connection, channel, queue

RabbitMQ has three core objects you'll touch in every program.

### Connection

A TCP connection between your app and the broker. Opening one is
expensive (TCP handshake + AMQP handshake + auth). **You want exactly
one per process, shared across all publishers/consumers.**

In Python:

```python
import pika
params = pika.URLParameters("amqp://guest:guest@localhost:5672/")
conn = pika.BlockingConnection(params)
```

The `BlockingConnection` is fine for sync code (workers, scripts, web
handlers that aren't `asyncio`). For `asyncio` services, use `aio-pika`
or the `AMQPAsyncHandler` from the `Logger` library.

### Channel

A multiplexed stream of commands inside a connection. **You want one
per thread, or one per logical "thing you're doing".** A channel is
cheap; don't share channels across threads.

```python
ch = conn.channel()
```

### Queue

A buffer of messages. **Producers publish to an exchange; the exchange
routes the message to one or more queues; consumers read from queues.**

```python
ch.queue_declare(queue="my-queue", durable=True)
```

You typically don't need to think about exchanges and queues separately
when starting out — for a single producer → single consumer flow you can
use the **default exchange** (empty string `""`) and publish directly
to a queue by its name. The `Logger` library does exactly this.

```
   publisher ──► default exchange ──► "logs" queue ──► consumer
```

---

## 4. Your first message in 30 seconds

Two terminals. **In terminal 1**, start a consumer that prints
whatever it receives:

```bash
. venv/bin/activate
pip install pika
python <<'PY'
import pika
conn = pika.BlockingConnection(pika.URLParameters("amqp://guest:guest@localhost:5672/"))
ch = conn.channel()
ch.queue_declare(queue="hello")
ch.basic_consume(queue="hello", auto_ack=True,
                 on_message_callback=lambda ch, m, p, body: print("got:", body))
print("waiting...")
ch.start_consuming()
PY
```

**In terminal 2**, publish a single message:

```bash
. venv/bin/activate
python <<'PY'
import pika
conn = pika.BlockingConnection(pika.URLParameters("amqp://guest:guest@localhost:5672/"))
ch = conn.channel()
ch.queue_declare(queue="hello")
ch.basic_publish(exchange="", routing_key="hello", body=b"world")
print("sent")
conn.close()
PY
```

You should see `got: b'world'` in terminal 1. **You just shipped a
message end-to-end.**

What happened:

```
Terminal 2                    Terminal 1
    │                              │
    │  basic_publish(exchange="",  │
    │    routing_key="hello",      │
    │    body=b"world")            │
    │ ─────────► exchange "" ─► queue "hello"
    │                              │
    │                       basic_consume picks it up
    │                              │
    │                       callback runs:
    │                       print("got:", body)
    │                              ▼
    │                          got: b'world'
```

---

## 5. Exchanges: how messages find their queue

A **direct publish** to the default exchange (above) works, but in real
systems you want to *route* messages. That's what **exchanges** are for.

```
   producer
      │  basic_publish(exchange="logs", routing_key="...")
      ▼
   exchange "logs"
      │
      ├── routing_key="billing"   ─► queue "billing-logs"
      ├── routing_key="auth"      ─► queue "auth-logs"
      └── routing_key="billing"   ─► queue "audit-logs"   (also wants billing)
```

The four exchange types determine *how* the routing_key is interpreted:

| Type | Routing | Use when |
|---|---|---|
| **`direct`** | Exact match on routing_key | One producer, multiple distinct consumers |
| **`topic`** | Wildcard match (`billing.*` matches `billing.eu`) | Hierarchical categories (`region.us.payment`) |
| **`fanout`** | Ignores routing_key, broadcasts to all bound queues | Publish-once, many-subscribers (e.g. log shippers) |
| **`headers`** | Match on message headers instead of routing_key | Rare; complex routing on metadata |

The `Logger` library uses **fanout** by default. Reasoning: every
consumer of the "logs" exchange wants *every* log message, regardless of
category. Fanout is the simplest fit and matches the "ship logs to N
downstream tools" use case.

### Try fanout

**In terminal 1**, declare an exchange and bind a queue to it, then consume:

```python
ch.exchange_declare(exchange="logs", exchange_type="fanout", durable=False)
ch.queue_declare(queue="logs-cli", durable=False, auto_delete=True)
ch.queue_bind(queue="logs-cli", exchange="logs")
ch.basic_consume(queue="logs-cli", auto_ack=True,
                 on_message_callback=lambda c, m, p, body: print("got:", body))
print("waiting...")
ch.start_consuming()
```

**In terminal 2**, publish to the exchange (routing_key is ignored):

```python
ch.exchange_declare(exchange="logs", exchange_type="fanout", durable=False)
for i in range(3):
    ch.basic_publish(exchange="logs", routing_key="anything",
                     body=f"msg-{i}".encode())
print("sent 3")
```

Terminal 1 will print `got: b'msg-0'`, `got: b'msg-1'`, `got: b'msg-2'`.

### Add a second subscriber to the same exchange

**In terminal 3**:

```python
ch.exchange_declare(exchange="logs", exchange_type="fanout", durable=False)
ch.queue_declare(queue="logs-audit", durable=False, auto_delete=True)
ch.queue_bind(queue="logs-audit", exchange="logs")
ch.basic_consume(queue="logs-audit", auto_ack=True,
                 on_message_callback=lambda c, m, p, body: print("audit:", body))
print("audit waiting...")
ch.start_consuming()
```

Publish one more message from terminal 2. **Both** terminal 1 AND
terminal 3 receive it. **That's fanout: one publish, many subscribers.**

```
   producer ──► exchange "logs" ──► "logs-cli"   ──► terminal 1
                                ├► "logs-audit" ──► terminal 3
```

This is exactly the architecture the `Logger` library uses: every
downstream tool (Datadog, ELK, S3) gets its own queue bound to the
"logs" exchange.

---

## 6. Durability: surviving broker restarts

If the broker restarts, by default **all your messages are lost**.
RabbitMQ has three orthogonal durability flags you have to combine
correctly:

| Object | Flag | Means |
|---|---|---|
| Exchange | `durable=True` | The exchange itself survives a broker restart. |
| Queue | `durable=True` | The queue survives a broker restart. |
| Message | `delivery_mode=2` (a.k.a. `persistent`) | The message body is written to disk. |

**All three must be set** for messages to survive a broker restart. If
any of them is missing, you lose data on restart.

```python
# All three: durable exchange, durable queue, persistent message
ch.exchange_declare(exchange="logs", exchange_type="fanout", durable=True)
ch.queue_declare(queue="logs-cli", durable=True)
ch.basic_publish(
    exchange="logs",
    routing_key="anything",  # ignored for fanout
    body=b"important",
    properties=pika.BasicProperties(delivery_mode=2),  # persistent
)
```

Verify it works: kill the broker with `docker restart logger-rabbitmq-1`,
restart your consumer, and the message is still there.

> ⚠️ **Gotcha**: changing the durability of an existing queue throws
> `PRECONDITION_FAILED`. If you change from `durable=False` to
> `durable=True`, you have to delete the queue first
> (`ch.queue_delete(queue="...")`).

The `Logger` library's `AMQPSettings` defaults to `durable=True` for this
reason — you almost always want durability in production.

---

## 7. Acknowledgement: don't lose messages on the consumer side

A message is **delivered** when the broker hands it to a consumer over
the wire. It's **acknowledged** (`ack`) when the consumer tells the
broker "I'm done with it, you can delete it." Between delivery and ack,
the message is "in flight."

Three modes:

| Mode | Set with | What happens on consumer crash |
|---|---|---|
| `auto_ack=True` | flag on `basic_consume` | Message is acked immediately on delivery. **Lost on crash.** |
| `auto_ack=False` + manual `basic_ack` | default | Message stays in queue until consumer acks. **Safe.** |
| `auto_ack=False` + `basic_nack` | on error | Message is requeued or sent to a dead-letter queue. **Safer.** |

`auto_ack=True` is convenient for demo scripts; **never use it in
production.**

```python
def on_message(ch, method, properties, body):
    try:
        process(body)
        ch.basic_ack(delivery_tag=method.delivery_tag)   # ✅ done
    except Exception as e:
        ch.basic_nack(delivery_tag=method.delivery_tag,
                      requeue=True)                       # 🔁 try again
        # OR: ch.basic_nack(requeue=False)              # ❌ drop (use a DLQ in prod)

ch.basic_consume(queue="logs", on_message_callback=on_message, auto_ack=False)
```

### Prefetch: don't give one consumer the whole queue

By default, RabbitMQ pushes messages to a consumer as fast as it can
ask for them. If you have 10,000 messages and one slow consumer, that
consumer ends up with 10,000 in flight. `basic_qos(prefetch_count=N)`
caps the number:

```python
ch.basic_qos(prefetch_count=50)  # at most 50 unacked messages per consumer
ch.basic_consume(queue="logs", on_message_callback=on_message)
```

A good rule of thumb: `prefetch_count` ≈ "how many messages one consumer
can hold in memory while processing". For a `Logger` consumer that
just writes to a file, 100–1000 is fine. For a CPU-bound worker, 1–10.

The `Logger` library's `AMQPSettings` exposes `batch_size` and
`flush_interval_s` which together do something similar on the **producer**
side — the producer batches N records (or waits T seconds) before
flushing to the broker. The two together give you end-to-end backpressure.

---

## 8. Routing patterns: direct, topic, fanout, headers

This is the section that people skim and then regret. Let me make it
sticky with a single example per type.

### 8.1 direct — exact match

```
exchange "tasks"   routing_key="send-email"   ─► queue "email-worker"
                    routing_key="render-pdf"   ─► queue "pdf-worker"
                    routing_key="send-email"   ─► queue "audit"  (also wants email)
```

Use when you have a small, fixed set of routing_keys and you want exact
dispatch.

### 8.2 topic — wildcard match

Routing keys are dot-separated: `region.us.billing`, `priority.high`.

```
exchange "events"   routing_key="*.us.*"         ─► queue "us-events"
                    routing_key="*.billing"      ─► queue "billing-events"
                    routing_key="#"               ─► queue "audit"  (everything)
```

`*` matches one word; `#` matches zero or more. The `Logger` library
doesn't use topic exchanges by default, but the `routing_key` field in
its config is ready for it.

### 8.3 fanout — broadcast

`Logger`'s default. Every queue bound to the exchange gets every
message. Use it whenever the same event is interesting to more than
one consumer and consumers don't need to filter.

### 8.4 headers — match on AMQP headers

Most people should never use this. If you need to route on
key/value pairs and you don't want to encode them in the routing key,
this is your escape hatch. `Logger` doesn't currently use it.

### Decision tree

```
Should every consumer see every message?
  ├─ Yes ─► fanout
  └─ No
       │
       Do you have a small, fixed set of categories?
         ├─ Yes ─► direct
         └─ No, hierarchical ─► topic
       └─ No, multi-attribute ─► headers (rare)
```

---

## 9. Putting it together: the Logger AMQP transport

Now that you understand the building blocks, the `Logger` library's
`AMQPSettings` should feel obvious:

```python
from src import LoggerConfig
from src.config.settings.amqp import AMQPSettings

config = LoggerConfig(
    service_name="billing-api",
    amqp=AMQPSettings(
        url="amqp://guest:guest@localhost:5672/",   # connection
        exchange="logs",                            # fanout
        exchange_type="fanout",
        queue="logs.billing-api",                   # one queue per service
        durable=True,                               # survive restart
        batch_size=200,                             # producer-side batching
        flush_interval_s=1.0,
        transport="sync",                            # or "async" (aio-pika)
        fail_open=True,                              # never crash the app
    ),
)

with LoggerConfig(config) as factory: ...   # see the Logger tutorial
```

What this gives you:

```
your code
  └─► LoggerFactory
        └─► ConsoleHandler       (immediate, for you)
        └─► AMQPSyncHandler      (queued, batched, fanout)
              │  batches 200 records or 1s
              │  publishes to:
              │
              ▼
        exchange "logs" (fanout, durable)
              │
              ├─► queue "logs.billing-api"  (declared by the handler)
              ├─► queue "logs.datadog"     (declared by the Datadog consumer)
              └─► queue "logs.s3"          (declared by the S3 archiver)
```

Every consumer declares its own queue and binds it to `"logs"`. The
producer never knows who's listening. **That's the win.**

### The four knobs that matter

| Knob | Default | What it controls |
|---|---|---|
| `batch_size` | 100 | Producer waits for N records before publishing |
| `flush_interval_s` | 1.0 | Producer waits at most T seconds before publishing |
| `transport` | `"sync"` | `sync` = pika, `async` = aio-pika with its own event loop |
| `fail_open` | `True` | If the broker is down, log to stderr and continue (don't crash) |

For a busy web service: `batch_size=200, flush_interval_s=0.5,
transport="async"`. For a CLI tool: `batch_size=50, flush_interval_s=2.0,
transport="sync"`.

### Sync vs async transport

- **`sync` (pika)**: the producer's thread is blocked briefly while
  pika publishes. With `batch_size=200` and `flush_interval_s=0.5` the
  blocking is sub-millisecond per record. Fine for scripts, workers,
  and most web apps.

- **`async` (aio-pika)**: the handler owns a dedicated asyncio loop
  in a daemon thread. The producer's `emit()` is a non-blocking
  `queue.SimpleQueue.put_nowait`. Use this when the producer is
  itself an `asyncio` program and you don't want pika's blocking
  I/O on the event loop.

The `Logger` library's `AMQPAsyncHandler` uses the dedicated-loop
pattern (similar to what the Java and Go clients do) so it works
correctly **from both sync and async** code.

---

## 10. Consuming Logger messages

The included `examples/rabbitmq_consumer.py` is a one-liner consumer.
It declares the queue and the exchange with the same settings the
`Logger` producer used (so they agree on `durable=True`), then prints
every message it receives.

```bash
. venv/bin/activate
python examples/rabbitmq_consumer.py
```

In a second terminal, run the demo:

```bash
python examples/otel_amqp_rotation_demo.py
```

You should see a stream of JSON lines:

```
[consumer] 10:41:40 #    1  {'message': 'demo starting', 'level': 'INFO', ..., 'trace_id': 'd7f3...', ...}
[consumer] 10:41:40 #    2  {'message': 'Executing function', ..., 'trace_id': 'ba37...', ...}
[consumer] 10:41:51 #10000  {'message': 'Finished in 0.0034s', ..., 'trace_id': 'ba37...', ...}
```

Notice the **`trace_id`** is the same in the consumer's payload as in
the rotating JSON log and in Jaeger — the same W3C trace id
propagates end-to-end.

### Routing to Datadog / ELK / S3

Each downstream tool needs its own queue. Create one per tool:

```python
import pika

conn = pika.BlockingConnection(pika.URLParameters("amqp://guest:guest@localhost:5672/"))
ch = conn.channel()
ch.exchange_declare(exchange="logs", exchange_type="fanout", durable=True)

# Datadog: this consumer ships logs to Datadog's HTTP intake
ch.queue_declare(queue="logs.datadog", durable=True)
ch.queue_bind(queue="logs.datadog", exchange="logs")

# S3 cold storage: this consumer writes batches to S3
ch.queue_declare(queue="logs.s3", durable=True)
ch.queue_bind(queue="logs.s3", exchange="logs")
```

Now you have two independent consumers reading from the same
`"logs"` exchange. **Adding a new sink doesn't require touching the
producer or any other consumer.**

### Manual `basic_get` for one-off inspection

If you just want to peek at the queue without setting up a full
consumer loop:

```python
method_frame, properties, body = ch.basic_get(queue="logs.billing-api", auto_ack=True)
if method_frame:
    print(body)
```

`basic_get` polls once. Use `basic_consume` (as in
`examples/rabbitmq_consumer.py`) for streaming.

---

## 11. The management UI

`http://localhost:15672` is your friend. From here you can:

- **Queues → "logs.billing-api" → Get messages**: pull a few messages
  from the queue to inspect their content (with requeue=true so they
  aren't lost).
- **Queues → ... → Purge**: drop all messages in a queue. Useful when
  testing and you want a clean slate.
- **Exchanges → "logs" → Bindings**: see which queues are bound.
- **Admin → Users**: add/remove users.
- **Admin → Policies**: set TTLs, max-length, lazy mode at the
  exchange or queue level (a `max-length-bytes` policy is the
  safety valve for log shipping — never let logs OOM your broker).

A policy like this is a great safety net for log queues:

```json
{
  "max-length": 1000000,
  "max-length-bytes": 1073741824,
  "overflow": "drop-head"
}
```

This caps each queue at 1M messages / 1 GB, and on overflow drops the
**oldest** messages first. Combined with a downstream archiver, you
get bounded memory + complete log retention.

---

## 12. Common production pitfalls

### 12.1 "My messages disappeared"

Check, in order:

1. **Did the queue exist?** If the producer declares a queue with
   different arguments than the consumer (e.g. `durable=False` vs
   `True`), AMQP rejects the redeclare. The producer's records never
   land. Look at the management UI: if the queue has zero
   `messages_published`, your publish is failing silently.
2. **Are you ack'ing?** If the consumer crashes between delivery and
   `basic_ack`, the message is requeued indefinitely. Check the UI
   for a non-zero `messages_unacknowledged` count.
3. **Did the broker OOM?** `docker logs logger-rabbitmq-1 | grep -i
   'high watermark'`. Adjust `vm_memory_high_watermark` in
   `rabbitmq.conf` if so.
4. **Did you set `durable=True` on the queue AND `delivery_mode=2`
   on the message?** Both are needed for survival.

### 12.2 "My consumer is slow and the queue is growing"

You have three levers:

1. **Scale consumers** — add more processes/threads reading from the
   same queue. RabbitMQ load-balances across them.
2. **Increase `prefetch_count`** — but only if your consumer can
   actually process them in parallel.
3. **Batch the consumer's work** — instead of acking one record at
   a time, accumulate N records and ack them as a group.

### 12.3 "The broker is down and my service is hung"

Two fixes:

1. **`fail_open=True`** (the default in `Logger`) — the handler
   prints a single stderr warning and continues without the broker.
2. **Tune the connection timeout** — `connect_timeout_s` (default 5s)
   controls how long pika waits before giving up.

For services that **must not** lose messages, you need a local
on-disk buffer (a "write-ahead log") that drains to RabbitMQ when the
broker comes back. The `Logger` library's queue handler already does
this in-process: it buffers records while the broker is down and
flushes them once the connection is re-established. For multi-host
durability, you'd add something like [WAL](https://github.com/etcd-io/etcd/tree/main/wal)
or a dedicated WAL service.

### 12.4 "I changed `durable=True` to `durable=False` and nothing works"

`PRECONDITION_FAILED`. AMQP refuses to redeclare a queue with
different arguments. Two options:

- **Delete and redeclare** — `ch.queue_delete(queue="..."); ch.queue_declare(...)`.
- **Version your queues** — use a new queue name (`logs.v2`) and
  migrate consumers over. This is the production-safe path.

### 12.5 "Connections keep multiplying"

You're creating a new `BlockingConnection` per record. Each connection
is a TCP socket + AMQP handshake + auth — ~50ms minimum. **Always
reuse a single connection per process** and pass channels around.

The `Logger` library does this correctly: one `AMQPSyncHandler`
instance owns one connection for the life of the handler.

---

## 13. Where to go next

You've now seen every primitive the `Logger` library uses to ship
records to RabbitMQ. From here:

- **Wire it to a real aggregator.** Replace the `examples/rabbitmq_consumer.py`
  body with a Datadog / Splunk / ELK / Loki / S3 client. Each
  one is a fanout consumer; the broker handles the rest.
- **Read the AMQP 0-9-1 spec.** [The spec is short and readable.](https://www.rabbitmq.com/specification.html)
  You now have enough background to read it without falling asleep.
- **Look at the `Logger` source.** `src/handlers/amqp/sync.py` is
  ~100 lines and does exactly what we covered: declare exchange +
  queue, bind, publish in batches, ack on close.
- **Run a real broker in production.** RabbitMQ ships a Kubernetes
  operator, a [Quorum Queue](https://www.rabbitmq.com/quorum-queues.html)
  type for high durability, and [Federation](https://www.rabbitmq.com/federation.html)
  for cross-cluster replication.

Happy shipping.
