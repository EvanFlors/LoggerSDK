# ---------------------------------------------------------------------
# Internal application imports
# ---------------------------------------------------------------------
from src.logger import logger_instance, LoggerConfig

from src.decorators.functions import function_log
from src.decorators.classes import class_log

@class_log(show_args=False, show_result=True)
class SampleClass:
    def instance_method(self, x, y):
        return x + y

    @classmethod
    def class_method(cls, x, y):
        return x + y

    @staticmethod
    def static_method(x, y):
        return x + y


@function_log(show_args=True, show_result=True)
def sample_function(x, y):
    return x + y


if __name__ == "__main__":

    config = LoggerConfig(
        name="test",
        directory="testing",
    )

    logger_instance.configure(config)

    sample = SampleClass()
    sample.instance_method(5, 10)
    sample.class_method(5, 10)
    sample.static_method(5, 10)

    sample_function(5, 10)