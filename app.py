# ---------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------
import logging

# ---------------------------------------------------------------------
# Internal application imports
# ---------------------------------------------------------------------
from logger.logger import Logger
from logger.config import LoggingSettings

from logger.decorators.functions import function_log
from logger.decorators.classes import class_log


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
    return x / 0


if __name__ == "__main__":

    Logger.configure(
        LoggingSettings(
            level="INFO",
            name="test",
            directory="logs",
            module_levels={
                "test": "DEBUG",
            },
            deterministic=True,
        )
    )

    logger_instance = Logger()
    logger_instance.set_span("test_span")
    logger_instance.set_trace("test_trace")
    logger_instance.bind("testing")

    logger = logger_instance.get_logger()

    sample = SampleClass()
    sample.instance_method(5, 10)
    sample.class_method(5, 10)
    sample.static_method(5, 10)

    sample_function(5, 10)
    error_function(5, 10)