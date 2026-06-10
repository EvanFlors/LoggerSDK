"""
Consumer for the demo AMQP exchange.

Reads from the `otel-amqp-demo` exchange and prints one line per message
that lands on the `otel-amqp-demo` queue.

Run in a second terminal while the demo script is producing:
    python examples/rabbitmq_consumer.py

Press Ctrl-C to stop.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Make `src` importable when this script is run from anywhere.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pika


EXCHANGE = "otel-amqp-demo"
QUEUE = "otel-amqp-demo"
URL = "amqp://guest:guest@localhost:5672/"


def main() -> None:
    conn = pika.BlockingConnection(pika.URLParameters(URL))
    ch = conn.channel()
    # Match the demo's durability so the existing exchange/queue
    # declared by the producer are accepted (AMQP rejects a
    # redeclare with different args).
    ch.exchange_declare(exchange=EXCHANGE, exchange_type="fanout", durable=True, auto_delete=False)
    ch.queue_declare(queue=QUEUE, durable=True, auto_delete=False)
    ch.queue_bind(queue=QUEUE, exchange=EXCHANGE)

    print(f"[consumer] bound to queue={QUEUE!r}; waiting for messages…", flush=True)
    seen = 0
    try:
        for method, _props, body in ch.consume(QUEUE, inactivity_timeout=1):
            if method is None:
                continue
            seen += 1
            try:
                payload = json.loads(body)
            except Exception:
                payload = body.decode("utf-8", "replace")
            ts = time.strftime("%H:%M:%S")
            print(f"[consumer] {ts} #{seen:>5}  {payload}", flush=True)
            ch.basic_ack(method.delivery_tag)
    except KeyboardInterrupt:
        print(f"\n[consumer] stopped after {seen} messages", flush=True)
    finally:
        try:
            ch.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main() or 0)
