# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the Codex-specific behavior of the Vauxhall hook installer."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from vauxhall.hooks import installation
from vauxhall.hooks.codex import install as installer


@pytest.mark.parametrize(
    ("existing_config", "description"),
    [
        (None, "Vauxhall telemetry hooks for Codex."),
        ({"description": "Project hooks"}, "Project hooks"),
    ],
)
def test_install_describes_hooks_file_without_replacing_description(
    tmp_path: Path, existing_config: dict | None, description: str
) -> None:
    """Codex hooks files get a description unless they already have one."""
    hooks_file = tmp_path / installer.SETTINGS_PATH
    if existing_config is not None:
        hooks_file.parent.mkdir()
        hooks_file.write_text(json.dumps(existing_config))

    with (
        patch.object(Path, "cwd", return_value=tmp_path),
        patch.object(installation, "setup_venv", return_value=Path("/venv/bin/python")),
    ):
        installer.install()

    assert json.loads(hooks_file.read_text())["description"] == description
