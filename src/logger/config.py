# ---------------------------------------------------------------------
# Standard libraries
# ---------------------------------------------------------------------
import logging

# ---------------------------------------------------------------------
# Third-party libraries
# ---------------------------------------------------------------------
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="_",
        env_nested_max_split=2,
        env_prefix="LOGGING_",
        extra="ignore",
    )

    directory: str = "logs"
    name: str = "app"
    level: str = "INFO"

    module_levels: dict[str, str] = {
        "src": "WARNING",
        "tests": "DEBUG",
    }

    min_level: int = logging.WARNING
    sample_rate: float = 1.0
    deterministic: bool = False

    date_format: str = "%Y-%m-%d_%H:%M:%S"

    base_format: str = "[%(asctime)s] [%(levelname)s] [%(context)s] [trace=%(trace_id)s span=%(span_id)s] - %(message)s"

    log_colors: dict[str, str] = {
        "DEBUG": "white",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold_red",
    }