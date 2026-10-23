# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Vauxhall Dashboard application logic."""

import os

# Importing pyloid (as of 0.27.2) replaces QTWEBENGINE_CHROMIUM_FLAGS with its
# own flags, so the user's are saved here, before any submodule imports it, for
# `app.main` to restore.
USER_CHROMIUM_FLAGS = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
