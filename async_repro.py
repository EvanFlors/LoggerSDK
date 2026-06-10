"""End-to-end repro of the AMQPAsyncHandler fix.

Exercises:
  1. Async handler connecting to a real broker from a sync main thread.
  2. Many emits (10k records).
  3. Clean shutdown — must not produce 'coroutine ... was never awaited'
     or 'TimeoutError' warnings.
"""
import os
import sys
import time
import warnings

import src  # noqa: F401
from src import LoggerConfig, LoggerFactory
from src.config import AMQPSettings, OTelSettings


def main() -> int:
    warnings.simplefilter("error", RuntimeWarning)

    config = LoggerConfig(
        service_name="async-repro",
        level="INFO",
        directory="logs",
        json_logs=True,
        amqp=AMQPSettings(
            url="amqp://guest:guest@localhost:5672/",
            exchange="logs",
            exchange_type="fanout",
            queue="logs.async-repro",
            transport="async",
            batch_size=50,
            flush_interval_s=0.5,
            fail_open=False,  # we want to know if connect fails
        ),
        otel=OTelSettings(
            enabled=True,
            service_name="async-repro",
            exporter="console",
            protocol="grpc"
        )
    )

    factory = LoggerFactory(config)
    try:
        log = factory.get_logger().bind(component="repro")
        log.set_trace("trace-async")
        log.set_span("span-async")
        log.info("starting", extra={"n": 10_000})

        t0 = time.perf_counter()
        for i in range(10_000):
            log.info("tick", extra={"i": i})
        log.info(f"emit phase done in {time.perf_counter() - t0:.2f}s")
    finally:
        factory.shutdown()

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
