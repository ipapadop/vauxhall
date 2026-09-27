# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Shared configuration schemas for Vauxhall."""

import json
import os
from collections.abc import Mapping
from dataclasses import MISSING, Field, dataclass, field, fields
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


def _field_default(f: Field[Any]) -> Any:  # noqa: ANN401
    """Return a dataclass field's default, calling its factory if it has one.

    Args:
        f: The field to read a default from.

    Returns:
        The field's default value, or ``None`` if it has neither.
    """
    if f.default is not MISSING:
        return f.default
    if f.default_factory is not MISSING:
        return f.default_factory()
    return None


class ConfigurationError(ValueError):
    """Raised when an explicit configuration value is invalid."""

    @classmethod
    def invalid_value(
        cls, source: str, section: str, key: str, value: object, expected: str
    ) -> "ConfigurationError":
        """Create a source-aware invalid-value error.

        Args:
            source: Environment variable or file location the value came from.
            section: Configuration section holding the key.
            key: Key within the section.
            value: The rejected value.
            expected: Description of what the field accepts.

        Returns:
            The error, ready to raise.
        """
        return cls(
            f"Invalid configuration value from {source} for {section}.{key}: "
            f"{value!r}; expected {expected}"
        )


PASSWORD_ENV = "VAUXHALL_MQTT_PASSWORD"  # noqa: S105


@dataclass
class MQTTConfig:
    """MQTT client configuration.

    The password is not a field: it comes from ``VAUXHALL_MQTT_PASSWORD`` or
    ``password_file``, so it never reaches a config file, ``asdict``, or the
    settings dialog. Empty strings mean unset.
    """

    host: str = field(default="localhost", metadata={"non_empty": True})
    port: int = field(default=1883, metadata={"min": 1, "max": 65535})
    keepalive: int = field(default=60, metadata={"min": 0, "max": 65535})
    tls: bool = False
    ca_certs: str = field(default="", metadata={"readable_file": True})
    username: str = ""
    password_file: str = field(default="", metadata={"readable_file": True})
    certfile: str = field(default="", metadata={"readable_file": True})
    keyfile: str = field(default="", metadata={"readable_file": True})

    def validate(self) -> None:
        """Reject combinations of options that cannot work together.

        The loader calls this, not the constructor: the password check reads
        the environment, and default configurations are built without it.

        Raises:
            ConfigurationError: If a client certificate lacks its key or the
                reverse, a CA or client certificate is set without TLS, or a
                password is set without a username.
        """
        has_password = self.password_file or os.environ.get(PASSWORD_ENV)
        problems = [
            (
                self.certfile and not self.keyfile,
                "mqtt.keyfile is required when mqtt.certfile is set",
            ),
            (
                self.keyfile and not self.certfile,
                "mqtt.certfile is required when mqtt.keyfile is set",
            ),
            (
                self.ca_certs and not self.tls,
                "mqtt.ca_certs requires mqtt.tls to be true",
            ),
            (
                self.certfile and not self.tls,
                "mqtt.certfile requires mqtt.tls to be true",
            ),
            (
                has_password and not self.username,
                (
                    f"mqtt.username is required when {PASSWORD_ENV}"
                    " or mqtt.password_file is set"
                ),
            ),
        ]
        for failed, message in problems:
            if failed:
                raise ConfigurationError(message)

    def password(self) -> str | None:
        """Return the broker password.

        Returns:
            The value of ``VAUXHALL_MQTT_PASSWORD``, else the contents of
            ``password_file`` without its trailing newline, else ``None``.

        Raises:
            OSError: If ``password_file`` can no longer be read, or its
                content is not valid UTF-8.
        """
        if password := os.environ.get(PASSWORD_ENV):
            return password
        if self.password_file:
            try:
                content = Path(self.password_file).read_text(encoding="utf-8")
            except UnicodeDecodeError as error:
                message = f"{self.password_file} is not valid UTF-8"
                raise OSError(message) from error
            return content.removesuffix("\n").removesuffix("\r")
        return None


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
        raise ConfigurationError(message) from e
    except OSError as e:
        message = f"{resolved_path}: Could not read configuration: {e}"
        raise ConfigurationError(message) from e

    if not isinstance(data, dict):
        message = (
            f"{resolved_path}: top-level configuration must be an object, got {data!r}"
        )
        raise ConfigurationError(message)
    return data


def find_config_file(filename: str) -> Path | None:
    """Search for config file in CWD and then ~/.config/vauxhall/.

    Args:
        filename: Name of the configuration file to look for.

    Returns:
        The first path that exists, or ``None`` when neither directory has it.
    """
    for directory in (Path.cwd(), Path.home() / ".config" / "vauxhall"):
        config_path = directory / filename
        if config_path.exists():
            return config_path
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
        """Return the explicit value and its environment variable or file source.

        Args:
            env_var: Environment variable that overrides the file.
            section: Section in the JSON config.
            key: Key within the section.

        Returns:
            The value and the source describing it, or ``None`` when neither
            the environment nor the file sets the key.

        Raises:
            ConfigurationError: If the section is present but is not an object.
        """
        if env_var in os.environ:
            return os.environ[env_var], env_var

        self._ensure_json_loaded()
        assert self._json_data is not None
        section_data = self._json_data.get(section, {})
        if not isinstance(section_data, dict):
            source = str(self.config_path) if self.config_path else "configuration"
            message = f"{source}: {section} must be an object, got {section_data!r}"
            raise ConfigurationError(message)
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
        return self._resolve(env_var, section, key, default, {})

    def resolve_dataclass(self, cls: type[T], section: str, env_prefix: str) -> T:
        """Automatically resolve all fields for a dataclass.

        Args:
            cls: The dataclass type to instantiate.
            section: The section in the JSON config.
            env_prefix: The prefix for environment variables.

        Returns:
            T: An instance of the dataclass.
        """
        config = cls(
            **{
                f.name: self._resolve(
                    f"{env_prefix}_{f.name.upper()}",
                    section,
                    f.name,
                    _field_default(f),
                    f.metadata,
                )
                for f in fields(cls)  # pyright: ignore[reportArgumentType]
            }
        )
        if validate := getattr(config, "validate", None):
            validate()
        return config

    def _resolve(
        self,
        env_var: str,
        section: str,
        key: str,
        default: T,
        metadata: Mapping[str, Any],
    ) -> T:
        """Resolve one setting, then coerce and validate it against its field.

        Args:
            env_var: Environment variable that overrides the file.
            section: Section in the JSON config.
            key: Key within the section.
            default: Value used when neither source sets the key.
            metadata: Field metadata constraining the value.

        Returns:
            The resolved value, normalized and validated.

        Raises:
            ConfigurationError: If an explicit value has the wrong type or
                falls outside the field's metadata constraints.
        """
        source_value = self._value_source(env_var, section, key)
        if source_value is None:
            return default

        value, source = source_value
        original_value = value
        if source.startswith("VAUXHALL_"):
            value = self._cast_environment_value(value, source, section, key, default)
        elif type(value) is not type(default) or (
            isinstance(value, list) and not all(isinstance(item, str) for item in value)
        ):
            raise ConfigurationError.invalid_value(
                source, section, key, value, self._expected(metadata, default)
            )

        if metadata.get("normalize") == "upper":
            assert isinstance(value, str)
            value = value.upper()

        if metadata.get("non_empty") and not value:
            raise ConfigurationError.invalid_value(
                source, section, key, original_value, "a non-empty string"
            )

        if metadata.get("readable_file") and value:
            assert isinstance(value, str)
            path = Path(value)
            # Hooks run in each agent's workspace, so a relative path would
            # resolve differently from one run to the next.
            if not (path.is_absolute() and path.is_file() and os.access(path, os.R_OK)):
                raise ConfigurationError.invalid_value(
                    source,
                    section,
                    key,
                    original_value,
                    "the absolute path of a readable file",
                )

        minimum = metadata.get("min")
        maximum = metadata.get("max")
        choices = metadata.get("choices")
        if (
            (minimum is not None and value < minimum)
            or (maximum is not None and value > maximum)
            or (choices is not None and value not in choices)
        ):
            raise ConfigurationError.invalid_value(
                source, section, key, original_value, self._expected(metadata, default)
            )

        return value  # type: ignore[return-value]

    def _cast_environment_value(
        self, value: object, source: str, section: str, key: str, default: T
    ) -> T:
        """Strictly cast an environment string to a field's default type.

        Args:
            value: The environment variable's string value.
            source: Environment variable the value came from.
            section: Section in the JSON config.
            key: Key within the section.
            default: Field default whose type the value is cast to.

        Returns:
            The value cast to the default's type.

        Raises:
            ConfigurationError: If the string is not a valid boolean or integer.
        """
        assert isinstance(value, str)
        if isinstance(default, bool):
            normalized = value.lower()
            if normalized in ("true", "1", "yes"):
                return True  # type: ignore[return-value]
            if normalized in ("false", "0", "no"):
                return False  # type: ignore[return-value]
            raise ConfigurationError.invalid_value(
                source, section, key, value, "a boolean"
            )
        if isinstance(default, int):
            try:
                return int(value)  # type: ignore[return-value]
            except ValueError as error:
                raise ConfigurationError.invalid_value(
                    source, section, key, value, "an integer"
                ) from error
        if isinstance(default, list):
            raise ConfigurationError.invalid_value(
                source, section, key, value, "a value only settable via a config file"
            )
        return value  # type: ignore[return-value]

    def _expected(self, metadata: Mapping[str, Any], default: object) -> str:
        """Describe the type and field metadata accepted by a configuration value.

        Args:
            metadata: Field metadata constraining the value.
            default: Field default whose type is described.

        Returns:
            A human-readable description for error messages.
        """
        expected = (
            "a boolean"
            if isinstance(default, bool)
            else "an integer"
            if isinstance(default, int)
            else "a list of strings"
            if isinstance(default, list)
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
