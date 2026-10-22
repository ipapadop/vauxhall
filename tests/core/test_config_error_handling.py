# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for configuration error handling."""

from pathlib import Path
from unittest.mock import patch

import pytest

from vauxhall.core.config import ConfigurationError, load_config_data


def test_load_config_data_os_error(tmp_path: Path) -> None:
    """Unreadable explicit files raise a source-aware configuration error.

    Args:
        tmp_path: Pytest temporary directory.
    """
    config_file = tmp_path / "unreadable.json"
    config_file.touch()

    # Simulate OSError by mocking Path.open
    with (
        patch.object(Path, "open", side_effect=OSError("Permission denied")),
        pytest.raises(ConfigurationError, match="Could not read configuration"),
    ):
        load_config_data(config_file)
