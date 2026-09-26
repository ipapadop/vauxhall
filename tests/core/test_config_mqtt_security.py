# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the MQTT authentication and TLS settings."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from vauxhall.core.config import (
    PASSWORD_ENV,
    ConfigResolver,
    ConfigurationError,
    MQTTConfig,
)


def load_mqtt(tmp_path: Path, mqtt: dict[str, object]) -> MQTTConfig:
    """Load the MQTT section of a config file written from ``mqtt``.

    Args:
        tmp_path: Directory to write the config file into.
        mqtt: The contents of the file's ``mqtt`` section.

    Returns:
        The loaded MQTT configuration.
    """
    path = tmp_path / "vauxhall_hooks.json"
    path.write_text(json.dumps({"mqtt": mqtt}), encoding="utf-8")
    return ConfigResolver("vauxhall_hooks.json", path).resolve_dataclass(
        MQTTConfig, "mqtt", "VAUXHALL_MQTT"
    )


@pytest.fixture
def secret_file(tmp_path: Path) -> Path:
    """Return a readable file to stand in for a certificate or password.

    Returns:
        The file's path.
    """
    path = tmp_path / "secret"
    path.write_text("hunter2\n", encoding="utf-8")
    return path


def test_defaults_are_unauthenticated_plaintext() -> None:
    """Without settings the client stays the documented local-development one."""
    config = MQTTConfig()

    assert not config.tls
    assert not config.username
    assert config.password() is None


def test_fields_load_from_file(tmp_path: Path, secret_file: Path) -> None:
    """Every auth and TLS field can come from the config file.

    Args:
        tmp_path: Pytest temporary directory.
        secret_file: A readable file for the path fields.
    """
    config = load_mqtt(
        tmp_path,
        {
            "tls": True,
            "ca_certs": str(secret_file),
            "username": "agent-host",
            "password_file": str(secret_file),
            "certfile": str(secret_file),
            "keyfile": str(secret_file),
        },
    )

    assert config.tls
    assert config.username == "agent-host"
    assert config.ca_certs == str(secret_file)


def test_environment_overrides_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An environment variable beats the file, as for every other field.

    Args:
        tmp_path: Pytest temporary directory.
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setenv("VAUXHALL_MQTT_TLS", "true")
    monkeypatch.setenv("VAUXHALL_MQTT_USERNAME", "from-env")

    config = load_mqtt(tmp_path, {"tls": False, "username": "from-file"})

    assert config.tls
    assert config.username == "from-env"


@pytest.mark.parametrize("field", ["ca_certs", "password_file", "certfile", "keyfile"])
def test_missing_file_names_its_source(
    tmp_path: Path, secret_file: Path, field: str
) -> None:
    """A path that is not a readable file is rejected at load time.

    Args:
        tmp_path: Pytest temporary directory.
        secret_file: A readable file for the fields not under test.
        field: The path field under test.
    """
    valid = str(secret_file)
    mqtt = {
        "tls": True,
        "username": "u",
        "ca_certs": valid,
        "password_file": valid,
        "certfile": valid,
        "keyfile": valid,
        field: str(tmp_path / "missing.pem"),
    }

    with pytest.raises(ConfigurationError, match=rf"vauxhall_hooks.json:mqtt.{field}"):
        load_mqtt(tmp_path, mqtt)


def test_directory_is_not_a_readable_file(tmp_path: Path) -> None:
    """A directory is not accepted where a file is expected.

    Args:
        tmp_path: Pytest temporary directory.
    """
    with pytest.raises(ConfigurationError, match="readable file"):
        load_mqtt(tmp_path, {"tls": True, "ca_certs": str(tmp_path)})


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"tls": True, "certfile": "c"}, "^mqtt.keyfile is required"),
        ({"tls": True, "keyfile": "k"}, "^mqtt.certfile is required"),
        ({"ca_certs": "ca"}, "^mqtt.ca_certs requires mqtt.tls"),
        ({"certfile": "c", "keyfile": "k"}, "^mqtt.certfile requires mqtt.tls"),
        ({"password_file": "p"}, "^mqtt.username is required"),
    ],
)
def test_incompatible_combinations_name_the_field_to_fix(
    kwargs: dict[str, object], message: str
) -> None:
    """Settings that cannot work together fail, naming the field to change first.

    Args:
        kwargs: The conflicting fields.
        message: Pattern the error must match.
    """
    with pytest.raises(ConfigurationError, match=message):
        MQTTConfig(**kwargs).validate()  # pyright: ignore[reportArgumentType]


def test_loader_rejects_incompatible_combinations(
    tmp_path: Path, secret_file: Path
) -> None:
    """Loading a configuration runs the same checks.

    Args:
        tmp_path: Pytest temporary directory.
        secret_file: A readable file for the CA path.
    """
    with pytest.raises(ConfigurationError, match=r"requires mqtt\.tls"):
        load_mqtt(tmp_path, {"ca_certs": str(secret_file)})


def test_environment_password_requires_username_when_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A password from the environment needs a username, checked at load time.

    Args:
        tmp_path: Pytest temporary directory.
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setenv(PASSWORD_ENV, "pw")

    with pytest.raises(ConfigurationError, match=r"mqtt\.username is required"):
        load_mqtt(tmp_path, {})

    assert load_mqtt(tmp_path, {"username": "u"}).password() == "pw"


def test_default_config_ignores_the_password_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Building a default configuration never fails because of the environment.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setenv(PASSWORD_ENV, "pw")

    assert MQTTConfig().username == ""


def test_relative_path_is_rejected_even_when_the_file_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hooks run in each workspace, so only absolute paths mean the same thing.

    Args:
        tmp_path: Pytest temporary directory.
        monkeypatch: Pytest monkeypatch fixture.
    """
    (tmp_path / "ca.pem").write_text("ca", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigurationError, match="absolute path of a readable file"):
        load_mqtt(tmp_path, {"tls": True, "ca_certs": "ca.pem"})


def test_password_file_loses_only_its_trailing_newline(tmp_path: Path) -> None:
    """The password is the file's content minus the line ending, nothing else.

    Args:
        tmp_path: Pytest temporary directory.
    """
    file = tmp_path / "pw"
    file.write_bytes(b" p w \r\n")

    assert MQTTConfig(username="u", password_file=str(file)).password() == " p w "


def test_environment_password_beats_password_file(
    monkeypatch: pytest.MonkeyPatch, secret_file: Path
) -> None:
    """The environment variable wins over ``password_file``.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        secret_file: A file holding a different password.
    """
    monkeypatch.setenv(PASSWORD_ENV, "from-env")

    config = MQTTConfig(username="u", password_file=str(secret_file))

    assert config.password() == "from-env"


def test_password_never_appears_in_field_views(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing that walks the fields or prints the config can leak the password.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setenv(PASSWORD_ENV, "s3cret")
    config = MQTTConfig(username="u")

    assert "s3cret" not in repr(config)
    assert "password" not in asdict(config)
