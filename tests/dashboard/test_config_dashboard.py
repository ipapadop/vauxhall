# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for loading and validating dashboard configuration."""

import json
import re
from pathlib import Path

import pytest

from vauxhall.core.config import ConfigurationError
from vauxhall.dashboard.config import DashboardConfig


def test_dashboard_config_loading(tmp_path: Path) -> None:
    """Test loading dashboard configuration from a JSON file.

    Args:
        tmp_path: Pytest temporary directory.
    """
    config_file = tmp_path / "vauxhall_dashboard.json"
    config_file.write_text(json.dumps({"dashboard": {"width": 1200}}))

    config = DashboardConfig.load(config_file)
    assert config.dashboard.width == 1200
    assert config.dashboard.height == 800  # Default


@pytest.mark.parametrize("payload", [[], "bad", 7, True])
def test_top_level_json_must_be_an_object(tmp_path: Path, payload: object) -> None:
    """Configuration files must contain JSON objects at their top level.

    Args:
        tmp_path: Pytest temporary directory.
        payload: The case's payload.
    """
    path = tmp_path / "vauxhall_dashboard.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ConfigurationError,
        match=rf"{re.escape(str(path))}.*top-level.*{re.escape(repr(payload))}",
    ):
        DashboardConfig.load(path)


@pytest.mark.parametrize("section", [[], "bad", 7, True])
def test_config_section_must_be_an_object(tmp_path: Path, section: object) -> None:
    """Named configuration sections must be objects.

    Args:
        tmp_path: Pytest temporary directory.
        section: The case's configuration section.
    """
    path = tmp_path / "vauxhall_dashboard.json"
    path.write_text(json.dumps({"mqtt": section}), encoding="utf-8")

    with pytest.raises(ConfigurationError, match=r"mqtt.*object"):
        DashboardConfig.load(path)


@pytest.mark.parametrize("port", [0, 65536, True, "1883"])
def test_json_mqtt_port_is_strictly_validated(tmp_path: Path, port: object) -> None:
    """MQTT port must be an integer within the supported port range.

    Args:
        tmp_path: Pytest temporary directory.
        port: The case's broker port.
    """
    path = tmp_path / "vauxhall_dashboard.json"
    path.write_text(json.dumps({"mqtt": {"port": port}}), encoding="utf-8")

    with pytest.raises(ConfigurationError, match=r"mqtt\.port.*1\.\.65535"):
        DashboardConfig.load(path)


@pytest.mark.parametrize("value", ["maybe", "", "2"])
def test_invalid_boolean_environment_value_fails_fast(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Invalid explicit dashboard booleans never fall back to defaults.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        value: The case's value.
    """
    monkeypatch.setenv("VAUXHALL_DASHBOARD_DEBUG", value)

    with pytest.raises(ConfigurationError, match=r"VAUXHALL_DASHBOARD_DEBUG.*boolean"):
        DashboardConfig.load()


@pytest.mark.parametrize("level", ["TRACE", "verbose", ""])
def test_invalid_logging_level_identifies_source(tmp_path: Path, level: str) -> None:
    """Logging choices report their path, logical field, and original value.

    Args:
        tmp_path: Pytest temporary directory.
        level: The case's logging level.
    """
    path = tmp_path / "vauxhall_dashboard.json"
    path.write_text(json.dumps({"logging": {"level": level}}), encoding="utf-8")

    with pytest.raises(
        ConfigurationError,
        match=rf"{re.escape(str(path))}.*logging\.level.*{re.escape(repr(level))}",
    ):
        DashboardConfig.load(path)


@pytest.mark.parametrize(
    ("field", "minimum", "maximum"),
    [
        ("width", 320, 16384),
        ("height", 320, 16384),
        ("stale_threshold", 1, 86400),
        ("pending_update_limit", 1, 10000),
        ("max_active_agents", 1, 1000),
        ("max_payload_bytes", 1024, 1048576),
    ],
)
def test_dashboard_limits_accept_locked_boundaries(
    tmp_path: Path, field: str, minimum: int, maximum: int
) -> None:
    """Dashboard limits accept both inclusive policy boundaries.

    Args:
        tmp_path: Pytest temporary directory.
        field: The configuration field under test.
        minimum: The field's lowest accepted value.
        maximum: The field's highest accepted value.
    """
    path = tmp_path / "vauxhall_dashboard.json"

    for value in (minimum, maximum):
        path.write_text(json.dumps({"dashboard": {field: value}}), encoding="utf-8")
        assert getattr(DashboardConfig.load(path).dashboard, field) == value


@pytest.mark.parametrize(
    ("field", "minimum", "maximum"),
    [
        ("width", 320, 16384),
        ("height", 320, 16384),
        ("stale_threshold", 1, 86400),
        ("pending_update_limit", 1, 10000),
        ("max_active_agents", 1, 1000),
        ("max_payload_bytes", 1024, 1048576),
    ],
)
def test_dashboard_limits_reject_values_outside_locked_boundaries(
    tmp_path: Path, field: str, minimum: int, maximum: int
) -> None:
    """Dashboard limits reject values outside their inclusive policy bounds.

    Args:
        tmp_path: Pytest temporary directory.
        field: The configuration field under test.
        minimum: The field's lowest accepted value.
        maximum: The field's highest accepted value.
    """
    path = tmp_path / "vauxhall_dashboard.json"

    for value in (minimum - 1, maximum + 1):
        path.write_text(json.dumps({"dashboard": {field: value}}), encoding="utf-8")
        with pytest.raises(ConfigurationError, match=rf"dashboard\.{field}"):
            DashboardConfig.load(path)


def test_invalid_environment_value_overrides_valid_file(tmp_path: Path) -> None:
    """An invalid environment override cannot be masked by a valid file value.

    Args:
        tmp_path: Pytest temporary directory.
    """
    path = tmp_path / "vauxhall_dashboard.json"
    path.write_text(json.dumps({"mqtt": {"port": 1883}}), encoding="utf-8")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("VAUXHALL_MQTT_PORT", "invalid")
        with pytest.raises(
            ConfigurationError,
            match=r"VAUXHALL_MQTT_PORT.*mqtt\.port.*'invalid'.*integer",
        ):
            DashboardConfig.load(path)
