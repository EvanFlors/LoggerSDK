import time

from fastapi import FastAPI, Request

from obserlog.config import LoggerConfig
from obserlog.factory import LoggerFactory


def build_app() -> FastAPI:
    factory = LoggerFactory(LoggerConfig(
        service_name="api",
        level="INFO",
        json_logs=True,
        otel={"enabled": True, "otlp_endpoint": "http://localhost:4317", "protocol": "grpc"},
    ))
    app = FastAPI(lifespan=factory.lifecycle)

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        log = factory.get_logger().bind(path=request.url.path, method=request.method)
        log.set_trace()
        log.set_span()
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = (time.perf_counter() - start) * 1000
        log.info(
            "request",
            extra={
                "type": "access",
                "status": response.status_code,
                "elapsed_ms": round(elapsed, 2),
            },
        )
        return response

    return app