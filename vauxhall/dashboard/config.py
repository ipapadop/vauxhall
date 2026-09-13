# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
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

    port: int = field(default=8080, metadata={"min": 1, "max": 65535})
    debug: bool = False
    window_title: str = field(
        default="Vauxhall Agent Dashboard", metadata={"non_empty": True}
    )
    width: int = field(default=1000, metadata={"min": 320, "max": 16384})
    height: int = field(default=800, metadata={"min": 320, "max": 16384})
    stale_threshold: int = field(default=120, metadata={"min": 1, "max": 86400})
    pending_update_limit: int = field(default=500, metadata={"min": 1, "max": 10000})
    max_active_agents: int = field(default=100, metadata={"min": 1, "max": 1000})
    max_payload_bytes: int = field(
        default=65536, metadata={"min": 1024, "max": 1048576}
    )


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
            mqtt=resolver.resolve_dataclass(MQTTConfig, "mqtt", "VAUXHALL_MQTT"),
            logging=resolver.resolve_dataclass(
                LoggingConfig, "logging", "VAUXHALL_LOGGING"
            ),
            dashboard=resolver.resolve_dataclass(
                UIConfig, "dashboard", "VAUXHALL_DASHBOARD"
            ),
        )


dashboard_settings = DashboardConfig.load()
