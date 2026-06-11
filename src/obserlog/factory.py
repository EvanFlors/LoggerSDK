"""Backwards-compatibility shim. The factory now lives in `factory/`."""
from .factory.logger_factory import LoggerFactory

__all__ = ["LoggerFactory"]
