# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Dashboard configuration for Vauxhall."""

from dataclasses import dataclass, field
from pathlib import Path

from vauxhall.core.config import LoggingConfig, MQTTConfig, load_config_data


@dataclass
class UIConfig:
    """UI configuration for the dashboard."""

    host: str = "127.0.0.1"
    port: int = 8080
    debug: bool = False
    window_title: str = "Vauxhall Agent Dashboard"
    width: int = 1000
    height: int = 800
    stale_threshold: int = 120


@dataclass
class DashboardConfig:
    """Consolidated configuration for the dashboard."""

    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    dashboard: UIConfig = field(default_factory=UIConfig)

    @classmethod
    def load(cls, config_path: Path | None = None) -> "DashboardConfig":
        """Load configuration from a file.

        Args:
            config_path: Path to the configuration file.

        Returns:
            DashboardConfig: The loaded configuration.
        """
        if config_path is None:
            config_path = Path("vauxhall_dashboard.json")

        data = load_config_data(config_path)
        return cls(
            mqtt=MQTTConfig(**data.get("mqtt", {})),
            logging=LoggingConfig(**data.get("logging", {})),
            dashboard=UIConfig(**data.get("dashboard", {})),
        )


dashboard_settings = DashboardConfig.load()
