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
from src.core.logger import Logger


def function_log(*, show_args: bool = True, show_result: bool = True):
    """
    Decorator factory that logs function execution with file, class (if any),
    and function name using the central Logger.
    """

    def decorator(func: callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()

            # ------------------------------------------------------------
            # Resolve context deterministically
            # ------------------------------------------------------------
            module = inspect.getmodule(func)
            file_name = (
                module.__file__.rsplit("/", 1)[-1]
                if module and module.__file__
                else "<unknown>"
            )

            function_name = func.__name__

            class_name = None
            if args and hasattr(args[0], "__dict__"):
                class_name = args[0].__class__.__name__

            context_parts = [file_name]
            if class_name:
                context_parts.append(class_name)
            context_parts.append(f"{function_name}()")

            context = " | ".join(context_parts)

            logger = Logger().bind(context=context)

            try:
                # ------------------------------------------------------------
                # Log execution start
                # ------------------------------------------------------------
                if show_args:
                    logger.info(
                        f"Executing {function_name} in {file_name}"
                        f"\nargs: {json.dumps(args, default=str, indent=2)}"
                        f"\nkwargs: {json.dumps(kwargs, default=str, indent=2)}",
                        extra={"context": context}
                    )
                else:
                    logger.info("Executing function", extra={"context": context})

                # ------------------------------------------------------------
                # Execute function
                # ------------------------------------------------------------
                result = func(*args, **kwargs)

                elapsed = time.time() - start_time

                # ------------------------------------------------------------
                # Log execution end
                # ------------------------------------------------------------
                if show_result:
                    logger.info(
                        f"Finished {function_name}() in {elapsed:.4f} seconds.\n"
                        f"{json.dumps(result, default=str, indent=2)}", extra={"context": context}
                    )
                else:
                    logger.info(
                        f"Finished in {elapsed:.4f}s",
                        extra={"context": context}
                    )

                return result

            except Exception as exc:
                elapsed = time.time() - start_time
                logger.error(
                    f"Exception after {elapsed:.4f}s: {exc}",
                    extra={"traceback": traceback.format_exc()},
                )
                raise

        return wrapper

    return decorator


if __name__ == "__main__":

    @function_log()
    def sample_function(x, y, **kwargs):
        return x + y + sum(kwargs.values())

    sample_function(5, 10, z=15)