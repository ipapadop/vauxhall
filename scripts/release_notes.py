# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Check a release tag and extract its notes from the changelog.

The release workflow runs this before building, so a tag that does not match
the package version, or a version without a dated changelog entry, stops the
release before anything is published.
"""

import argparse
import importlib.metadata
import re
import sys
from pathlib import Path

HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\](?: - (?P<date>.+))?$")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class ReleaseError(Exception):
    """The tag, version, or changelog is not ready for a release."""


def release_notes(changelog: str, version: str) -> str:
    """Return the changelog entry for a released version.

    Args:
        changelog: Text of ``CHANGELOG.md``.
        version: The version being released, without a leading ``v``.

    Returns:
        The entry's body, without its heading or surrounding blank lines.

    Raises:
        ReleaseError: If the entry is missing, undated, or empty.
    """
    lines = changelog.splitlines()
    start = None
    for index, line in enumerate(lines):
        match = HEADING.match(line)
        if start is not None and (match or line.startswith("[")):
            end = index
            break
        if match and match["version"] == version:
            if not match["date"] or not DATE.fullmatch(match["date"]):
                msg = f"The changelog entry for {version} has no YYYY-MM-DD date"
                raise ReleaseError(msg)
            start = index + 1
    else:
        end = len(lines)
    if start is None:
        msg = f"The changelog has no entry for {version}"
        raise ReleaseError(msg)
    notes = "\n".join(lines[start:end]).strip()
    if not notes:
        msg = f"The changelog entry for {version} is empty"
        raise ReleaseError(msg)
    return notes


def check_tag(tag: str, version: str) -> None:
    """Check that a release tag names the package version.

    Args:
        tag: The pushed Git tag, such as ``v0.1.0``.
        version: The version in the package metadata.

    Raises:
        ReleaseError: If the tag is not ``v`` followed by the version.
    """
    if tag != f"v{version}":
        msg = f"Tag {tag} does not match the package version {version}"
        raise ReleaseError(msg)


def main(argv: list[str] | None = None) -> int:
    """Check a release tag and write its notes.

    Args:
        argv: Command-line arguments, without the program name.

    Returns:
        The process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tag", help="the release tag, such as v0.1.0")
    parser.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    version = importlib.metadata.version("vauxhall")
    try:
        check_tag(args.tag, version)
        notes = release_notes(args.changelog.read_text(encoding="utf-8"), version)
    except ReleaseError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    args.output.write_text(notes + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
