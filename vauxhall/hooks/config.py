# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Configuration for Vauxhall hooks."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from vauxhall.core.config import (
    HOOKS_FILE,
    ConfigResolver,
    LoggingConfig,
    MQTTConfig,
)
from vauxhall.core.config_store import user_config_path
from vauxhall.core.logging import get_logger

logger = get_logger(__name__)


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
    # The dashboard saves this file, but hooks run in the agents' environments,
    # so the dashboard's VAUXHALL_* variables don't apply to it.
    SAVER_ENVIRONMENT_APPLIES: ClassVar[bool] = False

    @classmethod
    def load(
        cls,
        config_path: Path | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> "HookConfig":
        """Load hook configuration from environment or JSON file.

        Args:
            config_path: Path to the configuration file. If None, reads
                ``~/.config/vauxhall/vauxhall_hooks.json``, ignoring one in
                the current directory.
            environment: The environment variables that override the file,
                defaulting to the process environment.

        Returns:
            HookConfig: The loaded configuration.
        """
        resolver = ConfigResolver(
            HOOKS_FILE,
            config_path,
            search_current_directory=cls.SEARCHES_CURRENT_DIRECTORY,
            environment=environment,
        )
        return cls(
            mqtt=resolver.resolve_dataclass(MQTTConfig, "mqtt"),
            logging=resolver.resolve_dataclass(LoggingConfig, "logging"),
        )


def warn_about_workspace_file() -> None:
    """Log a warning when the current directory holds a hooks file hooks ignore.

    Hook processes call this; the dashboard loads hook settings too and has no
    use for the warning.
    """
    user_file = user_config_path(HOOKS_FILE)
    try:
        workspace_file = (Path.cwd() / HOOKS_FILE).resolve()
        ignored = workspace_file.exists() and workspace_file != user_file.resolve()
    except OSError:
        return
    if ignored:
        logger.warning("Ignoring %s: hooks read only %s", workspace_file, user_file)


def __getattr__(name: str) -> HookConfig:
    """Load ``hook_settings`` on first access, not on import.

    The dashboard imports this module for ``HookConfig`` and checks the hooks
    file without its own environment; loading at import would apply it.

    Args:
        name: The attribute being looked up.

    Returns:
        The hook configuration, loaded once from the process environment.

    Raises:
        AttributeError: If ``name`` is not ``hook_settings``.
    """
    if name != "hook_settings":
        message = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(message)
    settings = HookConfig.load()
    globals()["hook_settings"] = settings
    return settings
