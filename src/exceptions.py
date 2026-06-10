class LoggerError(Exception):
    """Base exception for logger errors."""

class LoggerConfigError(LoggerError):
    """Exception raised for errors in the logger configuration."""

class LoggerShutdownError(LoggerError):
    """Exception raised for errors during logger shutdown."""

class HandlerInitError(LoggerError):
    """Exception raised for errors during handler initialization."""

class AMQPConnectError(LoggerError):
    """Exception raised for errors during AMQP connection."""