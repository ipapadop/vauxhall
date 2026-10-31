# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Dashboard test collection."""

import importlib.util

# The dashboard extra installs no Pyloid on Python 3.14, where only the hooks
# are supported, so the modules that import it (or PySide6, or aiohttp) are
# left out there.
collect_ignore = (
    []
    if importlib.util.find_spec("pyloid")
    else [
        "test_card_state.py",
        "test_dashboard_app.py",
        "test_dashboard_config_logging.py",
        "test_ipc.py",
        "test_settings_editor.py",
        "test_ui_dispatch.py",
        "test_ui_server.py",
        "test_ui_state.py",
    ]
)
