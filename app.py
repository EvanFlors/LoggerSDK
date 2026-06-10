from src import BoundLogger, LoggerConfig, LoggerFactory
from src.config import AMQPSettings
from src.decorators.classes import class_log
from src.decorators.functions import function_log


@class_log(show_args=False, show_result=False)
class SampleClass:
    def instance_method(self, x, y):
        return x + y

    @classmethod
    def class_method(cls, x, y):
        return x + y

    @staticmethod
    def static_method(x, y):
        return x + y


@function_log(show_args=False, show_result=False)
def sample_function(x, y):
    return x + y


@function_log(show_args=False, show_result=False)
def error_function(x, y):
    return x / y


def logger_factory() -> None:
    config = LoggerConfig(
        service_name="test",
        level="INFO",
        directory="logs",
        json_logs=True,
        module_levels={"test": "DEBUG"},
        sampling={"rate": 1.0, "deterministic": True},
        amqp=AMQPSettings(
            url="http://localhost:5672",
            exchange="logs.fanout",
            queue="billing-logs",
            transport="async",
        ),
    )

    with LoggerFactory(config) as factory:
        logger: BoundLogger = factory.get_logger()
        logger.set_trace("demo-trace")
        logger.set_span("demo-span")
        logger.info("embed.response", extra={"event": "embed.response", "status": 200})
        logger.warning("This is a warning with extra fields", extra={"user_id": 123, "operation": "test"})
        logger.error("This is an error message", extra={"error_code": "E001", "details": "Something went wrong"})

        s = SampleClass()
        s.instance_method(5, 10)
        s.class_method(5, 10)
        s.static_method(5, 10)

        sample_function(5, 10)
        error_function(5, 10)


if __name__ == "__main__":
    logger_factory()
