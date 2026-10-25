# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Unit tests for ConfigResolver."""

import os
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from vauxhall.core.config import ConfigResolver


@dataclass
class MockConfig:
    """Mock config for testing resolve_dataclass."""

    host: str = "localhost"
    port: int = 1883
    enabled: bool = True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("1", True),
        ("YES", True),
        ("false", False),
        ("0", False),
        ("No", False),
    ],
)
def test_resolve_dataclass_parses_boolean_environment_values(
    value: str,
    expected: bool,  # noqa: FBT001
) -> None:
    """Every accepted spelling of a boolean sets a boolean field.

    Args:
        value: The environment variable's value.
        expected: The boolean it stands for.
    """
    resolver = ConfigResolver("test_config.json")
    with patch.dict(os.environ, {"VAUXHALL_TEST_ENABLED": value}):
        config = resolver.resolve_dataclass(MockConfig, "test")

    assert config.enabled is expected


def test_resolve_dataclass() -> None:
    """Test that ConfigResolver can resolve a full dataclass."""
    resolver = ConfigResolver("test_config.json")

    # 1. Test with defaults
    config = resolver.resolve_dataclass(MockConfig, "test")
    assert config.host == "localhost"
    assert config.port == 1883
    assert config.enabled is True

    # 2. Test with JSON override
    json_data = {"test": {"host": "json.host", "port": 9000}}
    with (
        patch("vauxhall.core.config.find_config_file", return_value=Path("dummy.json")),
        patch("vauxhall.core.config.load_config_data", return_value=json_data),
    ):
        resolver_json = ConfigResolver("test_config.json")
        config = resolver_json.resolve_dataclass(MockConfig, "test")
        assert config.host == "json.host"
        assert config.port == 9000
        assert config.enabled is True

    # 3. Test with Env override
    with patch.dict(
        os.environ,
        {
            "VAUXHALL_TEST_HOST": "env.host",
            "VAUXHALL_TEST_PORT": "1234",
            "VAUXHALL_TEST_ENABLED": "false",
        },
    ):
        resolver_env = ConfigResolver("test_config.json")
        config = resolver_env.resolve_dataclass(MockConfig, "test")
        assert config.host == "env.host"
        assert config.port == 1234
        assert config.enabled is False


def test_resolve_dataclass_reads_only_the_given_environment() -> None:
    """An injected environment replaces the process environment."""
    with patch.dict(os.environ, {"VAUXHALL_TEST_HOST": "process"}):
        resolver = ConfigResolver(
            "missing.json", environment={"VAUXHALL_TEST_PORT": "1884"}
        )
        config = resolver.resolve_dataclass(MockConfig, "test")

    assert config.host == "localhost"
    assert config.port == 1884
