# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Tests for the release tag and changelog check."""

import importlib.metadata
from pathlib import Path

import pytest

from scripts.release_notes import (
    ReleaseError,
    check_tag,
    is_prerelease,
    main,
    release_notes,
)

CHANGELOG = """\
# Changelog

## [Unreleased]

### Added

- Something new.

## [0.2.0] - 2026-10-01

### Fixed

- A bug.

## [0.1.0] - 2026-09-21

### Added

- The first release.

[Unreleased]: https://github.com/ipapadop/vauxhall/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ipapadop/vauxhall/compare/v0.1.0...v0.2.0
"""


def test_release_notes_returns_only_the_requested_entry() -> None:
    """An entry ends at the next heading."""
    assert release_notes(CHANGELOG, "0.2.0") == "### Fixed\n\n- A bug."


def test_release_notes_stop_at_link_references() -> None:
    """The last entry does not swallow the link reference definitions."""
    assert release_notes(CHANGELOG, "0.1.0") == "### Added\n\n- The first release."


def test_release_notes_keep_body_lines_that_start_with_a_link() -> None:
    """Only a link reference definition ends an entry, not an inline link."""
    changelog = (
        "## [0.1.0] - 2026-09-21\n\n"
        "The first release; see\n"
        "[known limitations](https://example.com/limits).\n\n"
        "### Added\n\n- Everything.\n\n"
        "[0.1.0]: https://github.com/ipapadop/vauxhall/releases/tag/v0.1.0\n"
    )

    assert release_notes(changelog, "0.1.0") == (
        "The first release; see\n"
        "[known limitations](https://example.com/limits).\n\n"
        "### Added\n\n- Everything."
    )


@pytest.mark.parametrize("version", ["1.0.0a1", "1.0.0b2", "1.0.0rc1", "1.0.0.dev3"])
def test_is_prerelease_flags_pre_release_segments(version: str) -> None:
    """Alpha, beta, release candidate, and development versions are pre-releases.

    Args:
        version: Version to classify.
    """
    assert is_prerelease(version)


@pytest.mark.parametrize("version", ["0.1.0", "0.1.0.post1"])
def test_is_prerelease_treats_final_and_post_releases_as_final(version: str) -> None:
    """A post release is a final release despite its letters.

    Args:
        version: Version to classify.
    """
    assert not is_prerelease(version)


@pytest.mark.parametrize(
    ("changelog", "message"),
    [
        (CHANGELOG, "no entry for 0.3.0"),
        ("## [0.3.0]\n\n- Undated.\n", "no YYYY-MM-DD date"),
        ("## [0.3.0] - soon\n\n- Misdated.\n", "no YYYY-MM-DD date"),
        ("## [0.3.0] - 2026-10-02\n\n## [0.2.0] - 2026-10-01\n", "is empty"),
    ],
)
def test_release_notes_reject_unready_entries(changelog: str, message: str) -> None:
    """A release needs a dated, non-empty entry.

    Args:
        changelog: Changelog text.
        message: Expected part of the error.
    """
    with pytest.raises(ReleaseError, match=message):
        release_notes(changelog, "0.3.0")


def test_check_tag_accepts_only_the_package_version() -> None:
    """The tag must be ``v`` followed by the exact version."""
    check_tag("v1.2.3", "1.2.3")
    for tag in ("1.2.3", "v1.2.4", "v1.2.3rc1"):
        with pytest.raises(ReleaseError, match="does not match"):
            check_tag(tag, "1.2.3")


def test_main_writes_notes_for_the_installed_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command checks the tag against the installed package.

    Args:
        tmp_path: Pytest temporary directory.
        monkeypatch: Pytest fixture that points ``GITHUB_OUTPUT`` at a file.
    """
    github_output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    version = importlib.metadata.version("vauxhall")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(f"## [{version}] - 2026-09-21\n\n- Notes.\n")
    output = tmp_path / "notes.md"

    status = main(
        [f"v{version}", "--changelog", str(changelog), "--output", str(output)]
    )

    assert status == 0
    assert output.read_text() == "- Notes.\n"
    expected = str(is_prerelease(version)).lower()
    assert github_output.read_text() == f"prerelease={expected}\n"


def test_main_writes_no_output_outside_github_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without ``GITHUB_OUTPUT`` the command only writes the notes.

    Args:
        tmp_path: Pytest temporary directory.
        monkeypatch: Pytest fixture that removes ``GITHUB_OUTPUT``.
    """
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.chdir(tmp_path)
    version = importlib.metadata.version("vauxhall")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(f"## [{version}] - 2026-09-21\n\n- Notes.\n")

    status = main(
        [f"v{version}", "--changelog", str(changelog), "--output", "notes.md"]
    )

    assert status == 0
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "CHANGELOG.md",
        "notes.md",
    ]


def test_main_reports_a_mismatched_tag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failed check exits non-zero, explains why, and writes nothing.

    Args:
        tmp_path: Pytest temporary directory.
        capsys: Pytest output capture.
    """
    output = tmp_path / "notes.md"

    status = main(["v0.0.0-not-a-release", "--output", str(output)])

    assert status == 1
    assert "does not match the package version" in capsys.readouterr().err
    assert not output.exists()
