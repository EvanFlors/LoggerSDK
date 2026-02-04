# ---------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------
import os
import sys
import logging
from datetime import datetime
from typing import Optional

# ---------------------------------------------------------------------
# Internal application imports
# ---------------------------------------------------------------------
from src.config import LoggerConfig
from src.core.formatters import JSONFormatter, BaseFormatter, ExtrasColoredFormatter
from src.core.filters import SamplingFilter, DeterministicSamplingFilter

from src.core.tracer import (
    trace_id_var,
    span_id_var,
    new_trace_id,
    new_span_id
)

class ContextLogger(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: dict):
        extra = kwargs.setdefault("extra", {})

        extra.setdefault("trace_id", trace_id_var.get())
        extra.setdefault("span_id", span_id_var.get())

        bound_context = self.extra.get("context")

        try:
            frame = sys._getframe(1)

            while frame:
                filename = frame.f_code.co_filename.replace("\\", "/")
                func = frame.f_code.co_name

                if (
                    "/logging/" in filename
                    or filename.endswith("logging/__init__.py")
                    or "src/core/logger" in filename
                    or func in ("process",)
                ):
                    frame = frame.f_back
                    continue

                caller_file = os.path.basename(filename)
                caller_func = func
                break

            else:
                caller_file = "unknown"
                caller_func = "unknown"

        except Exception:
            caller_file = "unknown"
            caller_func = "unknown"

        logger_name = self.logger.name

        if bound_context:
            extra["context"] = f"{logger_name} | {bound_context}"
        else:
            extra["context"] = f"{logger_name} | {caller_file}:{caller_func}()"

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

        for module, level in config.module_levels.items():
            logging.getLogger(module).setLevel(level)

    # --------------------------------------------------
    # Handlers
    # --------------------------------------------------
    def _add_console_handler(self):
        """
        Add a console handler to the logger.
        """
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.NOTSET)
        handler.setFormatter(BaseFormatter().formatter(
            self.config.date
        ))

        if getattr(self.config, 'deterministic', False):
            handler.addFilter(
                DeterministicSamplingFilter(
                    rate=self.config.sample_rate,
                    min_level=logging.WARNING,
                )
            )
        else:
            handler.addFilter(
                SamplingFilter(
                    rate=self.config.sample_rate,
                    min_level=logging.WARNING,
                )
            )

        self._logger.addHandler(handler)


    def _add_file_handler(self):
        """
        Add a file handler to the logger.
        """

        try:
            os.makedirs(self.config.directory, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"Failed to create log directory: {e}")

        name = f"{self.config.name}_{self._get_timestamp()}"
        ext = "json" if self.config.json_logs else "log"
        filename = f"{name}.{ext}"
        path = os.path.join(self.config.directory, filename)

        for handler in self._logger.handlers:
            if isinstance(handler, logging.FileHandler) and getattr(handler, 'baseFilename', None) == os.path.abspath(path):
                return  # Handler already exists

        handler = logging.FileHandler(path, encoding="utf-8")
        if self.config.json_logs:
            handler.setFormatter(JSONFormatter())
        else:
            handler.setFormatter(BaseFormatter())

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
        if not self._logger:
            raise RuntimeError("Logger not initialized. Call Logger.configure() first.")

        return ContextLogger(self._logger, {})


    def bind(self, context: str) -> ContextLogger:
        """
        Bind a fixed context to the logger.

        Args:
            context: The context information.

        Returns:
            ContextLogger: Logger adapter instance.
        """
        if not hasattr(self, "_logger"):
            raise RuntimeError("Logger not initialized. Call Logger.configure() first.")

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

    # --------------------------------------------------
    # Tracing
    # --------------------------------------------------

    def set_trace(self, trace_id: str | None = None):
        trace_id_var.set(trace_id or new_trace_id())


    def set_span(self, span_id: str | None = None):
        span_id_var.set(span_id or new_span_id())


if __name__ == "__main__":
    def main():
        Logger.configure(
            LoggerConfig(
                level=logging.INFO,
                name="test",
                directory="testing",
                module_levels={
                    "test": logging.DEBUG,
                },
                deterministic=True,
            )
        )
        logger_instance = Logger()
        logger = logger_instance.bind("testing")
        logger.info("This is an info message.")
        logger.error("This is an error message.")

    main()