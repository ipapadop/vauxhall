# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for configuration error handling."""

from pathlib import Path
from unittest.mock import patch

import pytest

from vauxhall.core.config import ConfigurationError, load_config_data


def test_load_config_data_malformed_json(tmp_path: Path) -> None:
    """Malformed JSON raises a configuration error instead of using defaults."""
    config_file = tmp_path / "malformed.json"
    with config_file.open("w") as f:
        f.write("{ invalid json }")

    with pytest.raises(ConfigurationError, match="is not valid JSON"):
        load_config_data(config_file)


def test_load_config_data_os_error(tmp_path: Path) -> None:
    """Unreadable explicit files raise a source-aware configuration error."""
    config_file = tmp_path / "unreadable.json"
    config_file.touch()

    # Simulate OSError by mocking Path.open
    with (
        patch.object(Path, "open", side_effect=OSError("Permission denied")),
        pytest.raises(ConfigurationError, match="Could not read configuration"),
    ):
        load_config_data(config_file)
