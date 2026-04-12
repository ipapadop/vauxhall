"""Configuration management for Vauxhall."""

import logging
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
    base_topic: str = "vauxhall"


@dataclass
class DashboardConfig:
    """Dashboard UI configuration."""

    host: str = "127.0.0.1"
    port: int = 8080
    debug: bool = False


@dataclass
class Config:
    """Central configuration for Vauxhall.

    Loads configuration from vauxhall.yaml if it exists, otherwise uses defaults.
    """

    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)

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

        mqtt_data = config_data.get("mqtt", {})
        dashboard_data = config_data.get("dashboard", {})

        return cls(
            mqtt=MQTTConfig(**mqtt_data),
            dashboard=DashboardConfig(**dashboard_data),
        )


# Global configuration instance
settings = Config.load()
