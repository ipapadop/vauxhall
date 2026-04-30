# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <giannis.papadopoulos@gmail.com>
# SPDX-License-Identifier: MIT

"""Dashboard configuration for Vauxhall."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from vauxhall.core.config import (
    LoggingConfig,
    MQTTConfig,
    find_config_file,
    get_env,
    load_config_data,
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
        # 1. Check for Env-Only Optimization
        env_host = os.environ.get("VAUXHALL_MQTT_HOST")
        if env_host and config_path is None:
            return cls(
                mqtt=MQTTConfig(
                    host=env_host,
                    port=get_env("VAUXHALL_MQTT_PORT", 1883),
                    keepalive=get_env("VAUXHALL_MQTT_KEEPALIVE", 60),
                ),
                logging=LoggingConfig(level=get_env("VAUXHALL_LOGGING_LEVEL", "INFO")),
                dashboard=UIConfig(
                    host=get_env("VAUXHALL_DASHBOARD_HOST", "127.0.0.1"),
                    port=get_env("VAUXHALL_DASHBOARD_PORT", 8080),
                    debug=get_env("VAUXHALL_DASHBOARD_DEBUG", default=False),
                    window_title=get_env(
                        "VAUXHALL_DASHBOARD_TITLE", "Vauxhall Agent Dashboard"
                    ),
                    width=get_env("VAUXHALL_DASHBOARD_WIDTH", 1000),
                    height=get_env("VAUXHALL_DASHBOARD_HEIGHT", 800),
                    stale_threshold=get_env("VAUXHALL_DASHBOARD_STALE_THRESHOLD", 120),
                ),
            )

        # 2. Regular resolution
        if config_path is None:
            config_path = find_config_file("vauxhall_dashboard.json")

        data = load_config_data(config_path) if config_path else {}

        return cls(
            mqtt=MQTTConfig(
                host=get_env(
                    "VAUXHALL_MQTT_HOST", data.get("mqtt", {}).get("host", "localhost")
                ),
                port=get_env(
                    "VAUXHALL_MQTT_PORT", data.get("mqtt", {}).get("port", 1883)
                ),
                keepalive=get_env(
                    "VAUXHALL_MQTT_KEEPALIVE", data.get("mqtt", {}).get("keepalive", 60)
                ),
            ),
            logging=LoggingConfig(
                level=get_env(
                    "VAUXHALL_LOGGING_LEVEL",
                    data.get("logging", {}).get("level", "INFO"),
                )
            ),
            dashboard=UIConfig(
                host=get_env(
                    "VAUXHALL_DASHBOARD_HOST",
                    data.get("dashboard", {}).get("host", "127.0.0.1"),
                ),
                port=get_env(
                    "VAUXHALL_DASHBOARD_PORT",
                    data.get("dashboard", {}).get("port", 8080),
                ),
                debug=get_env(
                    "VAUXHALL_DASHBOARD_DEBUG",
                    default=data.get("dashboard", {}).get("debug", False),
                ),
                window_title=get_env(
                    "VAUXHALL_DASHBOARD_TITLE",
                    data.get("dashboard", {}).get(
                        "window_title", "Vauxhall Agent Dashboard"
                    ),
                ),
                width=get_env(
                    "VAUXHALL_DASHBOARD_WIDTH",
                    data.get("dashboard", {}).get("width", 1000),
                ),
                height=get_env(
                    "VAUXHALL_DASHBOARD_HEIGHT",
                    data.get("dashboard", {}).get("height", 800),
                ),
                stale_threshold=get_env(
                    "VAUXHALL_DASHBOARD_STALE_THRESHOLD",
                    data.get("dashboard", {}).get("stale_threshold", 120),
                ),
            ),
        )


dashboard_settings = DashboardConfig.load()
