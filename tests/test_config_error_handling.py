# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for configuration error handling."""

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from vauxhall.core.config import load_config_data


def test_load_config_data_malformed_json(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test loading configuration data from a malformed JSON file."""
    config_file = tmp_path / "malformed.json"
    with config_file.open("w") as f:
        f.write("{ invalid json }")

    with caplog.at_level(logging.ERROR):
        loaded_data = load_config_data(config_file)

    assert loaded_data == {}
    assert "is not valid JSON" in caplog.text


def test_load_config_data_os_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test loading configuration data when an OS error occurs."""
    config_file = tmp_path / "unreadable.json"
    config_file.touch()

    # Simulate OSError by mocking Path.open
    with (
        patch.object(Path, "open", side_effect=OSError("Permission denied")),
        caplog.at_level(logging.ERROR),
    ):
        loaded_data = load_config_data(config_file)

    assert loaded_data == {}
    assert "Could not read configuration file" in caplog.text
