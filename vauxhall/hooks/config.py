# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Configuration for Vauxhall hooks."""

from dataclasses import dataclass, field
from pathlib import Path

from vauxhall.core.config import LoggingConfig, MQTTConfig, load_config_data


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
        """Load hook configuration from a JSON file.

        Args:
            config_path: Path to the configuration file. Defaults to
                "vauxhall_hooks.json" in the current directory.

        Returns:
            HookConfig: The loaded configuration.
        """
        if config_path is None:
            config_path = Path("vauxhall_hooks.json")

        data = load_config_data(config_path)
        return cls(
            mqtt=MQTTConfig(**data.get("mqtt", {})),
            logging=LoggingConfig(**data.get("logging", {})),
        )


hook_settings = HookConfig.load()
