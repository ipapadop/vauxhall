# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Configuration for Vauxhall hooks."""

from dataclasses import dataclass, field
from pathlib import Path

from vauxhall.core.config import (
    ConfigResolver,
    LoggingConfig,
    MQTTConfig,
)


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
            mqtt=resolver.resolve_dataclass(MQTTConfig, "mqtt", "VAUXHALL_MQTT"),
            logging=resolver.resolve_dataclass(
                LoggingConfig, "logging", "VAUXHALL_LOGGING"
            ),
        )


hook_settings = HookConfig.load()
