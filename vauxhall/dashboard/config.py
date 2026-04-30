# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Dashboard configuration for Vauxhall."""

from dataclasses import dataclass, field
from pathlib import Path

from vauxhall.core.config import (
    ConfigResolver,
    LoggingConfig,
    MQTTConfig,
)


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
        """Load configuration from environment or file.

        Args:
            config_path: Optional path to the configuration file.

        Returns:
            DashboardConfig: The loaded configuration.
        """
        resolver = ConfigResolver("vauxhall_dashboard.json", config_path)

        return cls(
            mqtt=MQTTConfig(
                host=resolver.get("VAUXHALL_MQTT_HOST", "mqtt", "host", "localhost"),
                port=resolver.get("VAUXHALL_MQTT_PORT", "mqtt", "port", 1883),
                keepalive=resolver.get(
                    "VAUXHALL_MQTT_KEEPALIVE", "mqtt", "keepalive", 60
                ),
            ),
            logging=LoggingConfig(
                level=resolver.get("VAUXHALL_LOGGING_LEVEL", "logging", "level", "INFO")
            ),
            dashboard=UIConfig(
                host=resolver.get(
                    "VAUXHALL_DASHBOARD_HOST", "dashboard", "host", "127.0.0.1"
                ),
                port=resolver.get("VAUXHALL_DASHBOARD_PORT", "dashboard", "port", 8080),
                debug=resolver.get(
                    "VAUXHALL_DASHBOARD_DEBUG", "dashboard", "debug", False
                ),
                window_title=resolver.get(
                    "VAUXHALL_DASHBOARD_TITLE",
                    "dashboard",
                    "window_title",
                    "Vauxhall Agent Dashboard",
                ),
                width=resolver.get(
                    "VAUXHALL_DASHBOARD_WIDTH", "dashboard", "width", 1000
                ),
                height=resolver.get(
                    "VAUXHALL_DASHBOARD_HEIGHT", "dashboard", "height", 800
                ),
                stale_threshold=resolver.get(
                    "VAUXHALL_DASHBOARD_STALE_THRESHOLD",
                    "dashboard",
                    "stale_threshold",
                    120,
                ),
            ),
        )


dashboard_settings = DashboardConfig.load()
