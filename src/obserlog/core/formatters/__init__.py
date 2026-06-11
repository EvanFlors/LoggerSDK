"""Formatters: structured JSON for sinks, colored for the console."""
from .colored_formatter import ConsoleFormatter
from .json_formatter import JSONFormatter

__all__ = ["ConsoleFormatter", "JSONFormatter"]
