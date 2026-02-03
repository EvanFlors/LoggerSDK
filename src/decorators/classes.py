# ---------------------------------------------------------------------
# Internal application imports
# ---------------------------------------------------------------------
from src.decorators.functions import function_log


def class_log(*, show_args: bool = True, show_result: bool = True):
    """
    Class decorator that applies function_log to all public callables:
    - instance methods
    - class methods
    - static methods
    """

    def decorator(cls):
        for attr_name, attr_value in cls.__dict__.items():
            if attr_name.startswith("_"):
                continue

            # ------------------------------------------------------------
            # Unwrap descriptors
            # ------------------------------------------------------------
            is_static = isinstance(attr_value, staticmethod)
            is_class = isinstance(attr_value, classmethod)

            if is_static or is_class:
                func = attr_value.__func__
            else:
                func = attr_value

            if not callable(func):
                continue

            # ------------------------------------------------------------
            # Apply function_log (decorator factory)
            # ------------------------------------------------------------
            wrapped = function_log(
                show_args=show_args,
                show_result=show_result
            )(func)

            # ------------------------------------------------------------
            # Re-wrap descriptor
            # ------------------------------------------------------------
            if is_static:
                wrapped = staticmethod(wrapped)
            elif is_class:
                wrapped = classmethod(wrapped)

            setattr(cls, attr_name, wrapped)

        return cls

    return decorator


if __name__ == "__main__":

    @class_log()
    class SampleClass:
        def instance_method(self, x, y):
            return x + y

        @classmethod
        def class_method(cls, x, y):
            return x + y

        @staticmethod
        def static_method(x, y):
            return x + y

    sample = SampleClass()
    sample.instance_method(5, 10)
    sample.class_method(5, 10)
    sample.static_method(5, 10)