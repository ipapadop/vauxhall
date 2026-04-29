# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Configuration management for Vauxhall."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from vauxhall.core.logging import get_logger

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

    Loads configuration from vauxhall.json if it exists, otherwise uses defaults.
    """

    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "Config":
        """Load configuration from a JSON file.

        Args:
            config_path: Path to the configuration file. Defaults to vauxhall.json
                in the current working directory.

        Returns:
            Config: The loaded configuration object.
        """
        if config_path is None:
            config_path = Path("vauxhall.json")
        else:
            config_path = Path(config_path)

        config_data = {}
        if config_path.exists():
            try:
                with config_path.open(encoding="utf-8") as f:
                    config_data = json.load(f) or {}
                logger.info("Loaded configuration from %s", config_path)
            except Exception:
                logger.exception("Failed to load configuration from %s", config_path)
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

    def save(self, config_path: str | Path | None = None) -> None:
        """Save the current configuration to a JSON file.

        Args:
            config_path: Path to the configuration file. Defaults to vauxhall.json.
        """
        if config_path is None:
            config_path = Path("vauxhall.json")
        else:
            config_path = Path(config_path)

        try:
            with config_path.open("w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=4)
            logger.info("Saved configuration to %s", config_path)
        except Exception:
            logger.exception("Failed to save configuration to %s", config_path)


# Global configuration instance
settings = Config.load()
