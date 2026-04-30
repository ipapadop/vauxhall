# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Test for automatic logging initialization in hook config."""

import importlib
import sys
from unittest.mock import patch


def test_logging_initialized_on_import() -> None:
    """Test that setup_logging is called when vauxhall.hooks.config is imported."""
    # Ensure the module is not in sys.modules so we can trigger the top-level code
    if "vauxhall.hooks.config" in sys.modules:
        del sys.modules["vauxhall.hooks.config"]

    # Patch setup_logging in the core module before importing config
    with patch("vauxhall.core.logging.setup_logging") as mock_core_setup:
        importlib.import_module("vauxhall.hooks.config")
        mock_core_setup.assert_called_once()
        # It should be called with the default level if no env/file is present
        _args, kwargs = mock_core_setup.call_args
        assert kwargs.get("level") == "INFO"


def test_logging_initialized_with_env_level() -> None:
    """Test that setup_logging is called with the level from environment variable."""
    # Ensure the module is not in sys.modules
    if "vauxhall.hooks.config" in sys.modules:
        del sys.modules["vauxhall.hooks.config"]

    env = {"VAUXHALL_LOGGING_LEVEL": "DEBUG"}
    with (
        patch.dict(sys.modules, {}),  # More isolation
        patch.dict("os.environ", env),
        patch("vauxhall.core.logging.setup_logging") as mock_core_setup,
    ):
        importlib.import_module("vauxhall.hooks.config")
        mock_core_setup.assert_called_once()
        _args, kwargs = mock_core_setup.call_args
        assert kwargs.get("level") == "DEBUG"
