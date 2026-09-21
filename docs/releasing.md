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

## Changelog

[CHANGELOG.md](../CHANGELOG.md) follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Every pull request
with a user-visible change adds a line under `## [Unreleased]`, in the
**Added**, **Changed**, **Deprecated**, **Removed**, **Fixed**, or
**Security** group. Links in an entry must be absolute URLs, such as
`https://github.com/ipapadop/vauxhall/blob/main/docs/privacy.md`, because the
entry becomes the GitHub release notes, where relative links don't resolve.

## Making a release

1. On a branch, set `version` in `pyproject.toml`, run `uv lock`, and rename
   `## [Unreleased]` in the changelog to `## [<version>] - <YYYY-MM-DD>`. Add
   a new, empty `## [Unreleased]` above it. In the entry, record the Claude
   Code, Codex, and Gemini CLI versions you checked the hooks with, following
   the [first run](../README.md#first-run) with each. Merge the pull request.
2. Tag the merge commit on `main` and push the tag:

   ```bash
   git switch main && git pull
   git tag -a v0.1.0 -m "Vauxhall 0.1.0"
   git push origin v0.1.0
   ```

3. The [release workflow](../.github/workflows/release.yml) then:
   1. runs the lint workflow and the whole CI workflow: Ruff, the Python
      suite on every supported Python and operating system, the coverage
      floors, the frontend suite, both test suites from the unpacked sdist,
      and the packaged dashboard on Linux, macOS, and Windows;
   2. checks that the tagged commit is on `main`, that the tag is `v` followed
      by the package version, and that the changelog has a dated, non-empty
      entry for it (`scripts/release_notes.py`);
   3. builds the sdist, and the wheel from that sdist, each in an isolated
      build environment, with timestamps taken from the tagged commit;
   4. runs `twine check --strict`, installs the wheel into a clean
      environment, and runs `vauxhall-hook-install --help` from it;
   5. creates a draft GitHub release with the wheel, the sdist, and a
      `SHA256SUMS` file, using the changelog entry as its notes, and then
      publishes it.

   If any step fails, nothing is published. A transient failure can be
   re-run from the Actions page; the last job reuses a draft release that an
   earlier attempt left behind. To change what is released instead, delete
   that draft if there is one (`gh release delete v0.1.0`), delete the tag
   (`git push --delete origin v0.1.0`; with the tag ruleset below, only an
   admin can), fix the problem, and tag again.

To check a download, run `sha256sum -c SHA256SUMS` in the directory that holds
the release files.

## Repository settings

Two settings protect published releases. They are configured on GitHub, not
in the repository:

- **Immutable releases** (*Settings → General → Releases*). Once a release is
  published, its files and tag can't be changed. The workflow attaches every
  file before publishing for this reason.
- **A tag ruleset** that blocks moving or deleting `v*` tags. Rulesets need
  a public repository or GitHub Pro (see issue #17). Once available, create it
  with:

  ```bash
  gh api repos/ipapadop/vauxhall/rulesets --method POST --input - <<'EOF'
  {
    "name": "Release tags",
    "target": "tag",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
    "rules": [{"type": "update"}, {"type": "deletion"}, {"type": "non_fast_forward"}],
    "bypass_actors": [
      {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
    ]
  }
  EOF
  ```

  Role `5` is the repository admin role. The rules block updating and
  deleting release tags for everyone else. Creating a tag isn't restricted:
  only people with write access can push tags at all.

## Not done yet: PyPI

Releases go to GitHub only. Publishing to PyPI is planned as a separate job
in the same workflow. It will use Trusted Publishing (OIDC) instead of an API
token, run in a protected `pypi` environment that needs a maintainer's
approval, and be rehearsed on TestPyPI before the first production upload.
Until then, install from a GitHub release or tag, as shown in the
[README](../README.md#installation).
