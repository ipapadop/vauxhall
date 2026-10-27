# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Vauxhall agent telemetry and dashboard package."""


def __getattr__(name: str) -> str:
    """Read ``__version__`` on first access, not on import.

    Every hook event imports this package in a new process, and reading
    the distribution metadata adds about 2 ms to each one; only the
    installer needs the version.

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
    from importlib.metadata import version  # noqa: PLC0415

    package_version = version("vauxhall")
    globals()["__version__"] = package_version
    return package_version
