# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for loading hook configuration."""

import json
import os
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest

from vauxhall.core.config import MQTTConfig
from vauxhall.hooks.config import HookConfig


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
    assert f"Ignoring {workspace_file.resolve()}" in caplog.text


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
def test_hooks_without_a_workspace_file_do_not_warn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Only a workspace file that would have been read is worth a warning.

    Args:
        caplog: Pytest log capture fixture.
    """
    with caplog.at_level("WARNING"):
        HookConfig.load()

    assert caplog.records == []
