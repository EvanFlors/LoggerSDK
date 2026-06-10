"""Stress test: create and shut down many factories in succession."""
import time
from src import LoggerConfig, LoggerFactory
from src.config import AMQPSettings

n = 50
t0 = time.perf_counter()
for i in range(n):
    config = LoggerConfig(
        service_name=f"stress-{i}",
        directory="logs",
        amqp=AMQPSettings(
            url="amqp://guest:guest@localhost:5672/",
            exchange="logs",
            exchange_type="fanout",
            queue=f"logs.stress-{i}",
            transport="async",
            batch_size=10,
            flush_interval_s=0.2,
            fail_open=False,
        ),
    )
    with LoggerFactory(config) as f:
        log = f.get_logger()
        log.info(f"hello {i}")
print(f"{n} factory lifecycles completed in {time.perf_counter() - t0:.2f}s")
