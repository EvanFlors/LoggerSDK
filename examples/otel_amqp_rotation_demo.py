"""
End-to-end demo: structured logger with **all three sinks** wired up.

  1. **Console** (immediate, colored)              — for the developer.
  2. **Rotating file** (size + time, JSON)         — for local persistence.
  3. **RabbitMQ** (sync pika, batched)             — for downstream consumers
                                                     (ELK / Splunk / etc).
  4. **OpenTelemetry** (gRPC OTLP → collector
     → Jaeger)                                     — for distributed traces.

The demo:
- Publishes 5,000 records into a deliberate span ("process-invoices")
- Mixes INFO, WARNING, and ERROR
- Lets the file rotate by setting `max_bytes` small enough to demonstrate it
- Wraps a unit of work in an OTel span so the same `trace_id` appears in
  the console, the rotated JSON file, the AMQP message body, and Jaeger

Prerequisites (see `docker-compose.yml`):
- RabbitMQ on `amqp://guest:guest@localhost:5672/`
- Jaeger (all-in-one, OTLP enabled) on `http://localhost:4317` (gRPC),
  UI on `http://localhost:16686`
- No OTel collector in the middle: the demo exports OTLP straight to
  Jaeger's built-in receiver.

Run:
    python examples/otel_amqp_rotation_demo.py

Then:
- Tail the JSON file:
    tail -f logs/otel-amqp-demo.log
- Read the AMQP queue:
    python examples/rabbitmq_consumer.py
- View the trace in Jaeger:
    open http://localhost:16686  (service: otel-amqp-demo)
"""
from __future__ import annotations

import os
import random
import sys
import time
from pathlib import Path

# Make `src` importable when this script is run from anywhere (the
# repo root, the `examples/` dir, or another cwd).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src import LoggerConfig, LoggerFactory
from src.config.settings.amqp import AMQPSettings
from src.config.settings.otel import OTelSettings
from src.config.settings.rotation import RotationSettings
from src.decorators import class_log, function_log


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
# Use a small `max_bytes` so we get a visible rollover during the demo.
# In production, this would be 10-50 MB.
ROTATE_EVERY = int(os.environ.get("DEMO_MAX_BYTES", "8192"))
RECORDS = int(os.environ.get("DEMO_RECORDS", "5000"))

config = LoggerConfig(
    service_name="otel-amqp-demo",
    level="INFO",
    directory="logs",
    json_logs=True,
    module_levels={
        # Quiet down the noisy internals during the demo.
        "aio_pika": "WARNING",
        "aiormq": "WARNING",
    },
    rotation=RotationSettings(
        max_bytes=ROTATE_EVERY,
        backup_count=3,
        compress=True,            # gzip rolled files
    ),
    amqp=AMQPSettings(
        url="amqp://guest:guest@localhost:5672/",
        exchange="otel-amqp-demo",
        exchange_type="fanout",
        queue="otel-amqp-demo",
        # `durable=True` so the exchange + queue survive between the
        # producer's run and a consumer attaching later. `auto_delete`
        # is not exposed on `AMQPSettings`; we leave that to the
        # broker's default behavior (delete when last queue unbinds).
        durable=True,
        batch_size=200,
        flush_interval_s=0.5,
        transport="sync",
        fail_open=True,           # never crash the demo because the broker is down
    ),
    otel=OTelSettings(
        enabled=True,
        service_name="otel-amqp-demo",
        # Send OTel traces directly to Jaeger's built-in OTLP receiver
        # (gRPC, port 4317). The Jaeger all-in-one image enables this
        # receiver when COLLECTOR_OTLP_ENABLED=true. No OTel collector
        # in the middle — fewer moving parts.
        otlp_endpoint="http://localhost:4317",
        protocol="grpc",
        insecure=True,
        sample_ratio=1.0,         # demo: keep all traces
    ),
)


# ---------------------------------------------------------------------------
# Domain code, instrumented with `@function_log` and `@class_log`
# ---------------------------------------------------------------------------
@function_log(show_args=False, show_result=False)
def make_invoice(order_id: str, amount: float) -> dict:
    """Build a fake invoice record. Emits Execution + Result records."""
    time.sleep(0.001)
    return {
        "order_id": order_id,
        "amount": amount,
        "currency": "USD",
    }


@class_log()
class InvoiceService:
    """A tiny service class. Each public method gets entry/exit logs."""

    def charge(self, invoice: dict) -> str:
        # Simulate a small failure rate so we get some ERRORs in the logs.
        if random.random() < 0.02:
            raise RuntimeError(f"payment provider timeout for {invoice['order_id']}")
        return f"txn-{invoice['order_id']}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print(f"\n=== Logger end-to-end demo ===")
    print(f"  records:   {RECORDS}")
    print(f"  rotation:  {ROTATE_EVERY} bytes (then .gz)")
    print(f"  file:      logs/otel-amqp-demo.log")
    print(f"  AMQP:      amqp://localhost:5672/ (exchange=otel-amqp-demo)")
    print(f"  OTel:      http://localhost:4317 (gRPC) → Jaeger on :16686")
    print()

    # Pre-clean: clear the demo log file and any rolled files so the
    # "before / after" diff is clean.
    logs_dir = Path(config.directory)
    for old in logs_dir.glob("otel-amqp-demo.log*"):
        old.unlink()

    service = InvoiceService()

    with LoggerFactory(config) as factory:
        # A top-level "request" log is the easiest way to verify the
        # `trace_id` propagates through every sink. Every log line below
        # carries the same trace_id.
        log = factory.get_logger().bind(component="billing", env="demo")
        log.set_trace()
        log.set_span()

        log.info("demo starting", extra={"records": RECORDS})

        # Wrap the work in an OTel span. The Tracer.start_span helper
        # falls back to a no-op when OTel is disabled or not installed.
        with factory.tracer.start_span("process-invoices") as span:
            span.set_attribute("batch.size", RECORDS)
            t0 = time.perf_counter()
            errors = 0
            for i in range(RECORDS):
                invoice = make_invoice(f"ord-{i:05d}", amount=round(random.uniform(10, 500), 2))
                try:
                    service.charge(invoice)
                except RuntimeError:
                    errors += 1
                    log.error(
                        "charge failed",
                        extra={"order_id": invoice["order_id"], "type": "ChargeError"},
                    )
            elapsed = time.perf_counter() - t0
            span.set_attribute("batch.errors", errors)
            span.set_attribute("batch.elapsed_s", round(elapsed, 3))

        log.info(
            "demo complete",
            extra={"records": RECORDS, "errors": errors, "elapsed_s": round(elapsed, 3)},
        )

        # Force a final flush so the AMQP handler ships its remaining
        # batched records before the factory shuts down.
        factory.flush()

    # ---- Summary --------------------------------------------------------
    print("\n=== Sink summary ===")

    files = sorted(logs_dir.glob("otel-amqp-demo.log*"))
    total_bytes = sum(f.stat().st_size for f in files)
    print(f"  file:    {len(files)} file(s), {total_bytes} bytes total")
    for f in files:
        size = f.stat().st_size
        suffix = f.suffix + (".gz" if f.suffix == "" and f.with_suffix(f.suffix + ".gz").exists() else "")
        print(f"           - {f.name} ({size} bytes)")

    print(f"  AMQP:    exchange 'otel-amqp-demo' (run examples/rabbitmq_consumer.py)")
    print(f"  OTel:    trace visible in Jaeger at http://localhost:16686")
    print(f"           service: 'otel-amqp-demo', look for 'process-invoices'")


if __name__ == "__main__":
    main()
