<!--
SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
SPDX-License-Identifier: MIT
-->

# Releases and Versioning

## Versioning policy

Vauxhall uses [Semantic Versioning](https://semver.org/) with
[PEP 440](https://peps.python.org/pep-0440/) spelling, and tags each release
`v<version>`, for example `v0.1.0` or `v0.2.0rc1`.

While the version is `0.x`:

- A **minor** release (`0.1.0` → `0.2.0`) may contain breaking changes. Each
  one is listed under **Changed** or **Removed** in the
  [changelog](../CHANGELOG.md), with what to do about it.
- A **patch** release (`0.1.0` → `0.1.1`) only fixes bugs and never breaks
  anything listed below.
- A version with a pre-release suffix (`a1`, `b1`, `rc1`, or `.dev1`) is
  published as a GitHub pre-release. A post-release (`0.1.0.post1`) is a
  normal release.

From `1.0.0` on, breaking changes need a major release.

### What counts as a breaking change

These are Vauxhall's public interfaces:

| Interface | Compatibility promise |
| --- | --- |
| Telemetry schema | A payload that validates today keeps validating until `schema_version` changes. A new schema version is announced in the changelog, and the dashboard keeps accepting the previous one for at least one minor release, so hooks and dashboards can be upgraded separately. |
| Commands | `vauxhall` and `vauxhall-hook-install`, with their arguments. |
| Configuration | The files, fields, environment variables, and defaults in [configuration.md](configuration.md). |
| Python API | `vauxhall.hooks.client.TelemetryClient`, `vauxhall.core.telemetry`, and `vauxhall.core.config_store`. Everything else is internal. |
| Hook registrations | The hook events and settings files the installers write, as listed in [integrations.md](integrations.md). |
| Python and operating systems | The versions in the [compatibility table](../README.md#compatibility). Dropping one needs a minor release. |

Vauxhall follows the documented hook formats of Claude Code, Codex, and Gemini
CLI. When an agent changes its format, a patch release adapts to it; that is a
fix, not a breaking change.

Releases go to GitHub only; Vauxhall isn't on PyPI yet, so install from a
GitHub release or tag, as shown in the [README](../README.md#installation).
For the release process itself, see [AGENTS.md](../AGENTS.md#releasing).
