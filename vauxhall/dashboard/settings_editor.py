# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Describe dashboard settings for the settings editor."""

import re
from dataclasses import asdict, fields
from typing import Any

from vauxhall.core.config import ConfigurationError
from vauxhall.core.config_store import field_sources, user_config_path
from vauxhall.dashboard.config import DashboardConfig

DASHBOARD_FILE = "vauxhall_dashboard.json"
HOOKS_FILE = "vauxhall_hooks.json"

# When a saved change takes effect. Fields that are not listed need a restart.
APPLY_MODES = {
    "mqtt.host": "reconnect",
    "mqtt.port": "reconnect",
    "mqtt.keepalive": "reconnect",
    "logging.level": "live",
    "dashboard.stale_threshold": "live",
    "dashboard.max_active_agents": "live",
    "dashboard.max_payload_bytes": "live",
}

_FIELD_PATTERN = re.compile(r"\b(mqtt|logging|dashboard)\.([a-z_]+)\b")


def apply_mode(key: str) -> str:
    """Return when a change to the "section.key" field takes effect."""
    return APPLY_MODES.get(key, "restart")


def hook_config_type() -> type[Any]:
    """Import the hook configuration type on first use.

    Importing ``vauxhall.hooks.config`` loads the hooks configuration and raises
    ``ConfigurationError`` if that file is malformed. Importing it lazily keeps
    a broken hooks file from stopping the dashboard.
    """
    from vauxhall.hooks.config import HookConfig  # noqa: PLC0415

    return HookConfig


def _field_type(default: object) -> str:
    """Return the settings editor input type for a field's default value."""
    if isinstance(default, bool):
        return "boolean"
    if isinstance(default, int):
        return "integer"
    return "string"


def describe_settings(config: DashboardConfig) -> dict[str, Any]:
    """Describe every dashboard setting for the settings editor.

    Args:
        config: The running dashboard configuration.

    Returns:
        dict[str, Any]: The fields with their values, constraints, sources, and
            when changes apply; the paths settings are saved to; and the error
            that prevents updating the hooks file, if any.

    Raises:
        ConfigurationError: If the dashboard configuration file is malformed.
    """
    sources = field_sources(DASHBOARD_FILE, DashboardConfig)
    try:
        field_sources(HOOKS_FILE, hook_config_type())
    except ConfigurationError as error:
        hooks_error = str(error)
    else:
        hooks_error = None

    described = []
    for section in fields(config):
        section_config = getattr(config, section.name)
        for field in fields(section_config):
            key = f"{section.name}.{field.name}"
            source = sources[key]
            choices = field.metadata.get("choices")
            described.append(
                {
                    "key": key,
                    "section": section.name,
                    "name": field.name,
                    "value": getattr(section_config, field.name),
                    "default": field.default,
                    "type": _field_type(field.default),
                    "min": field.metadata.get("min"),
                    "max": field.metadata.get("max"),
                    "choices": sorted(choices) if choices else None,
                    "required": bool(field.metadata.get("non_empty")),
                    "source": source.kind,
                    "location": source.location,
                    "editable": source.editable,
                    "apply": apply_mode(key),
                }
            )

    return {
        "fields": described,
        "paths": {
            "dashboard": str(user_config_path(DASHBOARD_FILE)),
            "hooks": str(user_config_path(HOOKS_FILE)),
        },
        "hooks_error": hooks_error,
    }


def changed_fields(old: DashboardConfig, new: DashboardConfig) -> list[str]:
    """Return the "section.key" names of fields whose values differ."""
    old_values = asdict(old)
    return [
        f"{section}.{key}"
        for section, values in asdict(new).items()
        for key, value in values.items()
        if old_values[section][key] != value
    ]


def error_field(message: str) -> str | None:
    """Return the dashboard field a configuration error message names, if any."""
    known = {
        f"{section}.{key}"
        for section, values in asdict(DashboardConfig()).items()
        for key in values
    }
    for match in _FIELD_PATTERN.finditer(message):
        key = f"{match[1]}.{match[2]}"
        if key in known:
            return key
    return None
