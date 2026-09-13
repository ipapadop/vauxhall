# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

import json
from pathlib import Path

import pytest

from vauxhall.core.config import (
    ConfigResolver,
    ConfigurationError,
    LoggingConfig,
    MQTTConfig,
    load_config_data,
)


def test_default_configs() -> None:
    """Test default MQTT and Logging configurations."""
    mqtt = MQTTConfig()
    assert mqtt.host == "localhost"
    assert mqtt.port == 1883

    log = LoggingConfig()
    assert log.level == "INFO"


def test_load_config_data(tmp_path: Path) -> None:
    """Test loading configuration data from a JSON file."""
    config_file = tmp_path / "vauxhall.json"
    data = {"mqtt": {"port": 1234}, "logging": {"level": "DEBUG"}}
    with config_file.open("w") as f:
        json.dump(data, f)

    loaded_data = load_config_data(config_file)
    assert loaded_data == data


def test_load_config_data_nonexistent() -> None:
    """Test loading configuration data from a nonexistent file."""
    assert load_config_data(Path("nonexistent.json")) == {}


def test_load_config_data_rejects_malformed_json(tmp_path: Path) -> None:
    """A malformed explicit file cannot silently replace safe defaults."""
    config_file = tmp_path / "vauxhall.json"
    config_file.write_text("{ invalid json }", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="not valid JSON"):
        load_config_data(config_file)


def test_mqtt_keepalive_accepts_locked_boundaries(tmp_path: Path) -> None:
    """MQTT keepalive accepts its inclusive policy boundaries."""
    config_file = tmp_path / "vauxhall.json"
    config_file.write_text(json.dumps({"mqtt": {"keepalive": 0}}), encoding="utf-8")

    assert (
        ConfigResolver("vauxhall.json", config_file)
        .resolve_dataclass(MQTTConfig, "mqtt", "VAUXHALL_MQTT")
        .keepalive
        == 0
    )

    config_file.write_text(json.dumps({"mqtt": {"keepalive": 65535}}), encoding="utf-8")
    assert (
        ConfigResolver("vauxhall.json", config_file)
        .resolve_dataclass(MQTTConfig, "mqtt", "VAUXHALL_MQTT")
        .keepalive
        == 65535
    )


@pytest.mark.parametrize("keepalive", [-1, 65536])
def test_mqtt_keepalive_rejects_values_outside_locked_boundaries(
    tmp_path: Path, keepalive: int
) -> None:
    """MQTT keepalive rejects values outside its inclusive range."""
    config_file = tmp_path / "vauxhall.json"
    config_file.write_text(
        json.dumps({"mqtt": {"keepalive": keepalive}}), encoding="utf-8"
    )

    with pytest.raises(ConfigurationError, match=r"mqtt\.keepalive.*0\.\.65535"):
        ConfigResolver("vauxhall.json", config_file).resolve_dataclass(
            MQTTConfig, "mqtt", "VAUXHALL_MQTT"
        )
