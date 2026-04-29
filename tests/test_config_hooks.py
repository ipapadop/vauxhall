# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for hook configuration."""

import json
from pathlib import Path

from vauxhall.hooks.config import HookConfig


def test_hook_config_loading(tmp_path: Path) -> None:
    """Test loading hook configuration from a JSON file."""
    config_file = tmp_path / "vauxhall_hooks.json"
    config_file.write_text(
        json.dumps({"mqtt": {"host": "remote-broker"}}), encoding="utf-8"
    )

    config = HookConfig.load(config_file)
    assert config.mqtt.host == "remote-broker"
    assert config.mqtt.port == 1883  # Default
