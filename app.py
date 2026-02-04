# ---------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------
import logging

# ---------------------------------------------------------------------
# Internal application imports
# ---------------------------------------------------------------------
from src.logger import Logger, LoggerConfig

from src.decorators.functions import function_log
from src.decorators.classes import class_log


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

    config = LoggerConfig(
        name="test",
        directory="testing",
        level=logging.INFO,
        module_levels={
            "src.core": logging.DEBUG,
        },
        deterministic=True,
        json_logs=False,
    )

    Logger.configure(config)
    logger_instance = Logger()
    logger_instance.bind("testing")
    logger = logger_instance.get_logger()

    sample = SampleClass()
    sample.instance_method(5, 10)
    sample.class_method(5, 10)
    sample.static_method(5, 10)

    sample_function(5, 10)
    error_function(5, 10)