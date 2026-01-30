# ---------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------
import time
import traceback
import functools
import json
import inspect

# ---------------------------------------------------------------------
# Internal application imports
# ---------------------------------------------------------------------
from src.logger import Logger


def function_log(func):
    """
    Decorator that logs function execution with file, class (if any),
    and function name using the central Logger.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = None
        start_time = time.time()

        try:
            # ------------------------------------------------------------
            # Resolve context deterministically
            # ------------------------------------------------------------
            module = inspect.getmodule(func)
            file_name = (
                module.__file__.split("/")[-1]
                if module and module.__file__
                else "<unknown>"
            )

            function_name = func.__name__

            class_name = None
            if args:
                first_arg = args[0]
                if hasattr(first_arg, "__class__"):
                    # Instance or class method
                    class_name = first_arg.__class__.__name__

            if class_name:
                context = f"{file_name} | {class_name}.{function_name}()"
            else:
                context = f"{file_name} | {function_name}()"

            logger = Logger().bind(context)

            logger.info(
                f"Executing {function_name} in {file_name}.{class_name}\n"
                f"args: {json.dumps(args, default=str, indent=2)}\n"
                f"kwargs: {json.dumps(kwargs, default=str, indent=2)}",
                extra={"context": context}
            )

            # ------------------------------------------------------------
            # Execute function
            # ------------------------------------------------------------
            result = func(*args, **kwargs)

            elapsed = time.time() - start_time

            logger.info(
                f"Finished {function_name} in {file_name}.{class_name} in {elapsed:.4f} seconds\n"
                f"result: {json.dumps(result, default=str, indent=2)}",
                extra={"context": context}
            )

            return result

        except Exception as exc:
            elapsed = time.time() - start_time
            tb = traceback.format_exc()

            if logger:
                logger.error(
                    f"Exception after {elapsed:.4f}s: {exc}",
                    extra={"traceback": tb},
                )

            raise

    return wrapper


def class_log():
    """
    Class decorator that applies function_log to all public callables.
    """

    def decorator(cls):
        for attr_name, attr_value in cls.__dict__.items():
            if attr_name.startswith("_"):
                continue

            if not callable(attr_value):
                continue

            is_static = isinstance(attr_value, staticmethod)
            is_class = isinstance(attr_value, classmethod)

            original = (
                attr_value.__func__
                if is_static or is_class
                else attr_value
            )

            wrapped = function_log(original)

            if is_static:
                wrapped = staticmethod(wrapped)
            elif is_class:
                wrapped = classmethod(wrapped)

            setattr(cls, attr_name, wrapped)

        return cls

    return decorator