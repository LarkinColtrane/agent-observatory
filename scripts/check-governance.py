#!/usr/bin/env python3
"""Phase 0 governance check for agent-observatory.

Verifies the governance baseline is complete and well-formed:
required files exist, YAML registers parse and have required fields,
relative Markdown links resolve, and no likely secrets are committed.

Exit code 0 = pass, 1 = fail. Stdlib + PyYAML only.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

REQUIRED = [
    "development-operating-contract.md",
    "agent-task-contract.md",
    "agent-handoff-contract.md",
    "review-checklist.md",
    "parallel-work-policy.md",
    "phase-quality-gates.md",
    "rollback-policy.md",
    "security-baseline.md",
    "agent-efficiency.md",
    "component-ownership.md",
    "assumptions.yaml",
    "technical-debt.yaml",
    "adr/README.md",
    "adr/0000-template.md",
]

REGISTERS = {
    "assumptions.yaml": (
        "assumptions",
        {"id", "statement", "confidence", "status", "owner", "affects", "validation_plan"},
        {"open", "validated", "invalidated"},
    ),
    "technical-debt.yaml": (
        "debt",
        {"id", "title", "severity", "status", "owner", "repayment_trigger"},
        {"open", "scheduled", "repaid", "accepted"},
    ),
}

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{32,}"),
    re.compile(r"xox[abpr]-[A-Za-z0-9-]{10,}"),
]

LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+)(?:#[^)]*)?\)")


def check_required(errors: list[str]) -> None:
    for rel in REQUIRED:
        if not (DOCS / rel).is_file():
            errors.append(f"missing required file: docs/{rel}")


def check_registers(errors: list[str]) -> None:
    for name, (key, fields, statuses) in REGISTERS.items():
        path = DOCS / name
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            errors.append(f"docs/{name}: invalid YAML: {exc}")
            continue
        entries = (data or {}).get(key)
        if not isinstance(entries, list):
            errors.append(f"docs/{name}: top-level '{key}' must be a list")
            continue
        seen: set[str] = set()
        for i, entry in enumerate(entries):
            missing = fields - set(entry or {})
            if missing:
                errors.append(f"docs/{name}[{i}]: missing fields {sorted(missing)}")
            eid = (entry or {}).get("id")
            if eid in seen:
                errors.append(f"docs/{name}: duplicate id {eid}")
            seen.add(eid)
            if (entry or {}).get("status") not in statuses:
                errors.append(f"docs/{name}[{eid}]: invalid status")


def check_links(errors: list[str]) -> None:
    for md in DOCS.rglob("*.md"):
        for target in LINK.findall(md.read_text()):
            if "://" in target or target.startswith("mailto:"):
                continue
            if not (md.parent / target).exists():
                errors.append(f"{md.relative_to(ROOT)}: broken link -> {target}")


def check_secrets(errors: list[str]) -> None:
    files = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    for rel in files:
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                # Report location only; never echo the matched value.
                errors.append(f"{rel}: possible secret matching /{pat.pattern[:12]}.../")


def main() -> int:
    errors: list[str] = []
    for check in (check_required, check_registers, check_links, check_secrets):
        before = len(errors)
        check(errors)
        print(f"{check.__name__}: {'ok' if len(errors) == before else 'FAIL'}")
    if errors:
        print("\nFAIL")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
