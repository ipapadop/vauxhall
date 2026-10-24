# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Configuration for Vauxhall hooks."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from vauxhall.core.config import (
    ConfigResolver,
    LoggingConfig,
    MQTTConfig,
)
from vauxhall.core.config_store import user_config_path
from vauxhall.core.logging import get_logger

logger = get_logger(__name__)

HOOKS_FILE = "vauxhall_hooks.json"


@dataclass
class HookConfig:
    """Configuration for Vauxhall hooks.

    Attributes:
        mqtt: MQTT client configuration.
        logging: Logging configuration.
    """

    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Hooks run in the agent's workspace, which a cloned repository controls:
    # a hooks file there could send telemetry, and the MQTT password, to any
    # broker.
    SEARCHES_CURRENT_DIRECTORY: ClassVar[bool] = False

    @classmethod
    def load(cls, config_path: Path | None = None) -> "HookConfig":
        """Load hook configuration from environment or JSON file.

        Args:
            config_path: Path to the configuration file. If None, reads
                ``~/.config/vauxhall/vauxhall_hooks.json``, ignoring one in
                the current directory.

        Returns:
            HookConfig: The loaded configuration.
        """
        workspace_file = Path.cwd() / HOOKS_FILE
        if config_path is None and workspace_file.exists():
            logger.warning(
                "Ignoring %s: hooks read only %s",
                workspace_file.resolve(),
                user_config_path(HOOKS_FILE),
            )
        resolver = ConfigResolver(
            HOOKS_FILE,
            config_path,
            search_current_directory=cls.SEARCHES_CURRENT_DIRECTORY,
        )
        return cls(
            mqtt=resolver.resolve_dataclass(MQTTConfig, "mqtt"),
            logging=resolver.resolve_dataclass(LoggingConfig, "logging"),
        )


hook_settings = HookConfig.load()
