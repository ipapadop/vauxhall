# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for choosing the dashboard's graphics backend."""

import ctypes
import logging

import pytest

from vauxhall.dashboard.graphics import set_graphics_backend, vulkan_available

FLAGS = "--enable-features=X"


class Probe:
    """Vulkan probe that records whether it ran."""

    def __init__(self, *, available: bool) -> None:
        """Initialize the probe with its answer.

        Args:
            available: What the probe reports.
        """
        self.available = available
        self.calls = 0

    def __call__(self) -> bool:
        """Report whether Vulkan is available.

        Returns:
            The configured answer.
        """
        self.calls += 1
        return self.available


def _apply(
    backend: str,
    platform: str = "linux",
    *,
    vulkan: bool = True,
    rhi: str | None = None,
) -> tuple[dict[str, str], Probe]:
    """Apply a graphics backend to a fresh environment.

    Args:
        backend: The configured graphics backend.
        platform: The ``sys.platform`` value to assume.
        vulkan: Whether the Vulkan probe succeeds.
        rhi: A ``QSG_RHI_BACKEND`` the user set, if any.

    Returns:
        The resulting environment and the probe.
    """
    environ = {"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS}
    if rhi is not None:
        environ["QSG_RHI_BACKEND"] = rhi
    probe = Probe(available=vulkan)
    set_graphics_backend(backend, environ, platform, probe)
    return environ, probe


@pytest.mark.parametrize(
    ("backend", "platform", "expected"),
    [
        ("auto", "linux", "vulkan"),
        ("vulkan", "linux", "vulkan"),
        ("vulkan", "win32", "vulkan"),
        ("opengl", "linux", "opengl"),
        ("opengl", "darwin", "opengl"),
    ],
)
def test_backend_sets_the_qt_quick_graphics_api(
    backend: str, platform: str, expected: str
) -> None:
    """A backend that names a graphics API selects it for Qt Quick.

    Args:
        backend: The configured graphics backend.
        platform: The ``sys.platform`` value to assume.
        expected: The resulting ``QSG_RHI_BACKEND``.
    """
    environ, _ = _apply(backend, platform)

    assert environ == {"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS, "QSG_RHI_BACKEND": expected}


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_auto_leaves_qt_its_own_choice_outside_linux(platform: str) -> None:
    """Outside Linux, auto changes nothing and doesn't probe for Vulkan.

    Args:
        platform: The ``sys.platform`` value to assume.
    """
    environ, probe = _apply("auto", platform)

    assert environ == {"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS}
    assert probe.calls == 0


def test_software_turns_off_the_gpu() -> None:
    """The software backend renders the page without the GPU."""
    environ, probe = _apply("software")

    assert environ == {"QTWEBENGINE_CHROMIUM_FLAGS": f"{FLAGS} --disable-gpu"}
    assert probe.calls == 0


@pytest.mark.parametrize("backend", ["auto", "vulkan"])
def test_unavailable_vulkan_falls_back_to_qts_choice(
    backend: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Without a working Vulkan driver, Qt picks the backend, and a warning says so.

    Args:
        backend: The configured graphics backend.
        caplog: Pytest log capture fixture.
    """
    with caplog.at_level(logging.WARNING, logger="vauxhall.dashboard.graphics"):
        environ, _ = _apply(backend, vulkan=False)

    assert environ == {"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS}
    assert "Vulkan is not available" in caplog.text
    assert "dashboard.graphics_backend" in caplog.text


@pytest.mark.parametrize("backend", ["auto", "vulkan", "opengl", "software"])
def test_users_own_qsg_rhi_backend_wins(backend: str) -> None:
    """A QSG_RHI_BACKEND the user set leaves the graphics setup to them.

    Args:
        backend: The configured graphics backend.
    """
    environ, probe = _apply(backend, rhi="opengl")

    assert environ == {"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS, "QSG_RHI_BACKEND": "opengl"}
    assert probe.calls == 0


class FakeVulkan:
    """Stand-in for the Vulkan loader library."""

    def __init__(self, *, create_result: int = 0, devices: int = 1) -> None:
        """Initialize the loader's answers.

        Args:
            create_result: The ``VkResult`` of ``vkCreateInstance``.
            devices: How many physical devices the instance reports.
        """
        self.create_result = create_result
        self.devices = devices
        self.destroyed = False

    def vkCreateInstance(self, info: object, _allocator: None, instance: object) -> int:  # noqa: N802
        """Check the request and hand out an instance handle.

        Args:
            info: Reference to the instance create info.
            _allocator: Allocation callbacks, unused.
            instance: Reference that receives the instance handle.

        Returns:
            The configured ``VkResult``.
        """
        assert info._obj.sType == 1
        instance._obj.value = 42
        return self.create_result

    def vkEnumeratePhysicalDevices(  # noqa: N802
        self, instance: ctypes.c_void_p, count: object, _devices: None
    ) -> int:
        """Report the configured number of physical devices.

        Args:
            instance: The instance handle.
            count: Reference that receives the device count.
            _devices: Device array, unused when only counting.

        Returns:
            ``VK_SUCCESS``.
        """
        assert instance.value == 42
        count._obj.value = self.devices
        return 0

    def vkDestroyInstance(self, instance: ctypes.c_void_p, _allocator: None) -> None:  # noqa: N802
        """Record that the instance was destroyed.

        Args:
            instance: The instance handle.
            _allocator: Allocation callbacks, unused.
        """
        assert instance.value == 42
        self.destroyed = True


def test_vulkan_available_creates_and_destroys_an_instance() -> None:
    """A loader that creates an instance with a device means Vulkan works."""
    library = FakeVulkan()

    assert vulkan_available(lambda _name: library)
    assert library.destroyed


def test_vulkan_available_without_a_device() -> None:
    """An instance without a physical device can't render, and is still destroyed."""
    library = FakeVulkan(devices=0)

    assert not vulkan_available(lambda _name: library)
    assert library.destroyed


def test_vulkan_available_when_no_driver_creates_an_instance() -> None:
    """A loader without a driver fails to create an instance."""
    library = FakeVulkan(create_result=-9)  # VK_ERROR_INCOMPATIBLE_DRIVER

    assert not vulkan_available(lambda _name: library)
    assert not library.destroyed


def test_vulkan_available_without_the_loader_library() -> None:
    """A missing Vulkan loader library means no Vulkan."""

    def missing(name: str) -> object:
        raise OSError(name)

    assert not vulkan_available(missing)
