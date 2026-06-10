from src import LoggerConfig, LoggerFactory

config = LoggerConfig(
    service_name="my-service",
    level="INFO",
    json_logs=True,
    rotation={
        "max_bytes": 10 * 1024 * 1024,  # 10 MB
        "backup_count": 5,
        "when": "midnight",  # Rotate at midnight
    },
    amqp_settings={
        "url": "amqp://guest:guest@localhost:5672/",
        "exchange": "logs",
        "queue": "log_queue",
        "transport": "sync"
    },
    otel_settings={
        "enabled": True,
        "otlp_endpoint": "http://localhost:4317",
        "protocol": "grpc"
    }
)

factory = LoggerFactory(config)
log = factory.get_logger().bind("request")
log.set_trace()
log.info("started", extra={"user_id": 123})
factory.shutdown()
