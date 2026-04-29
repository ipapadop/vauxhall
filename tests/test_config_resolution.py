# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for configuration resolution."""

from pathlib import Path
from unittest.mock import patch

from vauxhall.core.config import find_config_file, get_env


def test_get_env_types() -> None:
    """Test environment variable type conversion in get_env()."""
    with patch.dict("os.environ", {"INT_VAR": "123", "BOOL_VAR": "true"}):
        assert get_env("INT_VAR", 0) == 123
        assert get_env("BOOL_VAR", False) is True  # noqa: FBT003
        assert get_env("NONEXISTENT", "default") == "default"


def test_find_config_file_cwd(tmp_path: Path) -> None:
    """Test finding a configuration file in the current directory."""
    with patch("vauxhall.core.config.Path.cwd", return_value=tmp_path):
        config_file = tmp_path / "test.json"
        config_file.touch()
        assert find_config_file("test.json") == config_file
