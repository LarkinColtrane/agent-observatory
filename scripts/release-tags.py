#!/usr/bin/env python3
"""Create annotated tags listed in docs/governance-state.yaml `pending_tags`.

Run only by .github/workflows/release-tags.yml on main (ADR-0005 §7).
Each entry: {tag: <name>, commit: <40-hex sha>, message: <text>}.
Never moves or deletes tags. Exit 0 = all requested tags present at the
requested commits; 1 = refused/failed.
"""
from __future__ import annotations

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
        if not isinstance(commit, str) or not SHA_RE.match(commit):
            problems.append(f"pending_tags[{i}]: commit must be a full 40-hex sha")
        if not isinstance(msg, str) or not msg.strip():
            problems.append(f"pending_tags[{i}]: message must be non-empty")
    return problems


def main() -> int:
    state = yaml.safe_load(Path("docs/governance-state.yaml").read_text(encoding="utf-8")) or {}
    entries = state.get("pending_tags")
    problems = validate(entries)
    if problems:
        for p in problems:
            print(f"::error::{p}")
        return 1
    git("fetch", "--tags", "--force", "origin")
    failed = False
    for e in entries or []:
        tag, commit, msg = e["tag"], e["commit"], e["message"]
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
        git("push", "origin", f"refs/tags/{tag}:refs/tags/{tag}")  # never --force
        peeled = git("ls-remote", "origin", f"refs/tags/{tag}^{{}}").stdout.split()
        if not peeled or peeled[0] != commit:
            print(f"::error::{tag}: remote verification failed")
            failed = True
        else:
            print(f"{tag}: created (annotated) -> {commit}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
