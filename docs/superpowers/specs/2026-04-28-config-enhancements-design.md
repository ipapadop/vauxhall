# Design Spec: Configuration Enhancements (Env Vars & Search Paths)

**Date:** 2026-04-28
**Status:** Draft
**Topic:** Configuration Robustness & Distributed Support

## 1. Goal
Enhance the configuration system with Environment Variable support, standardized search paths, and consistent logging. Introduce an optimization to bypass file loading when environment variables are fully provided.

## 2. Architecture

### 2.1 Core Search & Resolution (`vauxhall/core/config.py`)
- **New Utility: `find_config_file(filename: str) -> Path | None`**
    - Searches `./filename`.
    - Searches `~/.config/vauxhall/filename`.
    - Returns the first existing path or `None`.
- **New Utility: `get_env(env_var: str, default: T) -> T`**
    - Helper for type-safe environment variable retrieval.

### 2.2 Environment-Only Optimization
- Before searching for a JSON file, the `load()` method of `HookConfig` and `DashboardConfig` will check if "critical" environment variables are set.
- **Hook Optimization**: If `VAUXHALL_MQTT_HOST` is set, bypass JSON file searching.
- **Dashboard Optimization**: If `VAUXHALL_MQTT_HOST` is set, bypass JSON file searching.

## 3. Resolution Priority
For each field:
1.  **Environment Variable** (e.g., `VAUXHALL_MQTT_HOST`)
2.  **JSON File Value** (if file found via search paths)
3.  **Dataclass Default**

## 4. Configuration Mapping

| Setting | Env Var | JSON Path | Default |
| :--- | :--- | :--- | :--- |
| MQTT Host | `VAUXHALL_MQTT_HOST` | `mqtt.host` | `localhost` |
| MQTT Port | `VAUXHALL_MQTT_PORT` | `mqtt.port` | `1883` |
| Logging Level | `VAUXHALL_LOGGING_LEVEL` | `logging.level` | `INFO` |
| UI Host | `VAUXHALL_DASHBOARD_HOST` | `dashboard.host` | `127.0.0.1` |
| UI Port | `VAUXHALL_DASHBOARD_PORT` | `dashboard.port` | `8080` |

## 5. Implementation Steps

1.  **Core Updates**:
    - Add `find_config_file` to `vauxhall/core/config.py`.
    - Add helper for environment variable resolution (handling types like `int`).
2.  **Hook Config Update**:
    - Update `HookConfig.load()` to implement search paths and environment-only optimization.
3.  **Dashboard Config Update**:
    - Update `DashboardConfig.load()` to implement search paths and environment-only optimization.
4.  **Logging Consistency**:
    - Update `vauxhall/hooks/gemini/telemetry_hook.py` to pass `hook_settings.logging.level` to `setup_logging()`.
5.  **Testing**:
    - Test `find_config_file` (mocking filesystem).
    - Test `load()` with environment variables (mocking `os.environ`).
    - Test environment-only optimization (verify no file access when env vars present).

## 6. Success Criteria
- Components correctly find config in `~/.config/vauxhall/`.
- `export VAUXHALL_MQTT_HOST=my-broker` overrides JSON settings.
- Providing `VAUXHALL_MQTT_HOST` avoids "File not found" logs for the JSON file.
- Logging level from config/env is correctly applied to hooks.
