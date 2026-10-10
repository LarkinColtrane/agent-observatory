#!/usr/bin/env python3
"""Governance check for agent-observatory.

Validates the governance baseline and its *state*, not just file presence:

  required_files   required governance documents and ADRs exist
  registers        assumptions/debt YAML: structure, enums, unique ids,
                   cross-references to components and phases
  state            governance-state.yaml: canonical phase order, status
                   transitions, phase blockers vs debt register, gate reports,
                   contract freeze rules, event-protocol deferral, path claims
  adrs             ADR index <-> files, status lines, Related ids resolve
  links            relative Markdown links (inline, reference, autolink)
                   resolve inside the repository; index covers required docs
  secret_patterns  fast pattern backstop over working tree, index and all
                   reachable history blobs (NOT a substitute for
                   scripts/secret-scan.sh, which runs gitleaks)

Never prints matched secret values. Exit 0 = pass, 1 = fail, 2 = usage error.
Run with:  python3 -I scripts/check-governance.py [--root PATH]
Requires PyYAML (pinned in requirements-governance.txt).
"""
from __future__ import annotations

import argparse
import posixpath
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

try:
    import yaml
except ImportError:  # pragma: no cover - environment problem, not a finding
    print("check-governance: PyYAML is required (pip install -r requirements-governance.txt)", file=sys.stderr)
    sys.exit(2)

REQUIRED_DOCS = [
    "README.md",
    "development-operating-contract.md",
    "agent-task-contract.md",
    "agent-handoff-contract.md",
    "review-checklist.md",
    "parallel-work-policy.md",
    "phase-quality-gates.md",
    "rollback-policy.md",
    "security-baseline.md",
    "security-incident-log.md",
    "agent-efficiency.md",
    "component-ownership.md",
    "roadmap.md",
    "assumptions.yaml",
    "technical-debt.yaml",
    "governance-state.yaml",
    "adr/README.md",
    "adr/0000-template.md",
    "adr/0001-adopt-development-operating-system.md",
    "adr/0002-phase-1-technology-stack.md",
    "adr/0003-phase-order-and-event-protocol-deferral.md",
    "adr/0004-dedicated-private-repository.md",
]

# Canonical phase order (ADR-0003). Changing it requires a reviewed change here.
CANONICAL_PHASES = [
    ("P0", "Governance"),
    ("P1", "Engineering foundation"),
    ("P2", "Universal agent event protocol"),
    ("P3", "Adapter / SDK layer"),
    ("P4", "Agent state engine"),
    ("P5", "Realtime observability"),
    ("P6", "Operations dashboard"),
    ("P7", "Analytics / scorecards"),
    ("P8", "2D virtual office"),
    ("P9", "External integrations"),
    ("P10", "Control room / workflow graph"),
    ("P11", "Production hardening"),
]
PHASE_IDS = [p for p, _ in CANONICAL_PHASES]
PHASE_STATUSES = ["not_started", "in_progress", "gate_review", "closed"]
CONTRACT_STATUSES = {"not_drafted", "draft", "in_review", "approved", "frozen", "deprecated"}
# Contracts that must exist and may not be drafted before a phase (ADR-0003).
# Hard-coded so a one-line YAML edit cannot lift the deferral (review B-17).
DEFERRED_CONTRACTS = {"event-protocol": "P2"}
APPROVING = {"APPROVE", "APPROVE_WITH_NOTES"}
VERDICT = re.compile(
    r"^- \*\*(Reviewer [AB]) final outcome:\*\*\s*(APPROVE_WITH_NOTES|APPROVE|REQUEST_CHANGES|BLOCK)\b",
    re.MULTILINE,
)
VERDICT_MARKER = "<!-- final-verdicts -->"
REVIEWER_KEYS = {"Reviewer A": "reviewer-a", "Reviewer B": "reviewer-b"}
PENDING_TAG = re.compile(r"^(?:phase-(P\d+)|contract-([a-z0-9-]+?))-v(\d+\.\d+\.\d+)$")
PENDING_SHA = re.compile(r"^(?:[0-9a-f]{40}|self)$")
CLAIM_TASK = re.compile(r"^AO-(P\d+)-\d{3}$")
GLOB_CHARS = set("*?[]{}")
REQUIRED_FREEZE_REVIEWERS = {"reviewer-a", "reviewer-b"}
GATE_ITEMS = set(range(1, 13))
GATE_RESULTS = {"yes": {"pass", "fail"}, "no": {"not_run", "not_applicable"}}
ADR_STATUSES = ("proposed", "accepted", "superseded", "deprecated")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

REGISTERS: dict[str, dict[str, Any]] = {
    "assumptions.yaml": {
        "key": "assumptions",
        "id": re.compile(r"^A-\d{3}$"),
        "text": ["statement", "owner", "validation_plan"],
        "enums": {"confidence": {"low", "medium", "high"}, "status": {"open", "validated", "invalidated"}},
    },
    "technical-debt.yaml": {
        "key": "debt",
        "id": re.compile(r"^TD-\d{3}$"),
        "text": ["title", "description", "owner", "repayment_trigger"],
        "enums": {
            "severity": {"low", "medium", "high", "critical"},
            "status": {"open", "scheduled", "repaid", "accepted"},
        },
    },
}

SECRET_PATTERNS = {
    "aws-access-key-id": re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "private-key-block": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "github-token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "github-fine-grained-pat": re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    "openai-or-anthropic-style-key": re.compile(rb"\bsk-(?:ant-)?[A-Za-z0-9_-]{32,}"),
    "slack-token": re.compile(rb"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "slack-webhook": re.compile(rb"https://hooks\.slack\.com/services/[A-Za-z0-9/]{20,}"),
    "google-api-key": re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b"),
    "jwt": re.compile(rb"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "credentialed-url": re.compile(rb"\b[a-z][a-z0-9+.-]*://[^\s:/@'\"<>]*:[^\s@/'\"<>]{2,}@[^\s'\"<>]+"),
    "aws-secret-access-key": re.compile(rb"(?i)aws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}"),
    "generic-secret-assignment": re.compile(
        rb"(?i)\b[a-z0-9_]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key)\b\s*[:=]\s*['\"]?"
        rb"(?![<$({\[]|example|placeholder|changeme|redacted|xxx|\*\*\*|none|null|true|false)"
        # Not a literal: a call/attribute expression such as os.environ.get("X").
        rb"(?![A-Za-z_][\w.]*\()"
        rb"[A-Za-z0-9/+_.=!@#%^&*-]{8,}"
    ),
}
MAX_BLOB = 5 * 1024 * 1024

INLINE_LINK = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+.*)?$", re.MULTILINE)
AUTOLINK = re.compile(r"<([^<>\s:]+\.(?:md|ya?ml|py|sh))>")
FENCE = re.compile(r"^(```|~~~).*?^\1", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]+`")
GATE_ROW = re.compile(r"^\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|\s*([A-Za-z_]+)\s*\|\s*([A-Za-z_]+)\s*\|([^|]*)\|\s*$", re.MULTILINE)
ID_REF = re.compile(r"\b(A-\d{3}|TD-\d{3}|ADR-\d{4})\b")


class Ctx:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.docs = root / "docs"
        self.errors: list[str] = []
        self.info: list[str] = []
        self.cache: dict[str, Any] = {}

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def load_yaml(self, rel: str) -> Any:
        """Load docs/<rel> once. Returns None (and records an error) on failure."""
        if rel in self.cache:
            return self.cache[rel]
        path = self.docs / rel
        data = None
        if path.is_file():
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
            except yaml.YAMLError as exc:
                mark = getattr(exc, "problem_mark", None)
                where = f" (line {mark.line + 1})" if mark else ""
                self.err(f"docs/{rel}: invalid YAML{where}")
            else:
                if not isinstance(data, dict):
                    self.err(f"docs/{rel}: top level must be a mapping")
                    data = None
        self.cache[rel] = data
        return data


def _text(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _entries(ctx: Ctx, rel: str, key: str) -> list[dict[str, Any]]:
    data = ctx.load_yaml(rel)
    if data is None:
        return []
    entries = data.get(key)
    if not isinstance(entries, list) or not entries:
        ctx.err(f"docs/{rel}: '{key}' must be a non-empty list")
        return []
    good = []
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            ctx.err(f"docs/{rel}: {key}[{i}] must be a mapping")
        else:
            good.append(e)
    return good


# ---------------------------------------------------------------- checks


def check_required_files(ctx: Ctx) -> None:
    for rel in REQUIRED_DOCS:
        if not (ctx.docs / rel).is_file():
            ctx.err(f"missing required file: docs/{rel}")


def _component_ids(ctx: Ctx) -> set[str]:
    state = ctx.load_yaml("governance-state.yaml") or {}
    comps = state.get("components")
    if not isinstance(comps, list):
        return set()
    return {c["id"] for c in comps if isinstance(c, dict) and isinstance(c.get("id"), str)}


def check_registers(ctx: Ctx) -> None:
    components = _component_ids(ctx)
    counts = []
    for rel, spec in REGISTERS.items():
        entries = _entries(ctx, rel, spec["key"])
        seen: set[str] = set()
        for i, e in enumerate(entries):
            eid = e.get("id")
            label = f"docs/{rel}[{eid if isinstance(eid, str) else i}]"
            if not isinstance(eid, str) or not spec["id"].match(eid):
                ctx.err(f"{label}: id missing or malformed")
            elif eid in seen:
                ctx.err(f"docs/{rel}: duplicate id {eid}")
            else:
                seen.add(eid)
            for field in spec["text"]:
                if not _text(e.get(field)):
                    ctx.err(f"{label}: '{field}' must be non-empty text")
            for field, allowed in spec["enums"].items():
                if e.get(field) not in allowed:
                    ctx.err(f"{label}: '{field}' must be one of {sorted(allowed)}")
            refs = e.get("affects") if rel == "assumptions.yaml" else [e.get("component")]
            if not isinstance(refs, list) or not refs:
                ctx.err(f"{label}: component reference(s) missing")
            else:
                for ref in refs:
                    if ref != "all" and ref not in components:
                        ctx.err(f"{label}: unknown component '{ref}'")
            if rel == "assumptions.yaml":
                if e.get("review_phase") not in PHASE_IDS:
                    ctx.err(f"{label}: 'review_phase' must be a phase id")
            else:
                blocks = e.get("blocks")
                if not isinstance(blocks, list) or any(b not in PHASE_IDS for b in blocks):
                    ctx.err(f"{label}: 'blocks' must be a list of phase ids")
        counts.append(f"{spec['key']}={len(entries)}")
    debt = _entries_quiet(ctx, "technical-debt.yaml", "debt")
    open_debt = sum(1 for d in debt if d.get("status") in {"open", "scheduled"})
    ctx.info.append(f"register counts: {', '.join(counts)} (open debt={open_debt})")


def _entries_quiet(ctx: Ctx, rel: str, key: str) -> list[dict[str, Any]]:
    data = ctx.load_yaml(rel) or {}
    entries = data.get(key)
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def _annotated_tag_exists(ctx: Ctx, tag: str) -> bool:
    try:
        kind = subprocess.run(
            ["git", "-C", str(ctx.root), "cat-file", "-t", f"refs/tags/{tag}"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return kind == "tag"


def _approved_by_both(ctx: Ctx, record: Any) -> str | None:
    """Return None if `record` holds approving final verdicts from both reviewers,
    else a reason. The last recorded verdict per reviewer wins."""
    # Consistency check, not authenticity: who wrote a verdict line is
    # enforced by CODEOWNERS + branch protection (TD-004, TD-007).
    if not _text(record):
        return "review_record missing"
    reviews_dir = (ctx.docs / "reviews").resolve()
    path = (ctx.root / record).resolve()
    if reviews_dir not in path.parents or not path.is_file():
        return f"review_record '{record}' must be an existing file under docs/reviews/"
    text = path.read_text(encoding="utf-8", errors="replace")
    if VERDICT_MARKER not in text:
        return f"review_record '{record}' has no '{VERDICT_MARKER}' section"
    section = text.split(VERDICT_MARKER, 1)[1]
    section = FENCE.sub("", re.sub(r"<!--.*?-->", "", section, flags=re.DOTALL))
    latest: dict[str, str] = {}
    for who, outcome in VERDICT.findall(section):
        latest[REVIEWER_KEYS[who]] = outcome
    missing = sorted(REQUIRED_FREEZE_REVIEWERS - latest.keys())
    if missing:
        return f"no recorded final verdict from {missing} in {record}"
    rejected = sorted(f"{k}={v}" for k, v in latest.items() if v not in APPROVING)
    if rejected:
        return f"latest verdicts are not approvals: {rejected}"
    return None


def _parse_gate_report(ctx: Ctx, rel: str) -> dict[int, tuple[str, str]] | None:
    path = ctx.root / rel
    if not path.is_file():
        ctx.err(f"{rel}: gate report missing")
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    # Only the current run counts; superseded runs are kept below this heading.
    parts = re.split(r"^#+\s*Superseded runs", text, flags=re.MULTILINE | re.IGNORECASE)
    if len(parts) > 2:
        ctx.err(f"{rel}: 'Superseded runs' heading appears more than once")
    current = parts[0]
    rows: dict[int, tuple[str, str]] = {}
    for m in GATE_ROW.finditer(current):
        item, ran, result = int(m.group(1)), m.group(4).lower(), m.group(5).lower()
        if item in rows:
            ctx.err(f"{rel}: gate item {item} listed twice")
        if ran not in GATE_RESULTS or result not in GATE_RESULTS[ran]:
            ctx.err(f"{rel}: item {item}: invalid (ran={ran}, result={result}) combination")
        rows[item] = (ran, result)
    missing = GATE_ITEMS - rows.keys()
    if missing:
        ctx.err(f"{rel}: gate items missing: {sorted(missing)}")
    return rows


def check_state(ctx: Ctx) -> None:
    state = ctx.load_yaml("governance-state.yaml")
    if state is None:
        return
    debt = {d.get("id"): d for d in _entries_quiet(ctx, "technical-debt.yaml", "debt")}

    # -- phases
    phases = state.get("phases")
    if not isinstance(phases, list) or not all(isinstance(p, dict) for p in phases):
        ctx.err("governance-state.yaml: 'phases' must be a list of mappings")
        phases = []
    got = [(p.get("id"), p.get("name")) for p in phases]
    if got != CANONICAL_PHASES:
        ctx.err("governance-state.yaml: phases must match the canonical order and names (ADR-0003)")
    status_of = {}
    for p in phases:
        pid, st = p.get("id"), p.get("status")
        if st not in PHASE_STATUSES:
            ctx.err(f"phase {pid}: invalid status '{st}'")
            continue
        status_of[pid] = st
    active = [pid for pid, st in status_of.items() if st in {"in_progress", "gate_review"}]
    if len(active) > 1:
        ctx.err(f"phases: more than one phase active at once: {active}")
    for i, (pid, _) in enumerate(CANONICAL_PHASES):
        st = status_of.get(pid)
        if i > 0 and st not in (None, "not_started") and status_of.get(PHASE_IDS[i - 1]) != "closed":
            ctx.err(f"phase {pid}: is '{st}' but {PHASE_IDS[i - 1]} is not closed")
    repo = state.get("repository") or {}
    if not isinstance(repo, dict) or not isinstance(repo.get("dedicated"), bool):
        ctx.err("governance-state.yaml: repository.dedicated must be true/false")
    elif not repo["dedicated"] and status_of.get("P1") not in (None, "not_started"):
        ctx.err("phase P1: cannot start while the project is not in its dedicated repository")
    elif repo["dedicated"]:
        name = f"{repo.get('required_owner')}/{repo.get('required_name')}"
        try:
            remotes = subprocess.run(
                ["git", "-C", str(ctx.root), "remote", "-v"], capture_output=True, text=True, check=True
            ).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            remotes = ""
        if not (_text(repo.get("required_owner")) and _text(repo.get("required_name"))) or not re.search(
            # Host-anchored: the URL must *start* with a GitHub prefix (review N4b).
            rf"(?m)^\S+\t(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/){re.escape(name)}(?:\.git)?\s",
            remotes,
        ):
            ctx.err(f"repository.dedicated is true but no git remote points at '{name}'")

    for p in phases:
        pid, st = p.get("id"), p.get("status")
        blocked_by = p.get("blocked_by", [])
        if not isinstance(blocked_by, list):
            ctx.err(f"phase {pid}: blocked_by must be a list")
            blocked_by = []
        for ref in blocked_by:
            d = debt.get(ref)
            if d is None:
                ctx.err(f"phase {pid}: blocked_by references unknown debt '{ref}'")
            elif d.get("status") not in {"open", "scheduled"} or pid not in (d.get("blocks") or []):
                ctx.err(f"phase {pid}: blocked_by '{ref}' is not open debt that blocks {pid}")
        for did, d in debt.items():
            if d.get("status") in {"open", "scheduled"} and pid in (d.get("blocks") or []):
                if did not in blocked_by:
                    ctx.err(f"phase {pid}: open debt {did} blocks it but is not in blocked_by")
                if st != "not_started":
                    ctx.err(f"phase {pid}: is '{st}' while blocked by open debt {did}")
        if st in {"gate_review", "closed"}:
            report_rel = p.get("gate_report")
            plan_rel = p.get("plan")
            if not _text(plan_rel) or not (ctx.root / plan_rel).is_file():
                ctx.err(f"phase {pid}: plan missing")
            if not _text(report_rel):
                ctx.err(f"phase {pid}: gate_report not set")
                continue
            approved = p.get("approved_not_applicable") or []
            rows = _parse_gate_report(ctx, report_rel)
            if rows is None:
                continue
            for item, (_, result) in sorted(rows.items()):
                if result == "not_applicable" and item not in approved:
                    ctx.err(f"phase {pid}: gate item {item} is not_applicable without plan approval")
                if st == "closed" and result not in {"pass", "not_applicable"}:
                    ctx.err(f"phase {pid}: closed but gate item {item} is '{result}'")
            if rows.get(10, ("", ""))[1] == "pass":
                reason = _approved_by_both(ctx, p.get("review_record"))
                if reason:
                    ctx.err(f"phase {pid}: gate item 10 is 'pass' but {reason}")
            if st == "closed":
                tag = p.get("gate_tag")
                if not _text(tag) or not re.fullmatch(rf"phase-{pid}-v\d+\.\d+\.\d+", tag):
                    ctx.err(f"phase {pid}: closed without a gate_tag of the form phase-{pid}-v<semver>")
                elif not _annotated_tag_exists(ctx, tag):
                    ctx.err(f"phase {pid}: gate_tag '{tag}' does not exist as an annotated git tag")
                elif subprocess.run(
                    ["git", "-C", str(ctx.root), "merge-base", "--is-ancestor", f"refs/tags/{tag}^{{commit}}", "HEAD"],
                    capture_output=True,
                ).returncode != 0:
                    ctx.err(f"phase {pid}: gate_tag '{tag}' is not an ancestor of HEAD")
                if not (isinstance(repo, dict) and repo.get("dedicated") is True):
                    ctx.err(f"phase {pid}: cannot be closed outside the dedicated repository (ADR-0004)")

    # -- contracts
    contracts = state.get("contracts")
    if not isinstance(contracts, list):
        ctx.err("governance-state.yaml: 'contracts' must be a list")
        contracts = []
    by_id = {c.get("id"): c for c in contracts if isinstance(c, dict)}
    for cid, phase in DEFERRED_CONTRACTS.items():
        if cid not in by_id:
            ctx.err(f"contract {cid}: must be registered (deferred to {phase}, ADR-0003)")
        elif by_id[cid].get("not_before_phase") != phase:
            ctx.err(f"contract {cid}: not_before_phase must be {phase} (ADR-0003)")
    for c in contracts:
        if not isinstance(c, dict):
            ctx.err("governance-state.yaml: contract entries must be mappings")
            continue
        cid, st = c.get("id"), c.get("status")
        if st not in CONTRACT_STATUSES:
            ctx.err(f"contract {cid}: invalid status '{st}'")
            continue
        nb = c.get("not_before_phase")
        if nb is not None:
            if nb not in PHASE_IDS:
                ctx.err(f"contract {cid}: not_before_phase '{nb}' is not a phase")
            elif st != "not_drafted" and status_of.get(nb, "not_started") == "not_started":
                ctx.err(f"contract {cid}: is '{st}' but may not be drafted before {nb} starts")
        if c.get("reviewed_by") or st in {"approved", "frozen"}:
            if not REQUIRED_FREEZE_REVIEWERS <= set(c.get("reviewed_by") or []):
                ctx.err(f"contract {cid}: '{st}' without review by both reviewers")
            reason = _approved_by_both(ctx, c.get("review_record"))
            if reason:
                ctx.err(f"contract {cid}: claims review but {reason}")
        if st in {"approved", "frozen"}:
            path = c.get("path")
            if not _text(path) or not (ctx.root / path).is_file():
                ctx.err(f"contract {cid}: {st} but path '{path}' does not exist")
            if not isinstance(c.get("version"), str) or not SEMVER.match(c["version"]):
                ctx.err(f"contract {cid}: {st} without a semver version")
        if st == "frozen":
            tag = c.get("tag")
            if tag != f"contract-{cid}-v{c.get('version')}":
                ctx.err(f"contract {cid}: frozen tag must be 'contract-{cid}-v{c.get('version')}'")
            elif not _annotated_tag_exists(ctx, tag):
                ctx.err(f"contract {cid}: frozen tag '{tag}' does not exist as an annotated git tag")

    # -- pending tags (created by the release-tags workflow, ADR-0005 §7)
    pending = state.get("pending_tags", [])
    if not isinstance(pending, list):
        ctx.err("governance-state.yaml: 'pending_tags' must be a list")
        pending = []
    for i, entry in enumerate(pending):
        if not isinstance(entry, dict):
            ctx.err(f"pending_tags[{i}]: must be a mapping")
            continue
        tag, commit = entry.get("tag"), entry.get("commit")
        m = PENDING_TAG.match(tag) if isinstance(tag, str) else None
        if not m:
            ctx.err(f"pending_tags[{i}]: invalid tag name {tag!r}")
            continue
        if not isinstance(commit, str) or not PENDING_SHA.match(commit):
            ctx.err(f"pending_tags[{i}] {tag}: commit must be a 40-hex sha or 'self'")
        if not _text(entry.get("message")):
            ctx.err(f"pending_tags[{i}] {tag}: message must be non-empty")
        phase_id, contract_id, version = m.groups()
        if _annotated_tag_exists(ctx, tag):
            continue  # already created: the entry is now an audit record (review P1B-10)
        if phase_id is not None:
            if status_of.get(phase_id) not in {"gate_review", "closed"}:
                ctx.err(f"pending_tags[{i}] {tag}: phase {phase_id} is not in gate_review/closed")
        else:
            c = by_id.get(contract_id)
            if c is None:
                ctx.err(f"pending_tags[{i}] {tag}: unknown contract '{contract_id}'")
            elif c.get("version") != version or c.get("status") not in {"approved", "frozen"}:
                ctx.err(f"pending_tags[{i}] {tag}: contract {contract_id} v{version} is not approved")
            else:
                reason = _approved_by_both(ctx, c.get("review_record"))
                if reason:
                    ctx.err(f"pending_tags[{i}] {tag}: {reason}")

    # -- claims
    claims = state.get("claims")
    if not isinstance(claims, list):
        ctx.err("governance-state.yaml: 'claims' must be a list")
        claims = []
    owned: list[tuple[str, str]] = []
    tasks_seen: set[str] = set()
    for c in claims:
        if not isinstance(c, dict) or not _text(c.get("task")) or not _text(c.get("owner")):
            ctx.err("claims: each claim needs task and owner")
            continue
        task = c["task"]
        if task in tasks_seen:
            ctx.err(f"claims: task {task} claimed more than once")
        tasks_seen.add(task)
        m = CLAIM_TASK.match(task)
        if not m:
            ctx.err(f"claim {task}: task id must look like AO-P<n>-<nnn>")
        elif status_of.get(m.group(1)) != "in_progress":
            ctx.err(f"claim {task}: phase {m.group(1)} is not in_progress")
        paths = c.get("paths")
        if not isinstance(paths, list) or not paths:
            ctx.err(f"claim {task}: paths must be a non-empty list")
            continue
        for path in paths:
            raw = str(path)
            if GLOB_CHARS & set(raw):
                ctx.err(f"claim {task}: '{raw}' uses glob characters; claim concrete path prefixes")
                continue
            norm = posixpath.normpath(raw.strip()).strip("/")
            if raw.startswith("/") or norm in {"", "."} or norm == ".." or norm.startswith("../"):
                ctx.err(f"claim {task}: '{raw}' must be a relative path inside the repository")
                continue
            norm = norm.casefold()  # case-insensitive filesystems (review note A, round 2)
            for other_task, other in owned:
                if norm == other or norm.startswith(other + "/") or other.startswith(norm + "/"):
                    ctx.err(f"claims: '{path}' ({c['task']}) overlaps '{other}' ({other_task})")
            owned.append((c["task"], norm))


def check_adrs(ctx: Ctx) -> None:
    adr_dir = ctx.docs / "adr"
    index = adr_dir / "README.md"
    if not index.is_file():
        return
    index_text = index.read_text(encoding="utf-8", errors="replace")
    listed = set(re.findall(r"\((\d{4}-[a-z0-9-]+\.md)\)", index_text))
    files = {p.name for p in adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md")} - {"0000-template.md"}
    for name in sorted(files - listed):
        ctx.err(f"docs/adr/{name}: not listed in docs/adr/README.md")
    for name in sorted(listed - files):
        ctx.err(f"docs/adr/README.md: lists missing ADR {name}")
    known = {f"ADR-{n[:4]}" for n in files}
    known |= {d.get("id") for d in _entries_quiet(ctx, "assumptions.yaml", "assumptions")}
    known |= {d.get("id") for d in _entries_quiet(ctx, "technical-debt.yaml", "debt")}
    for name in sorted(files):
        text = (adr_dir / name).read_text(encoding="utf-8", errors="replace")
        status = re.search(r"^- Status:\s*(\S+)", text, re.MULTILINE)
        if not status or not status.group(1).lower().startswith(ADR_STATUSES):
            ctx.err(f"docs/adr/{name}: missing or invalid Status line")
        related = re.search(r"^- Related:(.*)$", text, re.MULTILINE)
        for ref in ID_REF.findall(related.group(1) if related else ""):
            if ref not in known:
                ctx.err(f"docs/adr/{name}: Related references unknown id {ref}")


def check_links(ctx: Ctx) -> None:
    root = ctx.root.resolve()
    for md in sorted(ctx.docs.rglob("*.md")):
        text = INLINE_CODE.sub("", FENCE.sub("", md.read_text(encoding="utf-8", errors="replace")))
        targets = INLINE_LINK.findall(text) + REF_DEF.findall(text) + AUTOLINK.findall(text)
        for target in targets:
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("#"):
                continue
            path_part = target.split("#", 1)[0]
            if not path_part:
                continue
            resolved = (md.parent / path_part).resolve()
            rel = md.relative_to(ctx.root)
            if root != resolved and root not in resolved.parents:
                ctx.err(f"{rel}: link escapes repository -> {target}")
            elif not resolved.exists():
                ctx.err(f"{rel}: broken link -> {target}")
    index = ctx.docs / "README.md"
    if index.is_file():
        linked = {
            (index.parent / t.split("#")[0]).resolve()
            for t in INLINE_LINK.findall(index.read_text(encoding="utf-8", errors="replace"))
        }
        for rel in REQUIRED_DOCS:
            if rel == "README.md" or rel.startswith("adr/0"):
                continue
            if (ctx.docs / rel).resolve() not in linked:
                ctx.err(f"docs/README.md: required document not linked from index: {rel}")


def _git(ctx: Ctx, *args: str, binary: bool = False) -> Any:
    return subprocess.run(
        ["git", "-C", str(ctx.root), *args], capture_output=True, check=True, text=not binary
    ).stdout


def check_secret_patterns(ctx: Ctx) -> None:
    try:
        _git(ctx, "rev-parse", "--git-dir")
    except (subprocess.CalledProcessError, FileNotFoundError):
        ctx.err("secret_patterns: not a git repository (history and index cannot be scanned)")
        return
    hits: set[tuple[str, str]] = set()

    def scan(label: str, data: bytes) -> None:
        for name, pat in SECRET_PATTERNS.items():
            if pat.search(data):
                hits.add((label, name))

    # Working tree: tracked + untracked-not-ignored files.
    for rel in _git(ctx, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0"):
        path = ctx.root / rel
        if rel and path.is_file():
            if path.stat().st_size > MAX_BLOB:
                ctx.err(f"secret_patterns: {rel} (working tree) exceeds {MAX_BLOB} bytes; not scanned by the backstop")
            else:
                scan(f"{rel} (working tree)", path.read_bytes())

    # Index and every blob reachable from any ref (catches staged-only and
    # history-only secrets). Blob -> first path seen, for reporting.
    blobs: dict[str, str] = {}
    for line in _git(ctx, "ls-files", "-s", "-z").split("\0"):
        if line:
            meta, path = line.split("\t", 1)
            blobs.setdefault(meta.split()[1], f"{path} (index)")
    try:
        objects = _git(ctx, "rev-list", "--objects", "--all")
    except subprocess.CalledProcessError:
        objects = ""  # no commits yet
    for line in objects.splitlines():
        sha, _, path = line.partition(" ")
        if path:
            blobs.setdefault(sha, f"{path} (history)")
    if blobs:
        batch = subprocess.run(
            ["git", "-C", str(ctx.root), "cat-file", "--batch"],
            input="\n".join(blobs).encode() + b"\n",
            capture_output=True,
            check=True,
        ).stdout
        pos = 0
        while pos < len(batch):
            nl = batch.index(b"\n", pos)
            header = batch[pos:nl].decode().split()
            pos = nl + 1
            if len(header) < 3:  # "<sha> missing"
                continue
            sha, kind, size = header[0], header[1], int(header[2])
            data = batch[pos : pos + size]
            pos += size + 1
            if kind != "blob":
                continue
            if size > MAX_BLOB:
                # Never skip silently (review N-03): large blobs must be scanned by gitleaks.
                ctx.err(f"secret_patterns: {blobs[sha]} exceeds {MAX_BLOB} bytes; not scanned by the backstop")
            else:
                scan(blobs[sha], data)

    # Commit and annotated-tag messages (review N-03).
    try:
        commit_msgs = _git(ctx, "log", "--all", "--format=%H%x00%B%x1e", binary=True)
        tag_msgs = _git(ctx, "for-each-ref", "refs/tags", "--format=%(refname:short)%00%(contents)%1e", binary=True)
    except subprocess.CalledProcessError:
        commit_msgs = tag_msgs = b""
    for blob, label in ((commit_msgs, "commit message"), (tag_msgs, "tag message")):
        for record in blob.split(b"\x1e"):
            ref, _, body = record.strip().partition(b"\x00")
            if body:
                scan(f"{ref.decode(errors='replace')[:12]} ({label})", body)

    for label, name in sorted(hits):
        ctx.err(f"possible secret ({name}) in {label}")  # value never printed
    ctx.info.append(f"secret pattern backstop scanned {len(blobs)} index/history blobs")


CHECKS: list[Callable[[Ctx], None]] = [
    check_required_files,
    check_registers,
    check_state,
    check_adrs,
    check_links,
    check_secret_patterns,
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)
    ctx = Ctx(args.root.resolve())
    if not ctx.docs.is_dir():
        print(f"check-governance: no docs/ directory under {ctx.root}", file=sys.stderr)
        return 2
    for check in CHECKS:
        before = len(ctx.errors)
        try:
            check(ctx)
        except Exception as exc:  # a crash is a failure, reported cleanly
            ctx.err(f"{check.__name__}: internal error {type(exc).__name__}: {exc}")
        name = check.__name__.removeprefix("check_")
        print(f"{name}: {'ok' if len(ctx.errors) == before else 'FAIL'}")
    for line in ctx.info:
        print(f"info: {line}")
    if ctx.errors:
        print("\nFAIL")
        for e in ctx.errors:
            print(f"  - {e}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
