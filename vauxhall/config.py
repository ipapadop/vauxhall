"""Configuration management for Vauxhall."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from vauxhall.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class MQTTConfig:
    """MQTT client configuration."""

    host: str = "localhost"
    port: int = 1883
    keepalive: int = 60


@dataclass
class DashboardConfig:
    """Dashboard UI configuration."""

    host: str = "127.0.0.1"
    port: int = 8080
    debug: bool = False
    window_title: str = "Vauxhall Agent Dashboard"
    width: int = 1000
    height: int = 800
    stale_threshold: int = 120  # seconds


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"


@dataclass
class Config:
    """Central configuration for Vauxhall.

    Loads configuration from vauxhall.yaml if it exists, otherwise uses defaults.
    """

    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "Config":
        """Load configuration from a YAML file.

        Args:
            config_path: Path to the configuration file. Defaults to vauxhall.yaml
                in the current working directory.

        Returns:
            Config: The loaded configuration object.
        """
        if config_path is None:
            config_path = Path("vauxhall.yaml")
        else:
            config_path = Path(config_path)

        config_data = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = yaml.safe_load(f) or {}
                logger.info("Loaded configuration from %s", config_path)
            except Exception as e:
                logger.error("Failed to load configuration from %s: %s", config_path, e)
        else:
            logger.debug("Configuration file %s not found, using defaults", config_path)

        # Handle empty sections safely
        mqtt_data = config_data.get("mqtt") or {}
        dashboard_data = config_data.get("dashboard") or {}
        logging_data = config_data.get("logging") or {}

        return cls(
            mqtt=MQTTConfig(**mqtt_data),
            dashboard=DashboardConfig(**dashboard_data),
            logging=LoggingConfig(**logging_data),
        )


# Global configuration instance
settings = Config.load()
