# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Choice of the graphics API the dashboard window renders with.

Qt Quick, which displays the page Chromium renders, reads ``QSG_RHI_BACKEND``
when the application starts. On Linux its default, OpenGL, can show a blank
window on Wayland, so ``auto`` prefers Vulkan there.
"""

import ctypes
import os
import sys
from collections.abc import Callable, MutableMapping
from typing import Any

from vauxhall.core.logging import get_logger

logger = get_logger(__name__)

_VULKAN_LIBRARIES = {"win32": "vulkan-1.dll", "darwin": "libvulkan.1.dylib"}
_VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO = 1
_VK_SUCCESS = 0


class _VkInstanceCreateInfo(ctypes.Structure):
    _fields_ = (
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("pApplicationInfo", ctypes.c_void_p),
        ("enabledLayerCount", ctypes.c_uint32),
        ("ppEnabledLayerNames", ctypes.c_void_p),
        ("enabledExtensionCount", ctypes.c_uint32),
        ("ppEnabledExtensionNames", ctypes.c_void_p),
    )


def vulkan_available(load_library: Callable[[str], Any] = ctypes.CDLL) -> bool:
    """Report whether Vulkan has a driver with at least one device.

    Creates and destroys a bare Vulkan instance, which is what Qt needs first.

    Args:
        load_library: Loads a shared library by name.

    Returns:
        Whether an instance could be created and reports a physical device.
    """
    name = _VULKAN_LIBRARIES.get(sys.platform, "libvulkan.so.1")
    try:
        library = load_library(name)
        info = _VkInstanceCreateInfo(sType=_VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO)
        instance = ctypes.c_void_p()
        if library.vkCreateInstance(ctypes.byref(info), None, ctypes.byref(instance)):
            return False
        try:
            count = ctypes.c_uint32()
            result = library.vkEnumeratePhysicalDevices(
                instance, ctypes.byref(count), None
            )
            return result == _VK_SUCCESS and count.value > 0
        finally:
            library.vkDestroyInstance(instance, None)
    except (OSError, AttributeError):
        return False


def set_graphics_backend(
    backend: str,
    environ: MutableMapping[str, str] = os.environ,
    platform: str = sys.platform,
    vulkan_probe: Callable[[], bool] = vulkan_available,
) -> None:
    """Set up the environment for the configured graphics backend.

    Must run before ``Pyloid`` creates the application. A ``QSG_RHI_BACKEND``
    the user set leaves the graphics setup to them.

    Args:
        backend: ``auto``, ``vulkan``, ``opengl``, or ``software``.
        environ: The environment to update.
        platform: The ``sys.platform`` value.
        vulkan_probe: Reports whether Vulkan works on this machine.
    """
    if "QSG_RHI_BACKEND" in environ:
        logger.info(
            "Using QSG_RHI_BACKEND=%s from the environment.", environ["QSG_RHI_BACKEND"]
        )
        return
    if backend == "software":
        flags = environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} --disable-gpu".strip()
        return
    if backend == "auto":
        if not platform.startswith("linux"):
            return
        backend = "vulkan"
    if backend == "vulkan" and not vulkan_probe():
        logger.warning(
            "Vulkan is not available; letting Qt choose the graphics backend. "
            "If the window stays blank, set dashboard.graphics_backend to "
            "software."
        )
        return
    environ["QSG_RHI_BACKEND"] = backend
