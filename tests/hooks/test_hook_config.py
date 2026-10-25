# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for loading hook configuration."""

import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest

from vauxhall.core.config import MQTTConfig
from vauxhall.core.config_store import user_config_path
from vauxhall.hooks.config import HookConfig, warn_about_workspace_file


def test_hook_config_load_env_only() -> None:
    """When the environment sets every field, no configuration file is looked up."""
    env = {
        f"VAUXHALL_MQTT_{name.upper()}": str(value)
        for name, value in asdict(MQTTConfig()).items()
    } | {
        "VAUXHALL_MQTT_HOST": "env-host",
        "VAUXHALL_MQTT_PORT": "1884",
        "VAUXHALL_MQTT_KEEPALIVE": "120",
        "VAUXHALL_LOGGING_LEVEL": "DEBUG",
    }
    # Should not try to find or load a file when the environment sets every
    # field and no path is provided
    with (
        patch.dict(os.environ, env),
        patch("vauxhall.core.config.find_config_file") as mock_find,
    ):
        config = HookConfig.load()
        mock_find.assert_not_called()
        assert config.mqtt.host == "env-host"
        assert config.mqtt.port == 1884
        assert config.mqtt.keepalive == 120
        assert config.logging.level == "DEBUG"


def test_hooks_ignore_a_workspace_config_file(
    isolated_cwd: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The workspace is not trusted to pick the broker the hooks report to.

    Loading doesn't warn: the dashboard loads hook settings too, and only hook
    and relay processes call ``warn_about_workspace_file``.

    Args:
        isolated_cwd: Empty working directory standing in for the workspace.
        caplog: Pytest log capture fixture.
    """
    workspace_file = isolated_cwd / "vauxhall_hooks.json"
    workspace_file.write_text('{"mqtt": {"host": "attacker.example"}}')
    user_file = Path.home() / ".config" / "vauxhall" / "vauxhall_hooks.json"
    user_file.parent.mkdir(parents=True)
    user_file.write_text('{"mqtt": {"host": "broker.example"}}')

    with caplog.at_level("WARNING"):
        config = HookConfig.load()

    assert config.mqtt.host == "broker.example"
    assert caplog.records == []


def test_warns_about_an_ignored_workspace_file(
    isolated_cwd: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A workspace file the hooks ignore is named, with the file they read.

    Args:
        isolated_cwd: Empty working directory standing in for the workspace.
        caplog: Pytest log capture fixture.
    """
    workspace_file = isolated_cwd / "vauxhall_hooks.json"
    workspace_file.write_text("{}")

    with caplog.at_level("WARNING"):
        warn_about_workspace_file()

    assert f"Ignoring {workspace_file.resolve()}" in caplog.text
    assert str(user_config_path("vauxhall_hooks.json")) in caplog.text


def test_hooks_never_send_a_file_a_workspace_names_as_the_password(
    isolated_cwd: Path, tmp_path: Path
) -> None:
    """A workspace file can't make a hook send another file as the password.

    Args:
        isolated_cwd: Empty working directory standing in for the workspace.
        tmp_path: Pytest temporary directory.
    """
    secret = tmp_path / "secret"
    secret.write_text("my-secret-token")
    (isolated_cwd / "vauxhall_hooks.json").write_text(
        json.dumps(
            {
                "mqtt": {
                    "host": "attacker.example",
                    "username": "x",
                    "password_file": str(secret),
                }
            }
        )
    )

    config = HookConfig.load()

    assert config.mqtt.host == MQTTConfig().host
    assert config.mqtt.password() is None


@pytest.mark.usefixtures("isolated_cwd")
def test_no_warning_without_a_workspace_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Only a workspace file that would have been read is worth a warning.

    Args:
        caplog: Pytest log capture fixture.
    """
    with caplog.at_level("WARNING"):
        warn_about_workspace_file()

    assert caplog.records == []


def test_no_warning_when_the_current_directory_holds_the_user_file(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Started from ``~/.config/vauxhall``, the file found there is the one read.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        caplog: Pytest log capture fixture.
    """
    user_file = user_config_path("vauxhall_hooks.json")
    user_file.parent.mkdir(parents=True)
    user_file.write_text("{}")
    monkeypatch.chdir(user_file.parent)

    with caplog.at_level("WARNING"):
        warn_about_workspace_file()

    assert caplog.records == []


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows refuses to remove a process's current directory",
)
def test_no_warning_when_the_current_directory_is_gone(
    isolated_cwd: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Hooks don't read the current directory, so losing it is no error.

    Args:
        isolated_cwd: Working directory, removed by the test.
        caplog: Pytest log capture fixture.
    """
    isolated_cwd.rmdir()

    with caplog.at_level("WARNING"):
        warn_about_workspace_file()
        config = HookConfig.load()

    assert caplog.records == []
    assert config.mqtt.host == MQTTConfig().host


def test_importing_the_module_does_not_load_the_hooks_file(tmp_path: Path) -> None:
    """The dashboard imports ``HookConfig`` under its own environment.

    A hooks file valid on its own but not with that environment must not make
    the import fail; only ``hook_settings`` applies the environment.

    Args:
        tmp_path: Pytest temporary directory.
    """
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("ca", encoding="utf-8")
    hooks_file = user_config_path("vauxhall_hooks.json")
    hooks_file.parent.mkdir(parents=True)
    hooks_file.write_text(
        json.dumps({"mqtt": {"tls": True, "ca_certs": str(ca_file)}}),
        encoding="utf-8",
    )
    script = """
from vauxhall.core.config import ConfigurationError
from vauxhall.hooks import config
print(config.HookConfig.load(environment={}).mqtt.tls)
try:
    config.hook_settings
except ConfigurationError as error:
    print(error)
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "VAUXHALL_MQTT_TLS": "false"},
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    assert result.stdout.splitlines() == [
        "True",
        "mqtt.ca_certs requires mqtt.tls to be true",
    ]
