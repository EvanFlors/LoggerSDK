# ---------------------------------------------------------------------
# Standard library
# ---------------------------------------------------------------------
import logging
from dataclasses import dataclass, field


@dataclass
class LoggerConfig:
    directory: str = "logs"
    name: str = "app"
    json_logs: bool = False

    module_levels: dict[str, int] = field(default_factory=dict)
    sample_rate: float = 1.0
    deterministic: bool = False

    level: int = logging.INFO
    date: str = "%d-%m-%y_%H:%M:%S"