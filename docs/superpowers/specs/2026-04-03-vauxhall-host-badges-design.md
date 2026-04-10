# Design Spec: Host/Environment Badges

**Date:** 2026-04-03
**Topic:** Distinguishing between local and remote execution environments.

## 1. Overview
Agents can run on various machines (local laptop, SSH server). Providing clear visual context about the execution environment helps users navigate their workspaces more effectively.

## 2. Data Model
A new optional field `env` will be added to the telemetry payload.
- **Values:** `local`, `remote`.
- **Defaulting:** If `env` is missing, the dashboard will check the `workspace` path. Paths starting with `/home` or `C:\` default to `local`.

### Updated Message Format
```json
{
  "agent": "Gemini-1.5-Pro",
  "env": "remote",
  "workspace": "/var/www/project"
}
```

## 3. UI Design
- **Environment Badge:** A small text label placed before the agent name in the card header.
- **Styling:**
    - `.env-local`: Green background, white text ("LOCAL").
    - `.env-remote`: Blue background, white text ("REMOTE").

## 4. Interactions
- The environment badge will be included in the clipboard command when clicking a card if applicable (e.g., prefixing `ssh host` if the environment is remote).

## 5. Implementation Steps
1. Update `TelemetryClient.send` in `hooks/client.py` to optionally accept an `env` parameter.
2. Update `createCard` in `app.js` to render the environment badge.
3. Add CSS for `.env-badge` variations.
