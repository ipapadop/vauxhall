# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Shared configuration schemas for Vauxhall."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from vauxhall.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class MQTTConfig:
    """MQTT client configuration."""

    host: str = "localhost"
    port: int = 1883
    keepalive: int = 60


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"


def load_config_data(config_path: Path) -> dict[str, Any]:
    """Load configuration data from a JSON file.

    Args:
        config_path: Path to the configuration file.

    Returns:
        dict[str, Any]: The configuration data, or an empty dict if the file
            does not exist or is invalid.
    """
    if config_path.exists():
        try:
            with config_path.open(encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            logger.exception("Failed to load configuration from %s", config_path)
    return {}


def find_config_file(filename: str) -> Path | None:
    """Search for config file in CWD and then ~/.config/vauxhall/."""
    cwd_path = Path.cwd() / filename
    if cwd_path.exists():
        return cwd_path

    user_config = Path.home() / ".config" / "vauxhall" / filename
    if user_config.exists():
        return user_config

    return None


def get_env(env_var: str, default: T) -> T:
    """Get environment variable with type-safe fallback to default."""
    value = os.environ.get(env_var)
    if value is None:
        return default

    # Simple type conversion based on default type
    if isinstance(default, bool):
        return value.lower() in ("true", "1", "yes")
    if isinstance(default, int):
        try:
            return int(value)
        except ValueError:
            return default
    return value
