<!--
SPDX-FileCopyrightText: 2026 Yiannis Papadopoulos <2738325+ipapadop@users.noreply.github.com>
SPDX-License-Identifier: MIT
-->

# Repository History

This note records the decisions taken before Vauxhall's repository was made
public, so that the state of the history is deliberate and reviewable rather
than something a future contributor has to reconstruct. It covers issue #18.

## The public contact address

`2738325+ipapadop@users.noreply.github.com` is the only address that should
appear anywhere in this repository. It is GitHub's no-reply address for the
maintainer's account, so it identifies the author without publishing a personal
mailbox.

It is used in three places, and all three must agree:

- The SPDX `FileCopyrightText` header at the top of every source file.
- The `authors` and `maintainers` fields in `pyproject.toml`, which become the
  published package metadata.
- The author and committer of every commit, set through `user.email`.

Commit metadata has used a GitHub no-reply address from the first commit. The
file contents did not: an earlier version of the project carried the
maintainer's personal Gmail address in the SPDX headers and in the package
metadata. That was not intended to be permanent, and it was replaced before the
repository became public.

## The history rewrite

The personal address was not only in the working tree; it was in the SPDX
header of nearly every file in nearly every commit. Removing it in a new commit
would have left it readable in the history, and the history would have been
published along with the code.

**The history was therefore rewritten**, replacing the personal address with
the no-reply address in the contents of every file that carried it. The rewrite
changed nothing else: comparing the pre-rewrite tip with its rewritten
counterpart shows 78 files changed, 82 insertions and 82 deletions, every one
of them that address. Commit metadata was already correct and was not touched.

This was done deliberately, once, for that reason. It is the intentional
rewrite that issue #18 asked to be documented.

This is the only rewrite the project has performed. Vauxhall does not squash or
rewrite history as routine cleanup: the commit history is the project's record
of how it was built, and a rewrite invalidates every existing clone, fork, and
commit reference. Any future rewrite needs the same kind of reason and the same
kind of note as this one.

### What the rewrite left behind

`git filter-branch` writes a backup of the pre-rewrite history to
`refs/original/refs/heads/main` in the clone where it ran. That ref still
exists in the maintainer's local clone. It is intentional, and it is safe:

- It is a local ref. It was never pushed, and `git push` does not push it.
- It is not reachable from `main`, so the pre-rewrite blobs are not part of
  anything the remote serves.

It is kept as a recovery option. It can be discarded at any time with
`git update-ref -d refs/original/refs/heads/main`, followed by expiring the
reflog and running `git gc --prune=now`. Doing so is irreversible, and the
pre-rewrite history would no longer exist anywhere.

## The audit

The following was verified on the rewritten history before publication. The
`secrets` job in [`.github/workflows/security.yml`](../.github/workflows/security.yml)
keeps the first check current; the rest are one-time reviews that should be
repeated if the history is ever rewritten again.

| Check | Result |
| :--- | :--- |
| `gitleaks` over every commit on every ref | No findings. |
| Personal address in any tree reachable from `main` | None. |
| Author and committer of every commit | Only no-reply addresses. |
| Largest blobs in the object database | `uv.lock`, `package-lock.json`, and `AGENTS.md`. All expected. |
| Refs on the remote | Only `main`. The merged topic branches were deleted. |

To repeat the scan locally, with `gitleaks` on your `PATH`:

```bash
gitleaks git . --log-opts="--all" --redact
```

To check that no reachable commit contains the personal address:

```bash
git grep -I -l "<the address>" $(git rev-list --all)
```

## Draft planning artifacts

`docs/superpowers` held a draft plan and specification for work that had
already shipped. Unchecked plans for finished work are misleading to read, so
the directory was removed rather than published. Design documents and
implementation plans are not committed to this repository.
