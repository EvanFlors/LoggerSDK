from src import LoggerConfig, LoggerFactory
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


def main() -> None:
    factory = LoggerFactory(LoggerConfig(
        service_name="test",
        level="INFO",
        directory="logs",
        json_logs=True,
        module_levels={"test": "DEBUG"},
        sampling={"rate": 1.0, "deterministic": True},
    ))
    try:
        log = factory.get_logger().bind(context="testing")
        log.set_trace("demo-trace")
        log.set_span("demo-span")
        log.info("embed.response", extra={"event": "embed.response", "status": 200})
        log.warning("This is a warning with extra fields", extra={"user_id": 123, "operation": "test"})

        s = SampleClass()
        s.instance_method(5, 10)
        s.class_method(5, 10)
        s.static_method(5, 10)

        sample_function(5, 10)
        error_function(5, 10)
    finally:
        factory.shutdown()


if __name__ == "__main__":
    main()
