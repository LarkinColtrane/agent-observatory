#!/usr/bin/env python3
"""Artifact check for agent-observatory: task contracts and handoffs.

Validates docs/phases/P<n>-tasks/ (repays TD-006):

  AO-P<n>-<nnn>.task.yaml     against docs/agent-task-contract.md
  AO-P<n>-<nnn>.handoff.yaml  against docs/agent-handoff-contract.md

YAML is loaded safely and duplicate keys are rejected.
Task: every template field present and non-blank, list fields are lists (use
"n/a" or [], never delete a field); task_id format == file name, and the
phase in both == the directory phase; owned_paths a non-empty list of
normalised relative paths without globs; independent reviewer is not the
owner; depends_on/blocks name existing tasks; acceptance criteria ids unique
with statement + verified_by; allocated_ids well-formed and never given to
two tasks; contracts written as `<normalised path>@<tag>` where the path is
in the governance-state.yaml contracts registry with exactly that tag.
Handoff: the same field rules; a task file exists for task_id; status/level/
kind enums; checks use only the allowed (ran, result) pairs (ran true ->
pass|fail, ran false -> not_run|not_applicable) and give a note when not
passing; acceptance criteria are exactly the task's; new register ids come
from the task's allocated_ids; `complete` needs all criteria met, an L1 check
that ran, and no fail or not_run check.
Claims: each governance-state.yaml claim has a well-formed task id; a claim
in a phase with a task directory names an existing task with the same owner,
and the task's owned_paths lie inside it.

Exit 0 = pass, 1 = fail, 2 = usage error.
Run with:  python3 -I scripts/check-artifacts.py [--root PATH]
Requires PyYAML (pinned in requirements-governance.txt).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - environment problem, not a finding
    print("check-artifacts: PyYAML is required (pip install -r requirements-governance.txt)", file=sys.stderr)
    sys.exit(2)

PHASE = r"(0|[1-9]\d*)"  # canonical phase number, no leading zeros
TASK_ID = re.compile(rf"AO-P{PHASE}-(\d{{3}})")
FILE_NAME = re.compile(rf"(AO-P{PHASE}-\d{{3}})\.(task|handoff)\.yaml")
TASK_DIR = re.compile(rf"P{PHASE}-tasks")
CONTRACT_REF = re.compile(r"([A-Za-z0-9._/-]+)@([A-Za-z0-9._/-]+)")
ID_PATTERNS = {"assumptions": re.compile(r"A-\d{3}"), "debt": re.compile(r"TD-\d{3}")}
AC_ID = re.compile(r"AC\d+")
SHA = re.compile(r"[0-9a-f]{7,40}")
GLOB_CHARS = set("*?[]{}")

SPECIALISTS = {"security", "data-integrity", "concurrency", "architecture"}
HANDOFF_STATUS = {"complete", "partial", "blocked", "abandoned"}
CHANGE_KINDS = {"added", "modified", "deleted"}
CHECK_LEVELS = {"L1", "L2"}
ALLOWED_RESULTS = {True: {"pass", "fail"}, False: {"not_run", "not_applicable"}}

# Template fields; nested mappings list their own required keys.
TASK_FIELDS: dict[str, tuple[str, ...]] = {
    "task_id": (), "title": (), "phase": (), "owner": (),
    "reviewers": ("independent", "specialist"),
    "depends_on": (), "blocks": (), "objective": (),
    "inputs": ("frozen_contracts", "adrs", "assumptions"),
    "owned_paths": (), "read_only_paths": (), "hotspots": (),
    "allocated_ids": ("assumptions", "debt"),
    "out_of_scope": (), "acceptance_criteria": (),
    "testing": ("level_1", "level_2", "adversarial_cases"),
    "security_notes": (), "failure_mode": (), "rollback": (),
    "budget": ("max_agent_turns", "escalate_if"),
}
TASK_LISTS = {
    "reviewers.specialist", "depends_on", "blocks", "inputs.frozen_contracts", "inputs.adrs",
    "inputs.assumptions", "owned_paths", "read_only_paths", "hotspots", "allocated_ids.assumptions",
    "allocated_ids.debt", "out_of_scope", "acceptance_criteria", "testing.adversarial_cases",
}
HANDOFF_FIELDS: dict[str, tuple[str, ...]] = {
    "task_id": (), "from": (), "to": (), "status": (), "commit": (), "branch": (),
    "summary": (), "inspected": (), "searched_for_reuse": (), "changes": (),
    "contracts": ("consumed", "changed"),
    "acceptance_criteria": (), "checks": (), "risks_and_open_questions": (),
    "new_assumptions": (), "new_debt": (), "specialist_review_needed": (),
    "rollback": (), "next_steps": (),
}
HANDOFF_LISTS = {
    "inspected", "searched_for_reuse", "changes", "contracts.consumed", "contracts.changed",
    "acceptance_criteria", "checks", "risks_and_open_questions", "new_assumptions", "new_debt",
    "specialist_review_needed",
}


class StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys (YAML silently keeps the last)."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)  # type: ignore[no-untyped-call]
            if isinstance(key, (str, int, float, bool)) or key is None:
                if key in seen:
                    raise yaml.constructor.ConstructorError(
                        None, None, f"duplicate key {key!r}", key_node.start_mark)
                seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _text(v: Any) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _in(v: Any, allowed: set[str]) -> bool:
    return isinstance(v, str) and v in allowed


def _items(v: Any) -> list[Any]:
    return v if isinstance(v, list) else []


def _normal_path(p: str) -> bool:
    """A normalised relative path: no leading '/', no empty, '.' or '..' segments."""
    return not p.startswith("/") and all(seg not in ("", ".", "..") for seg in p.split("/"))


class Checker:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.errors: list[str] = []
        self.info: list[str] = []
        self.tags: dict[str, Any] = {}       # contract path -> recorded tag
        self.allocated: dict[str, str] = {}  # register id -> task id

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def load(self, path: Path) -> dict[str, Any] | None:
        try:
            data = yaml.load(path.read_text(encoding="utf-8", errors="replace"), Loader=StrictLoader)  # noqa: S506
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            problem = getattr(exc, "problem", None) or "syntax error"
            self.err(f"{self.rel(path)}: invalid YAML{f' (line {mark.line + 1})' if mark else ''}: {problem}")
            return None
        except RecursionError:
            self.err(f"{self.rel(path)}: YAML nested too deeply")
            return None
        if not isinstance(data, dict):
            self.err(f"{self.rel(path)}: top level must be a mapping")
            return None
        return data

    # ------------------------------------------------------------ shared rules

    def required(self, rel: str, data: dict[str, Any], fields: dict[str, tuple[str, ...]],
                 lists: set[str]) -> None:
        def one(name: str, value: Any) -> None:
            if value is None or (isinstance(value, str) and not value.strip()):
                self.err(f"{rel}: missing or blank required field '{name}' (use 'n/a' or [], never delete it)")
            elif name in lists and not isinstance(value, list):
                self.err(f"{rel}: '{name}' must be a list")

        for key, sub in fields.items():
            value = data.get(key)
            if not sub or value is None:
                one(key, value)
            elif not isinstance(value, dict):
                self.err(f"{rel}: '{key}' must be a mapping with {', '.join(sub)}")
            else:
                for s in sub:
                    one(f"{key}.{s}", value.get(s))

    def ids(self, rel: str, field: str, value: Any, pattern: re.Pattern[str]) -> list[str]:
        if not isinstance(value, list):
            self.err(f"{rel}: '{field}' must be a list")
            return []
        good = [v for v in value if isinstance(v, str) and pattern.fullmatch(v)]
        for v in value:
            if v not in good:
                self.err(f"{rel}: {field} entry {v!r} must match {pattern.pattern}")
        return good

    def contract_refs(self, rel: str, field: str, refs: Any) -> None:
        if not isinstance(refs, list):
            self.err(f"{rel}: '{field}' must be a list")
            return
        for ref in refs:
            m = CONTRACT_REF.fullmatch(ref) if isinstance(ref, str) else None
            if not m:
                self.err(f"{rel}: {field} entry {ref!r} must be '<path>@<git tag>'")
                continue
            path, tag = m.groups()
            if not _normal_path(path):
                self.err(f"{rel}: {field} '{ref}' path must be normalised (no '.', '..' or empty segments)")
            elif path not in self.tags:
                self.err(f"{rel}: {field} '{ref}' is not a contract in docs/governance-state.yaml")
            elif self.tags[path] is None or self.tags[path] != tag:
                self.err(f"{rel}: {field} '{ref}' does not match the recorded tag "
                         f"{self.tags[path]!r} (superseded, unknown or untagged)")
            elif not (self.root / path).is_file():
                self.err(f"{rel}: {field} '{ref}' names a missing file")

    def specialists(self, rel: str, field: str, value: Any) -> None:
        if value is not None and (not isinstance(value, list) or not set(map(str, value)) <= SPECIALISTS):
            self.err(f"{rel}: {field} must be a list drawn from {sorted(SPECIALISTS)}")

    # ------------------------------------------------------------ task

    def check_task(self, rel: str, data: dict[str, Any], fname_id: str, phase: str, known: set[str]) -> None:
        self.required(rel, data, TASK_FIELDS, TASK_LISTS)
        tid = data.get("task_id")
        if not (isinstance(tid, str) and TASK_ID.fullmatch(tid)):
            self.err(f"{rel}: task_id {tid!r} must look like AO-P<n>-<nnn>")
        elif tid != fname_id:
            self.err(f"{rel}: task_id {tid} does not match the file name ({fname_id})")
        elif TASK_ID.fullmatch(tid).group(1) != phase:  # type: ignore[union-attr]
            self.err(f"{rel}: task_id {tid} is not in phase directory P{phase}-tasks")
        if data.get("phase") is not None and data["phase"] != f"P{phase}":
            self.err(f"{rel}: phase {data['phase']!r} must be 'P{phase}'")

        rv = data.get("reviewers")
        if isinstance(rv, dict):
            ind = rv.get("independent")
            if _text(data.get("owner")) and data["owner"] in (ind if isinstance(ind, list) else [ind]):
                self.err(f"{rel}: independent reviewer must never be the owner ({data['owner']})")
            self.specialists(rel, "reviewers.specialist", rv.get("specialist"))

        for f in ("depends_on", "blocks"):
            if data.get(f) is None:
                continue
            for dep in self.ids(rel, f, data[f], TASK_ID):
                if dep == fname_id:
                    self.err(f"{rel}: {f} names the task itself")
                elif dep not in known:
                    self.err(f"{rel}: {f} names unknown task {dep}")

        inputs = data.get("inputs")
        if isinstance(inputs, dict):
            if inputs.get("frozen_contracts") is not None:
                self.contract_refs(rel, "inputs.frozen_contracts", inputs["frozen_contracts"])
            if inputs.get("assumptions") is not None:
                self.ids(rel, "inputs.assumptions", inputs["assumptions"], ID_PATTERNS["assumptions"])

        owned = data.get("owned_paths")
        if owned is not None and (not isinstance(owned, list) or not owned):
            self.err(f"{rel}: owned_paths must be a non-empty list")
        for p in _items(owned):
            if not _text(p):
                self.err(f"{rel}: owned_paths entry {p!r} must be a path")
            elif GLOB_CHARS & set(p):
                self.err(f"{rel}: owned_paths '{p}' uses glob characters; use concrete path prefixes")
            elif not _normal_path(p):
                self.err(f"{rel}: owned_paths '{p}' must be a normalised relative path "
                         "(no leading '/', no '.', '..' or empty segments)")

        alloc = data.get("allocated_ids")
        if isinstance(alloc, dict):
            for key, pat in ID_PATTERNS.items():
                if alloc.get(key) is None:
                    continue
                for rid in self.ids(rel, f"allocated_ids.{key}", alloc[key], pat):
                    holder = self.allocated.setdefault(rid, fname_id)
                    if holder != fname_id:
                        self.err(f"{rel}: {rid} is already allocated to {holder}")

        acs = data.get("acceptance_criteria")
        if acs is not None and (not isinstance(acs, list) or not acs):
            self.err(f"{rel}: acceptance_criteria must be a non-empty list")
        seen: set[str] = set()
        for i, ac in enumerate(_items(acs)):
            if not isinstance(ac, dict):
                self.err(f"{rel}: acceptance_criteria[{i}] must be a mapping")
                continue
            aid = ac.get("id")
            if not (isinstance(aid, str) and AC_ID.fullmatch(aid)):
                self.err(f"{rel}: acceptance_criteria[{i}].id {aid!r} must look like AC<n>")
            elif aid in seen:
                self.err(f"{rel}: acceptance criterion {aid} defined twice")
            seen.add(str(aid))
            for f in ("statement", "verified_by"):
                if not _text(ac.get(f)):
                    self.err(f"{rel}: acceptance_criteria[{i}] missing '{f}'")

    # ------------------------------------------------------------ handoff

    def check_handoff(self, rel: str, data: dict[str, Any], fname_id: str,
                      tasks: dict[str, dict[str, Any]]) -> None:
        self.required(rel, data, HANDOFF_FIELDS, HANDOFF_LISTS)
        tid = data.get("task_id")
        task: dict[str, Any] | None = None
        if not (isinstance(tid, str) and TASK_ID.fullmatch(tid)):
            self.err(f"{rel}: task_id {tid!r} must look like AO-P<n>-<nnn>")
        elif tid != fname_id:
            self.err(f"{rel}: task_id {tid} does not match the file name ({fname_id})")
        elif tid not in tasks:
            self.err(f"{rel}: no task contract {tid}.task.yaml for this handoff")
        else:
            task = tasks[tid]

        status = data.get("status")
        if status is not None and not _in(status, HANDOFF_STATUS):
            self.err(f"{rel}: status {status!r} must be one of {sorted(HANDOFF_STATUS)}")
        commit = data.get("commit")
        if commit is not None and not (isinstance(commit, str) and SHA.fullmatch(commit)):
            self.err(f"{rel}: commit must be a git SHA (7-40 lowercase hex)")
        steps = data.get("next_steps")
        if _in(status, {"partial", "blocked"}) and not (_text(steps) and steps.strip().lower() != "n/a"):
            self.err(f"{rel}: a {status} handoff must say in next_steps what the successor does first")
        for i, c in enumerate(_items(data.get("changes"))):
            if not (isinstance(c, dict) and _text(c.get("path")) and _in(c.get("kind"), CHANGE_KINDS)):
                self.err(f"{rel}: changes[{i}] needs a 'path' and kind in {sorted(CHANGE_KINDS)}")
        contracts = data.get("contracts")
        if isinstance(contracts, dict):
            for f in ("consumed", "changed"):
                if contracts.get(f) is not None:
                    self.contract_refs(rel, f"contracts.{f}", contracts[f])
        self.specialists(rel, "specialist_review_needed", data.get("specialist_review_needed"))

        all_met = True
        reported: set[str] = set()
        for i, ac in enumerate(_items(data.get("acceptance_criteria"))):
            if not isinstance(ac, dict):
                self.err(f"{rel}: acceptance_criteria[{i}] must be a mapping")
                continue
            aid = str(ac.get("id"))
            if aid in reported:
                self.err(f"{rel}: acceptance criterion {aid} reported twice")
            reported.add(aid)
            if not isinstance(ac.get("met"), bool):
                self.err(f"{rel}: acceptance_criteria[{i}].met must be true or false")
            all_met = all_met and ac.get("met") is True
            if not _text(ac.get("evidence")):
                self.err(f"{rel}: acceptance_criteria[{i}] missing 'evidence'")
        if task is not None:
            expected = {str(a.get("id")) for a in _items(task.get("acceptance_criteria")) if isinstance(a, dict)}
            for aid in sorted(reported - expected):
                self.err(f"{rel}: acceptance criterion {aid} is not in the task contract")
            for aid in sorted(expected - reported):
                self.err(f"{rel}: acceptance criterion {aid} from the task is not reported")

        any_fail = not_run = False
        ran_l1 = False
        checks = data.get("checks")
        if checks is not None and (not isinstance(checks, list) or not checks):
            self.err(f"{rel}: checks must be a non-empty list")
        for i, c in enumerate(_items(checks)):
            if not isinstance(c, dict):
                self.err(f"{rel}: checks[{i}] must be a mapping")
                continue
            if not _in(c.get("level"), CHECK_LEVELS):
                self.err(f"{rel}: checks[{i}].level {c.get('level')!r} must be L1 or L2")
            if not _text(c.get("command")):
                self.err(f"{rel}: checks[{i}] missing exact 'command'")
            ran, result = c.get("ran"), c.get("result")
            if not isinstance(ran, bool):
                self.err(f"{rel}: checks[{i}].ran must be true or false")
            elif not _in(result, ALLOWED_RESULTS[ran]):
                self.err(f"{rel}: checks[{i}] invalid (ran, result) combination ({str(ran).lower()}, {result!r}); "
                         f"ran {str(ran).lower()} allows {sorted(ALLOWED_RESULTS[ran])}")
            any_fail = any_fail or result == "fail"
            not_run = not_run or result == "not_run"
            ran_l1 = ran_l1 or (c.get("level") == "L1" and ran is True)
            if _in(result, {"fail", "not_run", "not_applicable"}) and not _text(c.get("note")):
                self.err(f"{rel}: checks[{i}] result {result} needs a 'note' with the reason")
            if ran is True and not _text(c.get("evidence")):
                self.err(f"{rel}: checks[{i}] ran but has no 'evidence'")
        if status == "complete" and (not all_met or any_fail or not_run or not ran_l1):
            self.err(f"{rel}: status complete requires every acceptance criterion met, at least one L1 check "
                     "that ran, and no fail or not_run check")

        alloc = (task or {}).get("allocated_ids")
        alloc = alloc if isinstance(alloc, dict) else {}
        for f, key in (("new_assumptions", "assumptions"), ("new_debt", "debt")):
            if data.get(f) is None:
                continue
            for rid in self.ids(rel, f, data[f], ID_PATTERNS[key]):
                if task is not None and rid not in _items(alloc.get(key)):
                    self.err(f"{rel}: {f} {rid} is not in the task's allocated_ids.{key}")

    # ------------------------------------------------------------ driver

    def check_phase_dir(self, d: Path, phase: str, claims: list[Any]) -> None:
        files: dict[str, dict[str, Path]] = {"task": {}, "handoff": {}}
        for f in sorted(d.iterdir()):
            m = FILE_NAME.fullmatch(f.name)
            if m and f.is_file() and m.group(2) == phase:
                files[m.group(3)][m.group(1)] = f
            elif m and f.is_file():
                self.err(f"{self.rel(f)}: file is not in phase directory P{m.group(2)}-tasks")
            elif m or f.suffix in {".yaml", ".yml"} or f.is_dir():
                self.err(f"{self.rel(f)}: unexpected entry; expected AO-P{phase}-<nnn>.task.yaml or .handoff.yaml file")
        tasks = {tid: data for tid, f in files["task"].items() if (data := self.load(f)) is not None}
        for tid, data in tasks.items():
            self.check_task(self.rel(files["task"][tid]), data, tid, phase, set(files["task"]))
        for tid, f in files["handoff"].items():
            if (data := self.load(f)) is not None:
                self.check_handoff(self.rel(f), data, tid, tasks)

        for c in claims:
            tid = c.get("task") if isinstance(c, dict) else None
            m = TASK_ID.fullmatch(tid) if isinstance(tid, str) else None
            if not m or m.group(1) != phase:
                continue  # malformed ids are reported once in run()
            task = tasks.get(tid)
            if task is None:
                self.err(f"claim {tid}: no task contract in {self.rel(d)}")
                continue
            if task.get("owner") != c.get("owner"):
                self.err(f"claim {tid}: owner {c.get('owner')!r} differs from task owner {task.get('owner')!r}")
            prefixes = [q.rstrip("/") for q in _items(c.get("paths")) if isinstance(q, str)]
            for p in _items(task.get("owned_paths")):
                p = str(p).rstrip("/")
                if not any(p == q or p.startswith(q + "/") for q in prefixes):
                    self.err(f"claim {tid}: owned path '{p}' is outside the recorded claim")
        self.info.append(f"{d.name}: {len(files['task'])} task(s), {len(files['handoff'])} handoff(s)")

    def run(self) -> None:
        state_path = self.root / "docs" / "governance-state.yaml"
        if not state_path.is_file():
            self.err("docs/governance-state.yaml: missing")
        state = (self.load(state_path) if state_path.is_file() else None) or {}
        self.tags = {c["path"]: c.get("tag") for c in _items(state.get("contracts"))
                     if isinstance(c, dict) and _text(c.get("path"))}
        claims = _items(state.get("claims"))
        for c in claims:
            tid = c.get("task") if isinstance(c, dict) else None
            if not (isinstance(tid, str) and TASK_ID.fullmatch(tid)):
                self.err(f"claim {tid!r}: task must be a well-formed id AO-P<n>-<nnn>")
        phases = self.root / "docs" / "phases"
        found = False
        for d in sorted(phases.iterdir()) if phases.is_dir() else []:
            m = TASK_DIR.fullmatch(d.name)
            if m and d.is_dir():
                found = True
                self.check_phase_dir(d, m.group(1), claims)
        if not found:
            self.info.append("no docs/phases/P<n>-tasks/ directories")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate task contracts and handoffs.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)
    checker = Checker(args.root.resolve())
    if not (checker.root / "docs").is_dir():
        print(f"check-artifacts: no docs/ directory under {checker.root}", file=sys.stderr)
        return 2
    try:
        checker.run()
    except Exception as exc:  # a crash is a failure, reported cleanly
        checker.err(f"internal error {type(exc).__name__}: {exc}")
    for line in checker.info:
        print(f"info: {line}")
    if checker.errors:
        print("\nFAIL")
        for e in checker.errors:
            print(f"  - {e}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
