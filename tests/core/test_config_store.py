# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for saving per-user configuration files."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from vauxhall.core.config import ConfigurationError
from vauxhall.core.config_store import (
    FieldSource,
    check_user_config,
    field_sources,
    save_user_config,
    user_config_path,
)
from vauxhall.dashboard.config import DashboardConfig
from vauxhall.hooks.config import HookConfig

DASHBOARD_FILE = "vauxhall_dashboard.json"
HOOKS_FILE = "vauxhall_hooks.json"


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the home directory, working directory, and environment."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(cwd)
    for name in list(os.environ):
        if name.startswith("VAUXHALL_"):
            monkeypatch.delenv(name)


def write_user_file(content: str) -> Path:
    """Write raw content to the per-user dashboard configuration file."""
    path = user_config_path(DASHBOARD_FILE)
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("filename", "config_type", "changes"),
    [
        (
            DASHBOARD_FILE,
            DashboardConfig,
            {"mqtt": {"host": "broker"}, "dashboard": {"stale_threshold": 300}},
        ),
        (HOOKS_FILE, HookConfig, {"mqtt": {"host": "broker"}}),
    ],
)
def test_saved_values_load_back(
    filename: str, config_type: type[Any], changes: dict[str, dict[str, object]]
) -> None:
    """Saved values are written to the user file and load unchanged."""
    path = save_user_config(filename, config_type, changes)

    assert path == user_config_path(filename)
    config = config_type.load(path)
    for section, values in changes.items():
        for key, value in values.items():
            assert getattr(getattr(config, section), key) == value


def test_check_user_config_validates_without_writing() -> None:
    """Checking reports the target path and errors but never writes the file."""
    path = check_user_config(
        DASHBOARD_FILE, DashboardConfig, {"mqtt": {"host": "broker"}}
    )

    assert path == user_config_path(DASHBOARD_FILE)
    assert not path.exists()
    with pytest.raises(ConfigurationError, match=r"mqtt\.port"):
        check_user_config(DASHBOARD_FILE, DashboardConfig, {"mqtt": {"port": 0}})


def test_save_keeps_unknown_sections_and_other_keys() -> None:
    """Merging keeps keys and sections the change does not mention."""
    path = write_user_file(json.dumps({"custom": {"x": 1}, "mqtt": {"port": 1884}}))

    save_user_config(DASHBOARD_FILE, DashboardConfig, {"mqtt": {"host": "broker"}})

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "custom": {"x": 1},
        "mqtt": {"port": 1884, "host": "broker"},
    }


def test_default_values_are_removed() -> None:
    """Saving a default removes the key, and the section once it is empty."""
    path = write_user_file(json.dumps({"mqtt": {"port": 1884}}))

    save_user_config(DASHBOARD_FILE, DashboardConfig, {"mqtt": {"port": 1883}})

    assert json.loads(path.read_text(encoding="utf-8")) == {}


def test_value_of_another_type_equal_to_default_is_kept_and_rejected() -> None:
    """A value equal to the default but of another type is validated, not removed."""
    with pytest.raises(ConfigurationError, match=r"dashboard\.debug"):
        save_user_config(DASHBOARD_FILE, DashboardConfig, {"dashboard": {"debug": 0}})

    assert not user_config_path(DASHBOARD_FILE).exists()


def test_invalid_value_leaves_file_unchanged() -> None:
    """An invalid change raises with the real path and does not touch the file."""
    path = write_user_file('{"mqtt": {"host": "broker"}}')
    original = path.read_bytes()

    with pytest.raises(ConfigurationError, match=r"mqtt\.port") as error:
        save_user_config(DASHBOARD_FILE, DashboardConfig, {"mqtt": {"port": 0}})

    assert str(path) in str(error.value)
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    ("content", "match"),
    [("{", "not valid JSON"), ('{"mqtt": 5}', "mqtt must be an object")],
)
def test_malformed_user_file_is_refused(content: str, match: str) -> None:
    """A malformed user file is never overwritten."""
    path = write_user_file(content)

    with pytest.raises(ConfigurationError, match=match):
        save_user_config(DASHBOARD_FILE, DashboardConfig, {"mqtt": {"host": "b"}})

    assert path.read_text(encoding="utf-8") == content


def test_environment_overridden_field_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fields set by an environment variable cannot be saved."""
    monkeypatch.setenv("VAUXHALL_MQTT_HOST", "env-broker")

    with pytest.raises(ConfigurationError, match="VAUXHALL_MQTT_HOST"):
        save_user_config(DASHBOARD_FILE, DashboardConfig, {"mqtt": {"host": "b"}})

    assert not user_config_path(DASHBOARD_FILE).exists()


def test_save_is_refused_when_current_directory_file_takes_precedence() -> None:
    """A save that a current-directory file would hide is rejected."""
    (Path.cwd() / DASHBOARD_FILE).write_text("{}", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="current directory"):
        save_user_config(DASHBOARD_FILE, DashboardConfig, {"mqtt": {"host": "b"}})

    assert not user_config_path(DASHBOARD_FILE).exists()


@pytest.mark.parametrize(
    ("filename", "config_type", "changes"),
    [
        (DASHBOARD_FILE, DashboardConfig, {"mqtt": {"password": "x"}}),
        (DASHBOARD_FILE, DashboardConfig, {"broker": {"host": "x"}}),
        (HOOKS_FILE, HookConfig, {"dashboard": {"port": 9000}}),
    ],
)
def test_unknown_field_is_refused(
    filename: str, config_type: type[Any], changes: dict[str, dict[str, object]]
) -> None:
    """Fields that the configuration type does not define are rejected."""
    with pytest.raises(ConfigurationError, match="Unknown configuration field"):
        save_user_config(filename, config_type, changes)


def test_sources_default_without_files() -> None:
    """Without files or environment variables, every field is an editable default."""
    sources = field_sources(DASHBOARD_FILE, DashboardConfig)

    assert sources["mqtt.host"] == FieldSource("default", None, editable=True)
    assert set(sources) >= {"logging.level", "dashboard.max_payload_bytes"}
    assert all(source.editable for source in sources.values())


def test_sources_user_file_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """User-file values are editable; environment values are not."""
    path = write_user_file('{"mqtt": {"host": "broker"}}')
    monkeypatch.setenv("VAUXHALL_MQTT_PORT", "1884")

    sources = field_sources(DASHBOARD_FILE, DashboardConfig)

    assert sources["mqtt.host"] == FieldSource(
        "file", str(path.resolve()), editable=True
    )
    assert sources["mqtt.port"] == FieldSource(
        "environment", "VAUXHALL_MQTT_PORT", editable=False
    )
    assert sources["mqtt.keepalive"] == FieldSource("default", None, editable=True)


@pytest.mark.parametrize("in_current_directory", [False, True])
def test_sources_refuse_non_object_section(*, in_current_directory: bool) -> None:
    """A known section that is not an object is rejected, as the loader does."""
    path = (
        Path.cwd() / DASHBOARD_FILE
        if in_current_directory
        else user_config_path(DASHBOARD_FILE)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"mqtt": 5}', encoding="utf-8")

    with pytest.raises(ConfigurationError, match="mqtt must be an object"):
        DashboardConfig.load()
    with pytest.raises(ConfigurationError, match="mqtt must be an object") as error:
        field_sources(DASHBOARD_FILE, DashboardConfig)

    assert str(path.resolve()) in str(error.value)


def test_sources_current_directory_file_hides_user_file() -> None:
    """A current-directory file makes every non-environment field read-only."""
    write_user_file('{"mqtt": {"port": 1884}}')
    cwd_file = Path.cwd() / DASHBOARD_FILE
    cwd_file.write_text('{"mqtt": {"host": "local"}}', encoding="utf-8")

    sources = field_sources(DASHBOARD_FILE, DashboardConfig)

    assert sources["mqtt.host"] == FieldSource(
        "file", str(cwd_file.resolve()), editable=False
    )
    assert sources["mqtt.port"] == FieldSource("default", None, editable=False)
