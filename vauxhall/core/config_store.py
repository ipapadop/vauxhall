# SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
# SPDX-License-Identifier: MIT

"""Save per-user configuration files without changing how they are loaded."""

import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from vauxhall.core.config import ConfigurationError, find_config_file, load_config_data


@dataclass(frozen=True)
class FieldSource:
    """Where a configuration field's effective value comes from.

    Attributes:
        kind: Whether the value comes from the environment, a file, or the default.
        location: The environment variable name or absolute file path, if any.
        editable: Whether saving to the user file would change the value.
    """

    kind: Literal["environment", "file", "default"]
    location: str | None
    editable: bool


def user_config_path(filename: str) -> Path:
    """Return the per-user path that configuration is saved to."""
    return Path.home() / ".config" / "vauxhall" / filename


def field_sources(filename: str, config_type: type[Any]) -> dict[str, FieldSource]:
    """Report where each field of a configuration comes from.

    Args:
        filename: The configuration file name, such as "vauxhall_dashboard.json".
        config_type: The configuration dataclass loaded from that file.

    Returns:
        dict[str, FieldSource]: The source of each field, keyed by "section.key".

    Raises:
        ConfigurationError: If the loaded configuration file is malformed or a
            known section is not an object.
    """
    loaded_path = find_config_file(filename)
    data = load_config_data(loaded_path) if loaded_path else {}
    location = str(loaded_path.resolve()) if loaded_path else None
    # The loader reads only one file, so a file in the current directory hides
    # the user file entirely.
    editable = location in (None, str(user_config_path(filename).resolve()))

    sources = {}
    for section, values in asdict(config_type()).items():
        section_data = data.get(section, {})
        if not isinstance(section_data, dict):
            message = f"{location}: {section} must be an object, got {section_data!r}"
            raise ConfigurationError(message)
        for key in values:
            environment_variable = f"VAUXHALL_{section.upper()}_{key.upper()}"
            if environment_variable in os.environ:
                source = FieldSource(
                    "environment", environment_variable, editable=False
                )
            elif key in section_data:
                source = FieldSource("file", location, editable=editable)
            else:
                source = FieldSource("default", None, editable=editable)
            sources[f"{section}.{key}"] = source
    return sources


def save_user_config(
    filename: str,
    config_type: type[Any],
    changes: Mapping[str, Mapping[str, object]],
) -> Path:
    """Merge changes into the per-user configuration file.

    Values equal to their default are removed from the file; unknown sections
    and keys already in the file are kept. The merged file is validated with
    ``config_type.load`` before it atomically replaces the original, so an
    invalid change leaves the file untouched.

    Args:
        filename: The configuration file name, such as "vauxhall_dashboard.json".
        config_type: The configuration dataclass loaded from that file.
        changes: New values, grouped by section.

    Returns:
        Path: The saved file.

    Raises:
        ConfigurationError: If a field is unknown or not editable, the existing
            file is malformed, or the merged configuration is invalid.
    """
    path = user_config_path(filename)
    _check_editable(field_sources(filename, config_type), changes, path)

    defaults = asdict(config_type())
    data = load_config_data(path)
    # field_sources has already checked the sections of the file being saved.
    for section, values in changes.items():
        section_data = data.get(section, {})
        for key, value in values.items():
            default = defaults[section][key]
            if type(value) is type(default) and value == default:
                section_data.pop(key, None)
            else:
                section_data[key] = value
        if section_data:
            data[section] = section_data
        else:
            data.pop(section, None)

    _validate(config_type, data, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomically(path, data)
    return path


def _check_editable(
    sources: Mapping[str, FieldSource],
    changes: Mapping[str, Mapping[str, object]],
    path: Path,
) -> None:
    """Reject fields that are unknown or whose saved value would be ignored."""
    for section, values in changes.items():
        for key in values:
            source = sources.get(f"{section}.{key}")
            if source is None:
                message = f"Unknown configuration field: {section}.{key}"
                raise ConfigurationError(message)
            if not source.editable:
                reason = (
                    f"it is set by {source.location}"
                    if source.kind == "environment"
                    else "a configuration file in the current directory "
                    "takes precedence"
                )
                message = f"{section}.{key} cannot be saved to {path}: {reason}"
                raise ConfigurationError(message)


def _validate(config_type: type[Any], data: dict[str, Any], path: Path) -> None:
    """Load candidate data with the unchanged loader, reporting the real path."""
    with tempfile.TemporaryDirectory() as directory:
        candidate = Path(directory) / path.name
        candidate.write_text(json.dumps(data), encoding="utf-8")
        try:
            config_type.load(candidate)
        except ConfigurationError as error:
            message = str(error).replace(str(candidate.resolve()), str(path))
            raise ConfigurationError(message) from None


def _write_json_atomically(path: Path, data: dict[str, Any]) -> None:
    """Replace a JSON file so readers see either the old or the new content."""
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8") as file:
            json.dump(data, file, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        if path.exists():
            shutil.copymode(path, temporary_path)
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
