# ---------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------
import os
import sys
import inspect
import logging
import functools
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
    date: str = "%d-%m-%y | %H:%M:%S"

    log_colors: Dict[str, str] = field(default_factory=lambda: {
        "DEBUG": "cyan",
        "INFO": "blue",
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

    def process(
        self,
        msg: str,
        kwargs: dict
    ):
        """
        Process the log message and add context information.

        Args:
            msg: The log message.
            kwargs: Additional keyword arguments.

        Returns:
            Tuple[str, dict]: The processed log message and updated keyword arguments.
        """

        extra = kwargs.setdefault("extra", {})

        if "context" not in extra or not extra["context"]:
            extra["context"] = self.extra.get("context") or Logger._auto_context_cached()

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


    def __init__(self, config: LoggerConfig = None) -> None:
        """
        Initialize the logger with the given configuration.

        Args:
            config: The logger configuration settings.

        Returns:
            None
        """

        if not Logger._initialized and config is not None:
            self._initialize(config)


    def _initialize(self, config: LoggerConfig) -> None:
        """
        Initialize the logger with the given configuration.

        Args:
            config: The logger configuration settings.

        Returns:
            None
        """

        Logger._initialized = True
        self.config = config

        self._logger = logging.getLogger(config.name)
        self._logger.setLevel(config.level)
        self._logger.propagate = False

        if not self._logger.handlers:
            self._add_console_handler()
            if config.directory:
                self._add_file_handler()


    # --------------------------------------------------
    # Handlers
    # --------------------------------------------------
    def _add_console_handler(self):
        """
        Add a console handler to the logger.
        """
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(self.config.formatter())
        handler.setLevel(self.config.level)
        self._logger.addHandler(handler)


    def _add_file_handler(self):
        """
        Add a file handler to the logger.
        """

        os.makedirs(self.config.directory, exist_ok=True)
        filename = f"{self.config.name} | {self._get_timestamp()}.log"
        path = os.path.join(self.config.directory, filename)

        handler = logging.FileHandler(path)
        handler.setFormatter(self.config.formatter())
        handler.setLevel(self.config.level)
        self._logger.addHandler(handler)


    # --------------------------------------------------
    # Context resolution
    # --------------------------------------------------
    @staticmethod
    @functools.lru_cache(maxsize=128)
    def _auto_context_cached() -> str:
        try:
            for frame_info in inspect.stack()[3:]:
                module = inspect.getmodule(frame_info.frame)
                if not module:
                    continue
                if module.__name__.startswith("logging"):
                    continue

                filename = os.path.basename(module.__file__) if module.__file__ else module.__name__
                function = frame_info.function
                lineno = frame_info.lineno

                self_obj = frame_info.frame.f_locals.get("self")
                if self_obj:
                    return f"{filename}:{lineno} {self_obj.__class__.__name__}.{function}()"

                return f"{filename}:{lineno} {function}()"

        except Exception:
            return "unknown.context"

    # --------------------------------------------------
    # Utils
    # --------------------------------------------------

    def _get_timestamp(
        self,
        format: Optional[str] = None
    ) -> str:
        if format:
            return datetime.now().strftime(format)
        return datetime.now().strftime(self.config.date)

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------
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


    @classmethod
    def configure(cls, config: LoggerConfig = None) -> None:
        """
        Set the logger configuration.

        Args:
            config: The logger configuration settings.

        Returns:
            None
        """
        if not config:
            config = LoggerConfig()

        if not cls._initialized:
            instance = cls._instance or cls()
            instance._initialize(config)


if __name__ == "__main__":
    def main():
        config = LoggerConfig(name="test", directory="testing")
        Logger.configure(config)
        logger_instance = Logger()
        logger_instance.bind("testing")
        logger = logger_instance.get_logger()
        logger.info("This is an info message.")
        logger.error("This is an error message.")

    main()