# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Configuration for Vauxhall hooks."""

from dataclasses import dataclass, field
from pathlib import Path

from vauxhall.core.config import (
    ConfigResolver,
    LoggingConfig,
    MQTTConfig,
)
from vauxhall.core.logging import setup_logging


@dataclass
class HookConfig:
    """Configuration for Vauxhall hooks.

    Attributes:
        mqtt: MQTT client configuration.
        logging: Logging configuration.
    """

    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def load(cls, config_path: Path | None = None) -> "HookConfig":
        """Load hook configuration from environment or JSON file.

        Args:
            config_path: Path to the configuration file. If None, searches
                for "vauxhall_hooks.json" in standard paths.

        Returns:
            HookConfig: The loaded configuration.
        """
        resolver = ConfigResolver("vauxhall_hooks.json", config_path)
        return cls(
            mqtt=MQTTConfig(
                host=resolver.get("VAUXHALL_MQTT_HOST", "mqtt", "host", "localhost"),
                port=resolver.get("VAUXHALL_MQTT_PORT", "mqtt", "port", 1883),
                keepalive=resolver.get(
                    "VAUXHALL_MQTT_KEEPALIVE", "mqtt", "keepalive", 60
                ),
            ),
            logging=LoggingConfig(
                level=resolver.get("VAUXHALL_LOGGING_LEVEL", "logging", "level", "INFO")
            ),
        )


hook_settings = HookConfig.load()
setup_logging(level=hook_settings.logging.level)
