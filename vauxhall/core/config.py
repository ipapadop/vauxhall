# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Shared configuration schemas for Vauxhall."""

import json
import os
from collections.abc import Mapping
from dataclasses import MISSING, dataclass, field, fields
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


class ConfigurationError(ValueError):
    """Raised when an explicit configuration value is invalid."""

    @classmethod
    def from_message(cls, message: str) -> "ConfigurationError":
        """Create an error from a fully formatted configuration message."""
        return cls(message)

    @classmethod
    def invalid_value(
        cls, source: str, section: str, key: str, value: object, expected: str
    ) -> "ConfigurationError":
        """Create a source-aware invalid-value error."""
        return cls(
            f"Invalid configuration value from {source} for {section}.{key}: "
            f"{value!r}; expected {expected}"
        )


@dataclass
class MQTTConfig:
    """MQTT client configuration."""

    host: str = field(default="localhost", metadata={"non_empty": True})
    port: int = field(default=1883, metadata={"min": 1, "max": 65535})
    keepalive: int = field(default=60, metadata={"min": 0, "max": 65535})


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = field(
        default="INFO",
        metadata={
            "choices": {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"},
            "normalize": "upper",
        },
    )


def load_config_data(config_path: Path) -> dict[str, Any]:
    """Load configuration data from a JSON file.

    Args:
        config_path: Path to the configuration file.

    Returns:
        dict[str, Any]: The configuration data, or an empty dict if the file
            does not exist.

    Raises:
        ConfigurationError: If an existing file cannot be read, parsed, or
            does not contain an object at the top level.
    """
    if not config_path.exists():
        return {}

    resolved_path = config_path.resolve()
    try:
        with config_path.open(encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        message = f"{resolved_path}: is not valid JSON: {e}"
        raise ConfigurationError.from_message(message) from e
    except OSError as e:
        message = f"{resolved_path}: Could not read configuration: {e}"
        raise ConfigurationError.from_message(message) from e

    if not isinstance(data, dict):
        message = (
            f"{resolved_path}: top-level configuration must be an object, got {data!r}"
        )
        raise ConfigurationError.from_message(message)
    return data


def find_config_file(filename: str) -> Path | None:
    """Search for config file in CWD and then ~/.config/vauxhall/."""
    cwd_path = Path.cwd() / filename
    if cwd_path.exists():
        return cwd_path

    user_config = Path.home() / ".config" / "vauxhall" / filename
    if user_config.exists():
        return user_config

    return None


class ConfigResolver:
    """Tiered configuration resolver with lazy JSON loading."""

    def __init__(
        self, default_filename: str, override_path: Path | None = None
    ) -> None:
        """Initialize the resolver.

        Args:
            default_filename: The name of the config file to search for.
            override_path: Optional explicit path to a config file.
        """
        self.default_filename = default_filename
        self.override_path = override_path
        self._json_data: dict[str, Any] | None = None
        self.config_path: Path | None = None

    def _ensure_json_loaded(self) -> None:
        """Lazily load JSON data if not already loaded."""
        if self._json_data is None:
            config_path = self.override_path or find_config_file(self.default_filename)
            if config_path is None:
                self._json_data = {}
                return

            self.config_path = config_path.resolve()
            self._json_data = load_config_data(self.config_path)

    def _value_source(
        self, env_var: str, section: str, key: str
    ) -> tuple[object, str] | None:
        """Return the explicit value and its environment variable or file source."""
        if env_var in os.environ:
            return os.environ[env_var], env_var

        self._ensure_json_loaded()
        assert self._json_data is not None
        section_data = self._json_data.get(section, {})
        if not isinstance(section_data, dict):
            source = str(self.config_path) if self.config_path else "configuration"
            message = f"{source}: {section} must be an object, got {section_data!r}"
            raise ConfigurationError.from_message(message)
        if key in section_data:
            assert self.config_path is not None
            return section_data[key], f"{self.config_path}:{section}.{key}"
        return None

    def get(self, env_var: str, section: str, key: str, default: T) -> T:
        """Resolve setting: Env -> JSON -> Default.

        Args:
            env_var: Environment variable name.
            section: Section in JSON config.
            key: Key within the section in JSON config.
            default: Default value if not found elsewhere.

        Returns:
            T: The resolved value.
        """
        source_value = self._value_source(env_var, section, key)
        if source_value is None:
            return default

        value, source = source_value
        return self._resolve_value(value, source, section, key, default, {})

    def resolve_dataclass(self, cls: type[T], section: str, env_prefix: str) -> T:
        """Automatically resolve all fields for a dataclass.

        Args:
            cls: The dataclass type to instantiate.
            section: The section in the JSON config.
            env_prefix: The prefix for environment variables.

        Returns:
            T: An instance of the dataclass.
        """
        resolved_fields: dict[str, Any] = {}
        for f in fields(cls):
            default = f.default if f.default is not MISSING else None
            env_var = f"{env_prefix}_{f.name.upper()}"

            source_value = self._value_source(env_var, section, f.name)
            if source_value is None:
                resolved_fields[f.name] = default
                continue

            value, source = source_value
            resolved_fields[f.name] = self._resolve_value(
                value, source, section, f.name, default, f.metadata
            )

        return cls(**resolved_fields)

    def _resolve_value(  # noqa: PLR0913, PLR0917
        self,
        value: object,
        source: str,
        section: str,
        key: str,
        default: T,
        metadata: Mapping[str, object],
    ) -> T:
        """Coerce and validate a configured value against its dataclass field."""
        original_value = value
        if source.startswith("VAUXHALL_"):
            value = self._cast_environment_value(value, source, section, key, default)
        elif type(value) is not type(default):
            self._raise_invalid(
                source, section, key, value, self._expected(metadata, default)
            )

        if metadata.get("normalize") == "upper":
            assert isinstance(value, str)
            value = value.upper()

        if metadata.get("non_empty") and not value:
            self._raise_invalid(
                source, section, key, original_value, "a non-empty string"
            )

        minimum = metadata.get("min")
        maximum = metadata.get("max")
        if minimum is not None and value < minimum:
            self._raise_invalid(
                source, section, key, original_value, self._expected(metadata, default)
            )
        if maximum is not None and value > maximum:
            self._raise_invalid(
                source, section, key, original_value, self._expected(metadata, default)
            )

        choices = metadata.get("choices")
        if choices is not None and value not in choices:
            self._raise_invalid(
                source, section, key, original_value, self._expected(metadata, default)
            )

        return value  # type: ignore[return-value]

    def _cast_environment_value(
        self, value: object, source: str, section: str, key: str, default: T
    ) -> T:
        """Strictly cast an environment string to a field's default type."""
        assert isinstance(value, str)
        if isinstance(default, bool):
            normalized = value.lower()
            if normalized in ("true", "1", "yes"):
                return True  # type: ignore[return-value]
            if normalized in ("false", "0", "no"):
                return False  # type: ignore[return-value]
            self._raise_invalid(source, section, key, value, "a boolean")
        if isinstance(default, int):
            try:
                return int(value)
            except ValueError:
                self._raise_invalid(source, section, key, value, "an integer")
        return value  # type: ignore[return-value]

    def _expected(self, metadata: Mapping[str, object], default: object) -> str:
        """Describe the type and field metadata accepted by a configuration value."""
        expected = (
            "a boolean"
            if isinstance(default, bool)
            else "an integer"
            if isinstance(default, int)
            else "a string"
        )
        if metadata.get("non_empty"):
            expected = "a non-empty string"
        if metadata.get("min") is not None and metadata.get("max") is not None:
            expected = f"{expected} in range {metadata['min']}..{metadata['max']}"
        if metadata.get("choices") is not None:
            choices = ", ".join(sorted(metadata["choices"]))
            expected = f"{expected} one of {choices}"
        return expected

    def _raise_invalid(
        self, source: str, section: str, key: str, value: object, expected: str
    ) -> None:
        """Raise a source-aware error for one invalid explicit configuration value."""
        raise ConfigurationError.invalid_value(source, section, key, value, expected)
