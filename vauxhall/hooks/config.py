# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Configuration for Vauxhall hooks."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from vauxhall.core.config import (
    LoggingConfig,
    MQTTConfig,
    find_config_file,
    get_env,
    load_config_data,
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
        # 1. Check for Env-Only Optimization
        env_host = os.environ.get("VAUXHALL_MQTT_HOST")
        if env_host and config_path is None:
            # Bypass file loading if critical env var is set
            return cls(
                mqtt=MQTTConfig(
                    host=env_host,
                    port=get_env("VAUXHALL_MQTT_PORT", 1883),
                    keepalive=get_env("VAUXHALL_MQTT_KEEPALIVE", 60),
                ),
                logging=LoggingConfig(level=get_env("VAUXHALL_LOGGING_LEVEL", "INFO")),
            )

        # 2. Regular resolution
        if config_path is None:
            config_path = find_config_file("vauxhall_hooks.json")

        data = load_config_data(config_path) if config_path else {}

        return cls(
            mqtt=MQTTConfig(
                host=get_env(
                    "VAUXHALL_MQTT_HOST", data.get("mqtt", {}).get("host", "localhost")
                ),
                port=get_env(
                    "VAUXHALL_MQTT_PORT", data.get("mqtt", {}).get("port", 1883)
                ),
                keepalive=get_env(
                    "VAUXHALL_MQTT_KEEPALIVE",
                    data.get("mqtt", {}).get("keepalive", 60),
                ),
            ),
            logging=LoggingConfig(
                level=get_env(
                    "VAUXHALL_LOGGING_LEVEL",
                    data.get("logging", {}).get("level", "INFO"),
                )
            ),
        )


hook_settings = HookConfig.load()
