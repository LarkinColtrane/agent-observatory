#!/usr/bin/env python3
"""Create annotated tags listed in docs/governance-state.yaml `pending_tags`.

Run only by .github/workflows/release-tags.yml on main (ADR-0005 §7).
Each entry: {tag: <name>, commit: <40-hex sha> | self, message: <text>}.
`self` resolves to the commit that first added the tag name to
docs/governance-state.yaml, so it is stable across later pushes.
The push token is read from GH_TOKEN and used only for `git push`.
Never moves or deletes tags. Exit 0 = all requested tags present at the
requested commits; 1 = refused/failed.
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

TAG_RE = re.compile(r"^(phase-P[0-9]+|contract-[a-z0-9-]+)-v[0-9]+\.[0-9]+\.[0-9]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check)


def validate(entries: object) -> list[str]:
    """Return problems with the pending_tags list (pure; unit-tested)."""
    if entries is None:
        return []
    if not isinstance(entries, list):
        return ["pending_tags must be a list"]
    problems = []
    seen: set[str] = set()
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            problems.append(f"pending_tags[{i}] must be a mapping")
            continue
        tag, commit, msg = e.get("tag"), e.get("commit"), e.get("message")
        if not isinstance(tag, str) or not TAG_RE.match(tag):
            problems.append(f"pending_tags[{i}]: invalid tag name {tag!r}")
        elif tag in seen:
            problems.append(f"pending_tags[{i}]: duplicate tag {tag}")
        else:
            seen.add(tag)
        if not isinstance(commit, str) or not (commit == "self" or SHA_RE.match(commit)):
            problems.append(f"pending_tags[{i}]: commit must be a full 40-hex sha or 'self'")
        if not isinstance(msg, str) or not msg.strip():
            problems.append(f"pending_tags[{i}]: message must be non-empty")
    return problems


def resolve_self(tag: str) -> str | None:
    """First commit on main that added `tag` to the governance state file."""
    out = git("log", "--format=%H", "--reverse", "-S", tag, "origin/main", "--",
              "docs/governance-state.yaml").stdout.split()
    return out[0] if out else None


def main() -> int:
    state = yaml.safe_load(Path("docs/governance-state.yaml").read_text(encoding="utf-8")) or {}
    entries = state.get("pending_tags")
    problems = validate(entries)
    if problems:
        for p in problems:
            print(f"::error::{p}")
        return 1
    token = os.environ.get("GH_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if entries and (not token or not re.fullmatch(r"[\w.-]+/[\w.-]+", repo)):
        print("::error::GH_TOKEN and GITHUB_REPOSITORY are required to push tags")
        return 1
    # Basic auth header (as actions/checkout does); never put the token in a URL.
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    push_auth = ("-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {basic}")
    push_url = f"https://github.com/{repo}.git"
    git("fetch", "--tags", "origin")
    failed = False
    for e in entries or []:
        tag, commit, msg = e["tag"], e["commit"], e["message"]
        if commit == "self":
            resolved = resolve_self(tag)
            if resolved is None:
                print(f"::error::{tag}: could not resolve 'self' from history")
                failed = True
                continue
            commit = resolved
        existing = git("rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}", check=False).stdout.strip()
        if existing:
            if existing == commit:
                print(f"{tag}: already present at {commit} — nothing to do")
            else:
                print(f"::error::{tag} exists at {existing}, not {commit}; tags are never moved")
                failed = True
            continue
        if git("cat-file", "-t", commit, check=False).stdout.strip() != "commit":
            print(f"::error::{tag}: {commit} is not a commit in this repository")
            failed = True
            continue
        if git("merge-base", "--is-ancestor", commit, "origin/main", check=False).returncode != 0:
            print(f"::error::{tag}: {commit} is not on main")
            failed = True
            continue
        git("-c", "user.name=github-actions[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "tag", "-a", tag, commit, "-m", msg)
        # Never --force. The credential exists only in this command's -c argument.
        if git(*push_auth, "push", push_url, f"refs/tags/{tag}:refs/tags/{tag}", check=False).returncode != 0:
            print(f"::error::{tag}: push refused")
            failed = True
            continue
        peeled = git("ls-remote", "origin", f"refs/tags/{tag}^{{}}").stdout.split()
        if not peeled or peeled[0] != commit:
            print(f"::error::{tag}: remote verification failed")
            failed = True
        else:
            print(f"{tag}: created (annotated) -> {commit}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
