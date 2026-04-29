# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Shared configuration schemas for Vauxhall."""

import json
from dataclasses import dataclass, field
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
