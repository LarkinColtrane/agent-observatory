#!/usr/bin/env python3
"""Cross-check TD-004 against GitHub's actual protection of `main` (review B-25).

If docs/technical-debt.yaml records TD-004 as repaid, `main` must report
`protected: true` with the `governance` status check required. Otherwise the
register is lying and this check fails. While TD-004 is open, the current
state is printed for information only.

Reads only GET /repos/{repo}/branches/main, which needs no Administration
permission. Uses GITHUB_TOKEN if set (CI) and GITHUB_REPOSITORY (default
LarkinColtrane/agent-observatory). Never prints the token.
Exit 0 = consistent, 1 = inconsistent or unverifiable, 2 = usage error.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    print("check-repo-protection: PyYAML is required", file=sys.stderr)
    sys.exit(2)

REQUIRED_CHECK = "governance"
REPAID = {"repaid"}


# Ruleset rule types that make a branch protected (GET /rules/branches/{branch}).
PROTECTING_RULES = {"pull_request", "non_fast_forward", "deletion", "required_status_checks"}


def required_checks(branch: dict[str, Any], rules: list[dict[str, Any]] | None = None) -> set[str]:
    """Required check names from classic protection and/or ruleset rules
    (review N-B: ruleset checks may not appear in the branch payload)."""
    rsc = (branch.get("protection") or {}).get("required_status_checks") or {}
    names = set(rsc.get("contexts") or [])
    names |= {c.get("context") for c in rsc.get("checks") or [] if isinstance(c, dict)}
    for rule in rules or []:
        if isinstance(rule, dict) and rule.get("type") == "required_status_checks":
            params = rule.get("parameters") or {}
            names |= {c.get("context") for c in params.get("required_status_checks") or [] if isinstance(c, dict)}
    return {n for n in names if n}


def is_protected(branch: dict[str, Any], rules: list[dict[str, Any]] | None = None) -> bool:
    return branch.get("protected") is True or any(
        isinstance(r, dict) and r.get("type") in PROTECTING_RULES for r in rules or []
    )


def evaluate(td004_status: str | None, branch: dict[str, Any], rules: list[dict[str, Any]] | None = None) -> list[str]:
    """Return problems; empty means consistent."""
    if td004_status not in REPAID:
        return []
    problems = []
    if not is_protected(branch, rules):
        problems.append("TD-004 is recorded as repaid but main is not protected")
    if REQUIRED_CHECK not in required_checks(branch, rules):
        problems.append(f"TD-004 is recorded as repaid but '{REQUIRED_CHECK}' is not a required check on main")
    return problems


def td004_status(root: Path) -> str | None:
    data = yaml.safe_load((root / "docs/technical-debt.yaml").read_text(encoding="utf-8")) or {}
    for entry in data.get("debt") or []:
        if isinstance(entry, dict) and entry.get("id") == "TD-004":
            return entry.get("status")
    return None


def _get(path: str) -> Any:
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    if not api.startswith("https://"):
        raise ValueError("GITHUB_API_URL must be an https:// URL")
    req = urllib.request.Request(f"{api}{path}", headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=20) as resp:  # nosec B310 - scheme validated as https above
        return json.load(resp)


def fetch_branch(repo: str) -> dict[str, Any]:
    return _get(f"/repos/{repo}/branches/main")


def fetch_rules(repo: str) -> list[dict[str, Any]] | None:
    """Ruleset rules for main, or None when this token cannot read them."""
    try:
        rules = _get(f"/repos/{repo}/rules/branches/main")
    except urllib.error.HTTPError:
        return None
    return rules if isinstance(rules, list) else None


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    repo = os.environ.get("GITHUB_REPOSITORY", "LarkinColtrane/agent-observatory")
    status = td004_status(root)
    try:
        branch = fetch_branch(repo)
        rules = fetch_rules(repo)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        if status in REPAID:
            print(f"check-repo-protection: FAIL — cannot read protection state ({type(exc).__name__})")
            return 1
        print(f"check-repo-protection: TD-004 {status}; protection state unreadable ({type(exc).__name__}) — informational")
        return 0
    problems = evaluate(status, branch, rules)
    print(
        f"check-repo-protection: TD-004={status}; main protected={is_protected(branch, rules)}; "
        f"required checks={sorted(required_checks(branch, rules))}; "
        f"rules endpoint={'unreadable' if rules is None else f'{len(rules)} rule(s)'}"
    )
    for p in problems:
        print(f"  - {p}")
    print("FAIL" if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
