import json
from pathlib import Path

from vauxhall.core.config import LoggingConfig, MQTTConfig, load_config_data


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
