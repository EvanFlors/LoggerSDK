# ---------------------------------------------------------------------
# Standard libraries
# ---------------------------------------------------------------------
import os
import sys
import uuid
import random
import logging

from contextvars import ContextVar
from datetime import datetime
from typing import Optional

# ---------------------------------------------------------------------
# Third-party libraries
# ---------------------------------------------------------------------
from colorlog import ColoredFormatter

# ---------------------------------------------------------------------
# Internal application imports
# ---------------------------------------------------------------------
from logger.config import LoggingSettings

trace_id_var = ContextVar("trace_id", default=None)
span_id_var = ContextVar("span_id", default=None)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def new_span_id() -> str:
    return uuid.uuid4().hex


# ==========================================================
# Formatter factory
# ==========================================================
class BaseFormatter(logging.Formatter):

    def __init__(self, logging_settings: Optional[LoggingSettings] = None):
        if logging_settings is None:
            logging_settings = LoggingSettings()
        self.logging_settings = logging_settings
        super().__init__()

    def formatter(self, date: str) -> ColoredFormatter:
        return ColoredFormatter(
            fmt="%(log_color)s" + self.logging_settings.base_format + "%(reset)s",
            datefmt=date,
            log_colors=self.logging_settings.log_colors,
        )


# ==========================================================
# Filters
# ==========================================================
class SamplingFilter(logging.Filter):

    def __init__(
        self,
        logging_settings: Optional[LoggingSettings] = None
    ):
        """
        Initialize the sampling filter.

        Args:
            logging_settings: Optional logging settings to customize the filter behavior.

        Returns:
            None
        """
        super().__init__()
        if logging_settings is None:
            logging_settings = LoggingSettings()
        self.logging_settings = logging_settings


    def filter(
        self,
        record: logging.LogRecord
    ) -> bool:
        """
        Determine whether a log record should be emitted based on the sampling settings.

        Args:
            record: The log record to evaluate.

        Returns:
            bool: True if the record should be emitted, False otherwise.
        """
        if record.levelno >= self.logging_settings.min_level:
            return True
        return random.random() < self.logging_settings.sample_rate


# ==========================================================
# Caller resolution
# ==========================================================
def resolve_caller() -> tuple[str, str]:
    """
    Finds the first frame that is not from:
    - Python logging internals
    - This logger module
    """
    try:
        frame = sys._getframe(3)

        while frame:
            filename = frame.f_code.co_filename.replace("\\", "/")
            func = frame.f_code.co_name

            # Skip stdlib logging internals
            if "/logging/" in filename or filename.endswith("logging/__init__.py"):
                frame = frame.f_back
                continue

            # Skip this module itself
            if "src/core/logger" in filename or "src/core/logging" in filename:
                frame = frame.f_back
                continue

            # Skip adapter method
            if func in ("process",):
                frame = frame.f_back
                continue

            return os.path.basename(filename), func

        return "unknown", "unknown"

    except Exception:
        return "unknown", "unknown"


# ==========================================================
# Context Logger
# ==========================================================
class ContextLogger(logging.LoggerAdapter):

    def process(
        self,
        msg: str,
        kwargs: dict
    ) -> tuple[str, dict]:
        """
        Process the log message and its context.

        Args:
            msg: The log message.
            kwargs: Additional keyword arguments.

        Returns:
            A tuple containing the processed message and updated keyword arguments.
        """

        call_extra = kwargs.get("extra")
        if not isinstance(call_extra, dict):
            call_extra = {}

        merged_extra = {**self.extra, **call_extra}
        merged_extra.setdefault("trace_id", "No trace")
        merged_extra.setdefault("span_id", "No span")

        bound_context = merged_extra.get("context")

        caller_file, caller_func = resolve_caller()
        logger_name = self.logger.name

        if bound_context:
            merged_extra["context"] = f"{logger_name} | {bound_context}"
        else:
            merged_extra["context"] = f"{logger_name} | {caller_file}:{caller_func}()"

        kwargs["extra"] = merged_extra
        return msg, kwargs


class Logger:

    _instance: Optional["Logger"] = None
    _initialized: bool = False

    def __new__(cls) -> "Logger":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


    def _initialize(
        self,
        config: LoggingSettings = None
    ) -> None:
        Logger._initialized = True

        self._config = config

        self._logger = logging.getLogger(self._config.name)
        self._logger.setLevel(self._config.level)
        self._logger.propagate = False

        if not self._logger.handlers:
            self._add_console_handler()
            if self._config.directory:
                self._add_file_handler()

        for module, level in self._config.module_levels.items():
            logging.getLogger(module).setLevel(level)

    # --------------------------------------------------
    # Handlers
    # --------------------------------------------------
    def _add_console_handler(self):
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.NOTSET)
        handler.setFormatter(BaseFormatter(self._config).formatter(
            self._config.date_format
        ))

        handler.addFilter(
            SamplingFilter(self._config)
        )

        self._logger.addHandler(handler)


    def _add_file_handler(self):
        try:
            os.makedirs(self._config.directory, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"Failed to create log directory: {e}")

        name = f"{self._config.name}_{self._get_timestamp()}"
        ext = "log"
        filename = f"{name}.{ext}"
        path = os.path.join(self._config.directory, filename)

        for handler in self._logger.handlers:
            if isinstance(handler, logging.FileHandler) and getattr(handler, 'baseFilename', None) == os.path.abspath(path):
                return  # Handler already exists

        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(BaseFormatter(self._config).formatter(self._config.date_format))
        handler.setLevel(logging.NOTSET)
        self._logger.addHandler(handler)

    # --------------------------------------------------
    # Context resolution
    # --------------------------------------------------
    @staticmethod
    def _auto_context() -> str:
        try:
            frame = sys._getframe(2)
            code = frame.f_code
            filename = os.path.basename(code.co_filename)
            function = code.co_name
            lineno = frame.f_lineno

            self_obj = frame.f_locals.get("self")
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
        return datetime.now().strftime(self._config.date_format)

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def get_logger(self) -> ContextLogger:
        if not hasattr(self, "_logger"):
            raise RuntimeError("Logger not initialized. Call Logger.configure() first.")

        return ContextLogger(self._logger, {})


    def bind(self, context: str) -> ContextLogger:
        if not hasattr(self, "_logger"):
            raise RuntimeError("Logger not initialized. Call Logger.configure() first.")

        return ContextLogger(self._logger, {"context": context})


    @classmethod
    def configure(
        cls,
        config: LoggingSettings = None
    ) -> None:
        if not config:
            config = LoggingSettings()

        if not cls._initialized:
            instance = cls._instance or cls()
            instance._initialize(config)

    # --------------------------------------------------
    # Tracing
    # --------------------------------------------------

    def set_trace(
        self,
        trace_id: str | None = None
    ):
        """
        Set the trace ID for the current log context.

        Args:
            trace_id (str | None): The trace ID to set.

        Returns:
            None
        """
        trace_id_var.set(trace_id or new_trace_id())


    def set_span(
        self,
        span_id: str | None = None
    ):
        """
        Set the span ID for the current log context.

        Args:
            span_id (str | None): The span ID to set.

        Returns:
            None
        """
        span_id_var.set(span_id or new_span_id())


if __name__ == "__main__":
    def main():
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

        logger = logger_instance.bind("testing")

        logger.info("This is an info message.")
        logger.error("This is an error message.")

        logger = logger_instance.bind("additional_context")

        logger.info("This is an info message from additional context.")
        logger.error("This is an error message from additional context.")

    main()