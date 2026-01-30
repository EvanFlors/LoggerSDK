# ---------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------
import os
import sys
import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict

# ---------------------------------------------------------------------
# Third party libraries
# ---------------------------------------------------------------------
from colorlog import ColoredFormatter


@dataclass
class LoggerConfig:
    """
    Logger configuration settings.
    """

    directory: str = "logs"
    name: str = "app"

    base: str = (
        "[%(asctime)s] [%(levelname)s] "
        "[%(context)s] "
        "- %(message)s"
    )
    level: int = logging.INFO
    date: str = "%Y-%m-%d %H:%M:%S"

    log_colors: Dict[str, str] = field(default_factory=lambda: {
        "DEBUG": "cyan",
        "INFO": "green",
        "WARNING": "bold_yellow",
        "ERROR": "red",
        "CRITICAL": "bold_red",
    })

    def formatter(self) -> ColoredFormatter:
        """
        Build and return a ColoredFormatter instance.
        """
        return ColoredFormatter(
            fmt="%(log_color)s" + self.base + "%(reset)s",
            datefmt=self.date,
            log_colors=self.log_colors,
        )


class ContextLogger(logging.LoggerAdapter):
    """
    Logger adapter that adds context information to log messages.
    """

    def process(self, msg: str, kwargs: dict):
        extra = kwargs.get("extra", {})

        if "context" not in extra or not extra["context"]:
            extra["context"] = Logger()._auto_context()

        kwargs["extra"] = extra
        return msg, kwargs


class Logger:
    """
    Singleton logger factory.
    """

    _instance: Optional["Logger"] = None
    _initialized: bool = False


    def __new__(cls) -> "Logger":
        """
        Create a new logger instance.

        Args:
            cls: The class of the logger instance.

        Returns:
            Logger: The singleton Logger instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


    def __init__(self, config: LoggerConfig = LoggerConfig()) -> None:
        """
        Initialize the logger with the given configuration.

        Args:
            config: The logger configuration settings.
        """
        if Logger._initialized:
            return

        Logger._initialized = True
        self.config = config

        self._logger = logging.getLogger(self.config.name)
        self._logger.setLevel(self.config.level)
        self._logger.propagate = False
        self._logger.handlers.clear()

        self._add_handler(logging.StreamHandler(sys.stdout))

        if self.config.directory:
            os.makedirs(self.config.directory, exist_ok=True)
            filename = f"{self.config.name}_{datetime.now():%Y%m%d_%H%M%S}.log"
            path = os.path.join(self.config.directory, filename)
            self._add_handler(logging.FileHandler(path))


    def _add_handler(self, handler: logging.Handler) -> None:
        """
        Add a logging handler to the logger.

        Args:
            handler: The logging handler to add.
        """
        handler.setLevel(self._logger.level)
        handler.setFormatter(self.config.formatter())
        self._logger.addHandler(handler)


    def _auto_context(self) -> str:
        """
        Automatically determine context from the call stack.

        Returns:
            str: Context string in the form:
                    <file>.<Class>.<function> or <file>.<function>
        """
        try:
            for frame_info in inspect.stack()[2:]:
                frame = frame_info.frame
                module = inspect.getmodule(frame)

                # Skip internal logging frames
                if not module:
                    continue
                if module.__name__.startswith("logging"):
                    continue
                if module.__name__ == __name__:
                    continue

                filename = os.path.basename(module.__file__) if module.__file__ else module.__name__
                function = frame_info.function
                lineno = frame_info.lineno

                # Detect class context if available
                for local_name, local_val in frame.f_locals.items():
                    if local_name == "self":
                        class_name = local_val.__class__.__name__
                        return f"{filename}:{lineno} {class_name}.{function}"
                return f"{filename}:{lineno} {function}"

        except Exception:
            return "unknown.context"


    def get_logger(self) -> ContextLogger:
        """
        Get a logger with automatic context.

        Returns:
            ContextLogger: Logger adapter instance.
        """
        return ContextLogger(self._logger, {})


    def bind(self, context: str) -> ContextLogger:
        """
        Bind a fixed context to the logger.

        Args:
            context: The context information.

        Returns:
            ContextLogger: Logger adapter instance.
        """
        return ContextLogger(self._logger, {"context": context})


logger = Logger().get_logger()

if __name__ == "__main__":
    def main():
        log = Logger().bind("testing")
        log.info("This is an info message.")
        log.error("This is an error message.")

    main()
