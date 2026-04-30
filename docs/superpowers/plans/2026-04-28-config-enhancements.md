# Configuration Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement environment variable overrides, standardized search paths, and consistent logging.

**Architecture:** Add robust search and env-resolution helpers to `vauxhall/core/config.py`. Update `HookConfig.load()` and `DashboardConfig.load()` to use these helpers and implement the environment-only optimization.

**Tech Stack:** Python 3.12+, Dataclasses, JSON, os.environ.

---

### Task 1: Core Utilities for Resolution

**Files:**
- Modify: `vauxhall/core/config.py`
- Test: `tests/test_config_resolution.py` (Create)

- [ ] **Step 1: Update vauxhall/core/config.py**
Add `find_config_file` and `get_env` helpers.

```python
import os
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")

def find_config_file(filename: str) -> Path | None:
    """Search for config file in CWD and then ~/.config/vauxhall/."""
    cwd_path = Path.cwd() / filename
    if cwd_path.exists():
        return cwd_path
    
    user_config = Path.home() / ".config" / "vauxhall" / filename
    if user_config.exists():
        return user_config
        
    return None

def get_env(env_var: str, default: T) -> T:
    """Get environment variable with type-safe fallback to default."""
    value = os.environ.get(env_var)
    if value is None:
        return default
    
    # Simple type conversion based on default type
    if isinstance(default, int):
        try:
            return int(value)
        except ValueError:
            return default
    if isinstance(default, bool):
        return value.lower() in ("true", "1", "yes")
    return value
```

- [ ] **Step 2: Create test for core utilities**
```python
from pathlib import Path
from unittest.mock import patch
from vauxhall.core.config import find_config_file, get_env

def test_get_env_types():
    with patch.dict("os.environ", {"INT_VAR": "123", "BOOL_VAR": "true"}):
        assert get_env("INT_VAR", 0) == 123
        assert get_env("BOOL_VAR", False) is True
        assert get_env("NONEXISTENT", "default") == "default"

def test_find_config_file_cwd(tmp_path):
    with patch("vauxhall.core.config.Path.cwd", return_value=tmp_path):
        config_file = tmp_path / "test.json"
        config_file.touch()
        assert find_config_file("test.json") == config_file
```

- [ ] **Step 3: Run test**
`pytest tests/test_config_resolution.py`

- [ ] **Step 4: Commit**
`git add vauxhall/core/config.py tests/test_config_resolution.py && git commit -m "feat: add config resolution utilities in core"`

---

### Task 2: Enhance Hook Configuration

**Files:**
- Modify: `vauxhall/hooks/config.py`
- Test: `tests/test_config_hooks.py`

- [ ] **Step 1: Update vauxhall/hooks/config.py**
Implement environment-only optimization and search paths in `load()`.

```python
from vauxhall.core.config import MQTTConfig, LoggingConfig, load_config_data, find_config_file, get_env

@classmethod
def load(cls, config_path: Path | None = None) -> "HookConfig":
    # 1. Check for Env-Only Optimization
    env_host = os.environ.get("VAUXHALL_MQTT_HOST")
    if env_host and config_path is None:
        # Bypass file loading if critical env var is set
        return cls(
            mqtt=MQTTConfig(
                host=env_host,
                port=get_env("VAUXHALL_MQTT_PORT", 1883),
                keepalive=get_env("VAUXHALL_MQTT_KEEPALIVE", 60)
            ),
            logging=LoggingConfig(level=get_env("VAUXHALL_LOGGING_LEVEL", "INFO"))
        )

    # 2. Regular resolution
    if config_path is None:
        config_path = find_config_file("vauxhall_hooks.json")
    
    data = load_config_data(config_path) if config_path else {}
    
    return cls(
        mqtt=MQTTConfig(
            host=get_env("VAUXHALL_MQTT_HOST", data.get("mqtt", {}).get("host", "localhost")),
            port=get_env("VAUXHALL_MQTT_PORT", data.get("mqtt", {}).get("port", 1883)),
            keepalive=get_env("VAUXHALL_MQTT_KEEPALIVE", data.get("mqtt", {}).get("keepalive", 60))
        ),
        logging=LoggingConfig(
            level=get_env("VAUXHALL_LOGGING_LEVEL", data.get("logging", {}).get("level", "INFO"))
        )
    )
```

- [ ] **Step 2: Run existing hook tests**
`pytest tests/test_config_hooks.py`

- [ ] **Step 3: Commit**
`git add vauxhall/hooks/config.py && git commit -m "feat: enhance hook config with env vars and search paths"`

---

### Task 3: Enhance Dashboard Configuration

**Files:**
- Modify: `vauxhall/dashboard/config.py`
- Test: `tests/test_config_dashboard.py`

- [ ] **Step 1: Update vauxhall/dashboard/config.py**
Implement similar enhancements for the dashboard.

- [ ] **Step 2: Run existing dashboard tests**
`pytest tests/test_config_dashboard.py`

- [ ] **Step 3: Commit**
`git add vauxhall/dashboard/config.py && git commit -m "feat: enhance dashboard config with env vars and search paths"`

---

### Task 4: Fix Hook Logging Level

**Files:**
- Modify: `vauxhall/hooks/gemini/telemetry_hook.py`

- [ ] **Step 1: Update vauxhall/hooks/gemini/telemetry_hook.py**
Ensure `setup_logging` uses the configured level.

```python
# vauxhall/hooks/gemini/telemetry_hook.py
from vauxhall.hooks.config import hook_settings

def main() -> None:
    # ...
    setup_logging(level=hook_settings.logging.level)
    # ...
```

- [ ] **Step 2: Verify with tests**
`pytest tests/test_telemetry_hook.py`

- [ ] **Step 3: Commit**
`git add vauxhall/hooks/gemini/telemetry_hook.py && git commit -m "fix: telemetry hook respects configured logging level"`
