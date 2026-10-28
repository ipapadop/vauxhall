# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Vauxhall agent telemetry and dashboard package."""


def _read_version() -> str:
    """Read the installed distribution's version and cache it as ``__version__``.

    Called on first access, not on import: every hook event imports this
    package in a new process, and reading the distribution metadata adds
    about 2 ms to each one; only the installer needs the version.

    Returns:
        The installed distribution's version.
    """
    from importlib.metadata import version  # noqa: PLC0415

    package_version = version("vauxhall")
    globals()["__version__"] = package_version
    return package_version


def __getattr__(name: str) -> str:
    """Resolve ``__version__`` lazily; Python calls this for missing attributes.

    Args:
        name: The attribute being looked up.

    Returns:
        The installed distribution's version.

    Raises:
        AttributeError: If ``name`` is not ``__version__``.
    """
    if name != "__version__":
        message = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(message)
    return _read_version()
