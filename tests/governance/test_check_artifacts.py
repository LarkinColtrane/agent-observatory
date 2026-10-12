"""Adversarial tests for scripts/check-artifacts.py (task contracts + handoffs).

Each test builds a throwaway root holding the real governance-state.yaml, the
contract files it registers and the real P1 task files, adds one valid
synthetic handoff, breaks exactly one rule, and asserts the checker FAILS with
a specific message. Positive tests assert that the real repository and the
unmodified fixture pass, so the negative tests are meaningful. Most tests call
main() in-process for speed; the Subprocess class proves real exit codes and
that no traceback escapes. Regression cases from Reviewer B (R-B-005-*) are
marked with their finding id.
Run: python3 -I -m unittest discover -s tests/governance -t . -v
"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable

import yaml

REPO = Path(__file__).resolve().parents[2]
CHECKER = REPO / "scripts" / "check-artifacts.py"
TASKS = "docs/phases/P1-tasks"
STATE = "docs/governance-state.yaml"
CONTRACT = "docs/adr/0005-phase-1-foundation-contract.md@contract-phase1-foundation-v1.0.0"

_spec = importlib.util.spec_from_file_location("check_artifacts", CHECKER)
assert _spec and _spec.loader
check_artifacts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_artifacts)

HANDOFF: dict[str, Any] = {
    "task_id": "AO-P1-005",
    "from": "w4-governance-tooling",
    "to": "reviewer-b",
    "status": "complete",
    "commit": "0123456789abcdef0123456789abcdef01234567",
    "branch": "p1/005-governance-tooling",
    "summary": "Synthetic handoff used by the adversarial tests.",
    "inspected": ["docs/agent-handoff-contract.md"],
    "searched_for_reuse": [{"query": "existing validator", "result": "nothing suitable"}],
    "changes": [{"path": "scripts/check-artifacts.py", "kind": "added", "note": "validator"}],
    "contracts": {"consumed": [CONTRACT], "changed": []},
    "acceptance_criteria": [
        {"id": "AC1", "met": True, "evidence": "test_check_artifacts"},
        {"id": "AC2", "met": True, "evidence": "test_workflow"},
    ],
    "checks": [
        {"level": "L1", "command": "python3 -I scripts/check-artifacts.py", "ran": True,
         "result": "pass", "evidence": "PASS"},
        {"level": "L2", "command": "docker compose up", "ran": False, "result": "not_applicable",
         "evidence": "n/a", "note": "no containers in this task"},
    ],
    "risks_and_open_questions": ["none"],
    "new_assumptions": [],
    "new_debt": ["TD-015"],
    "specialist_review_needed": [],
    "rollback": "revert commit",
    "next_steps": "n/a",
}


def run_inprocess(root: Path) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = check_artifacts.main(["--root", str(root)])
    return rc, out.getvalue() + err.getvalue()


def run_subprocess(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-I", str(CHECKER), *args],
                          capture_output=True, text=True, timeout=60, check=False)


class ArtifactCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="artifacts-test-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        state = yaml.safe_load((REPO / STATE).read_text(encoding="utf-8"))
        registered = [c["path"] for c in state["contracts"] if c.get("path")]
        for rel in [STATE, *registered]:
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / rel, self.root / rel)
        shutil.copytree(REPO / TASKS, self.root / TASKS)
        self.write(f"{TASKS}/AO-P1-005.handoff.yaml", HANDOFF)

    # helpers ------------------------------------------------------------
    def path(self, rel: str) -> Path:
        return self.root / rel

    def read(self, rel: str) -> Any:
        return yaml.safe_load(self.path(rel).read_text(encoding="utf-8"))

    def write(self, rel: str, data: Any) -> None:
        self.path(rel).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    def write_text(self, rel: str, text: str) -> None:
        self.path(rel).write_text(text, encoding="utf-8")

    def edit(self, rel: str, fn: Callable[[Any], None]) -> None:
        data = self.read(rel)
        fn(data)
        self.write(rel, data)

    def task(self, fn: Callable[[Any], None], n: int = 5) -> None:
        self.edit(f"{TASKS}/AO-P1-00{n}.task.yaml", fn)

    def handoff(self, fn: Callable[[Any], None]) -> None:
        self.edit(f"{TASKS}/AO-P1-005.handoff.yaml", fn)

    def assertFails(self, *fragments: str) -> None:
        rc, out = run_inprocess(self.root)
        self.assertEqual(rc, 1, out)
        self.assertNotIn("internal error", out)
        for frag in fragments:
            self.assertIn(frag, out)

    def assertClean(self) -> None:
        rc, out = run_inprocess(self.root)
        self.assertIn(rc, (0, 1), out)
        self.assertNotIn("internal error", out)


class Positive(ArtifactCase):
    def test_real_task_files_cover_p1_plan(self) -> None:
        ids = sorted(p.name.split(".")[0] for p in (REPO / TASKS).glob("*.task.yaml"))
        self.assertEqual(ids, [f"AO-P1-00{i}" for i in range(1, 8)])

    def test_fixture_with_valid_handoff_passes(self) -> None:
        rc, out = run_inprocess(self.root)
        self.assertEqual(rc, 0, out)
        handoffs = len(list(self.path(TASKS).glob("*.handoff.yaml")))  # fixture count, not a live constant
        self.assertGreaterEqual(handoffs, 1)
        self.assertIn(f"7 task(s), {handoffs} handoff(s)", out)

    def test_not_applicable_with_note_still_allowed_on_complete(self) -> None:
        rc, out = run_inprocess(self.root)  # fixture has an L2 not_applicable check
        self.assertEqual(rc, 0, out)

    def test_usage_error_without_docs(self) -> None:
        shutil.rmtree(self.root / "docs")
        rc, out = run_inprocess(self.root)
        self.assertEqual(rc, 2, out)


class TaskRules(ArtifactCase):
    def test_missing_top_level_field(self) -> None:
        self.task(lambda d: d.pop("rollback"))
        self.assertFails("missing or blank required field 'rollback'")

    def test_blank_field_counts_as_missing(self) -> None:
        self.task(lambda d: d.update(failure_mode="  "))
        self.assertFails("missing or blank required field 'failure_mode'")

    def test_missing_nested_field(self) -> None:
        self.task(lambda d: d["reviewers"].pop("specialist"))
        self.assertFails("missing or blank required field 'reviewers.specialist'")

    def test_blank_nested_fields(self) -> None:  # R-B-005-04 (case nested_empty_string)
        self.task(lambda d: (d["testing"].update(level_1=""), d["budget"].update(escalate_if="")), n=7)
        self.assertFails("'testing.level_1'", "'budget.escalate_if'")

    def test_list_field_given_as_string(self) -> None:  # R-B-005-04
        self.task(lambda d: d.update(out_of_scope="everything else"))
        self.assertFails("'out_of_scope' must be a list")

    def test_nested_list_field_given_as_string(self) -> None:  # R-B-005-04
        self.task(lambda d: d["testing"].update(adversarial_cases="many"))
        self.assertFails("'testing.adversarial_cases' must be a list")

    def test_bad_task_id_format(self) -> None:
        self.task(lambda d: d.update(task_id="AO-P1-5"))
        self.assertFails("must look like AO-P<n>-<nnn>")

    def test_task_id_does_not_match_filename(self) -> None:
        self.task(lambda d: d.update(task_id="AO-P1-009"))
        self.assertFails("does not match the file name (AO-P1-005)")

    def test_phase_does_not_match_directory(self) -> None:
        self.task(lambda d: d.update(phase="P2"))
        self.assertFails("phase 'P2' must be 'P1'")

    def test_other_phase_file_in_directory(self) -> None:  # R-B-005-06 (case other_phase_id_in_P1_dir)
        self.path(f"{TASKS}/AO-P1-007.task.yaml").rename(self.path(f"{TASKS}/AO-P2-007.task.yaml"))
        self.edit(f"{TASKS}/AO-P2-007.task.yaml", lambda d: d.update(task_id="AO-P2-007"))
        self.task(lambda d: d.update(blocks=["AO-P2-007"]), n=6)
        self.assertFails("AO-P2-007.task.yaml: file is not in phase directory P2-tasks",
                         "blocks names unknown task AO-P2-007")

    def test_leading_zero_phase_in_file_name(self) -> None:  # R-B-005-06
        self.write(f"{TASKS}/AO-P01-008.task.yaml", {"task_id": "AO-P01-008"})
        self.assertFails("AO-P01-008.task.yaml: unexpected entry")

    def test_directory_named_like_task(self) -> None:  # case dir_named_like_task
        self.path(f"{TASKS}/AO-P1-010.task.yaml").mkdir()
        self.assertFails("AO-P1-010.task.yaml: unexpected entry")

    def test_owned_paths_empty(self) -> None:
        self.task(lambda d: d.update(owned_paths=[]))
        self.assertFails("owned_paths must be a non-empty list")

    def test_owned_paths_glob(self) -> None:
        self.task(lambda d: d["owned_paths"].append("scripts/**"))
        self.assertFails("uses glob characters")

    def test_owned_paths_not_normalised(self) -> None:  # R-B-005-07 (case owned_dot)
        for bad in (".", "./scripts", "scripts//x", "../outside", "scripts/./x", "/etc", "scripts/"):
            with self.subTest(bad=bad):
                self.task(lambda d, bad=bad: d.update(owned_paths=[bad]))
                self.assertFails(f"owned_paths '{bad}' must be a normalised relative path")

    def test_owner_reviews_own_task(self) -> None:
        self.task(lambda d: d["reviewers"].update(independent="w4-governance-tooling"))
        self.assertFails("independent reviewer must never be the owner")

    def test_unknown_specialist(self) -> None:
        self.task(lambda d: d["reviewers"].update(specialist=["vibes"]))
        self.assertFails("reviewers.specialist must be a list drawn from")

    def test_depends_on_unknown_task(self) -> None:
        self.task(lambda d: d.update(depends_on=["AO-P1-099"]))
        self.assertFails("depends_on names unknown task AO-P1-099")

    def test_depends_on_itself(self) -> None:
        self.task(lambda d: d.update(blocks=["AO-P1-005"]))
        self.assertFails("blocks names the task itself")

    def test_contract_without_tag(self) -> None:
        self.task(lambda d: d["inputs"].update(frozen_contracts=["docs/adr/0005-phase-1-foundation-contract.md"]))
        self.assertFails("must be '<path>@<git tag>'")

    def test_contract_with_superseded_tag(self) -> None:
        self.task(lambda d: d["inputs"].update(
            frozen_contracts=["docs/adr/0005-phase-1-foundation-contract.md@contract-phase1-foundation-v0.9.0"]))
        self.assertFails("superseded, unknown or untagged")

    def test_contract_not_in_registry(self) -> None:  # R-B-005-03 (case consumed_unregistered_path)
        self.task(lambda d: d["inputs"].update(frozen_contracts=["docs/adr/9999-nope.md@v1"]))
        self.assertFails("is not a contract in docs/governance-state.yaml")

    def test_contract_registered_without_tag(self) -> None:  # R-B-005-03
        self.task(lambda d: d["inputs"].update(frozen_contracts=["docs/agent-task-contract.md@anything"]))
        self.assertFails("does not match the recorded tag None")

    def test_allocated_id_bad_format(self) -> None:
        self.task(lambda d: d["allocated_ids"].update(debt=["TD-15"]))
        self.assertFails("allocated_ids.debt entry 'TD-15'")

    def test_allocated_id_given_to_two_tasks(self) -> None:
        self.task(lambda d: d["allocated_ids"].update(debt=["TD-012"]))
        self.assertFails("TD-012 is already allocated to AO-P1-002")

    def test_duplicate_acceptance_criterion(self) -> None:
        self.task(lambda d: d["acceptance_criteria"].append(copy.deepcopy(d["acceptance_criteria"][0])))
        self.assertFails("acceptance criterion AC1 defined twice")

    def test_acceptance_criterion_without_verification(self) -> None:
        self.task(lambda d: d["acceptance_criteria"][0].pop("verified_by"))
        self.assertFails("missing 'verified_by'")

    def test_unexpected_file_name(self) -> None:
        self.write(f"{TASKS}/AO-P1-5.task.yaml", {"task_id": "AO-P1-5"})
        self.assertFails("unexpected entry")

    def test_malformed_yaml(self) -> None:
        self.write_text(f"{TASKS}/AO-P1-005.task.yaml", "task_id: [unclosed\n")
        self.assertFails("AO-P1-005.task.yaml: invalid YAML")

    def test_duplicate_key(self) -> None:  # R-B-005-10 (case duplicate_key)
        text = self.path(f"{TASKS}/AO-P1-005.handoff.yaml").read_text(encoding="utf-8")
        self.write_text(f"{TASKS}/AO-P1-005.handoff.yaml", text.replace("status: complete", "status: complete\nstatus: partial"))
        self.assertFails("invalid YAML", "duplicate key 'status'")

    def test_python_tag_rejected(self) -> None:  # case python_tag
        self.write_text(f"{TASKS}/AO-P1-005.task.yaml", 'task_id: !!python/object/apply:os.system ["echo pwned"]\n')
        self.assertFails("invalid YAML", "could not determine a constructor")

    def test_deep_nesting(self) -> None:  # case deep_nesting
        self.write_text(f"{TASKS}/AO-P1-005.task.yaml", "task_id: " + "[" * 5000 + "]" * 5000 + "\n")
        self.assertFails("AO-P1-005.task.yaml")

    def test_non_utf8_file(self) -> None:  # case binary
        self.path(f"{TASKS}/AO-P1-005.task.yaml").write_bytes("task_id: x".encode("utf-16"))
        self.assertFails("AO-P1-005.task.yaml: invalid YAML")

    def test_top_level_not_mapping(self) -> None:
        self.write(f"{TASKS}/AO-P1-005.task.yaml", ["a", "b"])
        self.assertFails("top level must be a mapping")


class HandoffRules(ArtifactCase):
    def test_missing_field(self) -> None:
        self.handoff(lambda d: d.pop("checks"))
        self.assertFails("missing or blank required field 'checks'")

    def test_changes_given_as_string(self) -> None:  # R-B-005-04 (case changes_string)
        self.handoff(lambda d: d.update(changes="lots"))
        self.assertFails("'changes' must be a list")

    def test_ran_true_not_run(self) -> None:
        self.handoff(lambda d: d["checks"][0].update(result="not_run", note="x"))
        self.assertFails("invalid (ran, result) combination (true, 'not_run')")

    def test_ran_false_pass(self) -> None:
        self.handoff(lambda d: d["checks"][1].update(result="pass"))
        self.assertFails("invalid (ran, result) combination (false, 'pass')")

    def test_ran_false_fail(self) -> None:
        self.handoff(lambda d: d["checks"][1].update(result="fail"))
        self.assertFails("invalid (ran, result) combination (false, 'fail')")

    def test_ran_true_without_evidence(self) -> None:
        self.handoff(lambda d: d["checks"][0].pop("evidence"))
        self.assertFails("checks[0] ran but has no 'evidence'")

    def test_ran_not_boolean(self) -> None:
        self.handoff(lambda d: d["checks"][0].update(ran="yes"))
        self.assertFails("checks[0].ran must be true or false")

    def test_unknown_result(self) -> None:
        self.handoff(lambda d: d["checks"][0].update(result="passed"))
        self.assertFails("invalid (ran, result) combination (true, 'passed')")

    def test_not_run_without_reason(self) -> None:
        self.handoff(lambda d: d["checks"][1].pop("note"))
        self.assertFails("needs a 'note' with the reason")

    def test_bad_level(self) -> None:
        self.handoff(lambda d: d["checks"][0].update(level="L3"))
        self.assertFails("must be L1 or L2")

    def test_status_enum(self) -> None:
        self.handoff(lambda d: d.update(status="done"))
        self.assertFails("status 'done' must be one of")

    def test_commit_not_sha(self) -> None:
        self.handoff(lambda d: d.update(commit="HEAD"))
        self.assertFails("commit must be a git SHA")

    def test_handoff_without_task_file(self) -> None:
        self.path(f"{TASKS}/AO-P1-005.handoff.yaml").rename(self.path(f"{TASKS}/AO-P1-008.handoff.yaml"))
        self.edit(f"{TASKS}/AO-P1-008.handoff.yaml", lambda d: d.update(task_id="AO-P1-008"))
        self.assertFails("no task contract AO-P1-008.task.yaml for this handoff")

    def test_task_id_mismatch(self) -> None:
        self.handoff(lambda d: d.update(task_id="AO-P1-004"))
        self.assertFails("does not match the file name (AO-P1-005)")

    def test_consumed_contract_without_tag(self) -> None:
        self.handoff(lambda d: d["contracts"].update(consumed=["docs/adr/0005-phase-1-foundation-contract.md"]))
        self.assertFails("contracts.consumed entry")

    def test_consumed_contract_superseded(self) -> None:
        self.handoff(lambda d: d["contracts"].update(
            consumed=["docs/adr/0005-phase-1-foundation-contract.md@contract-phase1-foundation-v0.1.0"]))
        self.assertFails("superseded, unknown or untagged")

    def test_consumed_contract_path_aliases(self) -> None:  # R-B-005-03 (case consumed_dotdot_alias)
        for path in ("scripts/../docs/adr/0005-phase-1-foundation-contract.md",
                     "./docs/adr/0005-phase-1-foundation-contract.md",
                     "docs//adr/0005-phase-1-foundation-contract.md"):
            with self.subTest(path=path):
                self.handoff(lambda d, path=path: d["contracts"].update(
                    consumed=[f"{path}@contract-phase1-foundation-v1.0.0"]))
                self.assertFails("path must be normalised")

    def test_consumed_unregistered_path(self) -> None:  # R-B-005-03 (case consumed_unregistered_path)
        self.handoff(lambda d: d["contracts"].update(consumed=["docs/governance-state.yaml@totally-made-up"]))
        self.assertFails("is not a contract in docs/governance-state.yaml")

    def test_unknown_acceptance_criterion(self) -> None:
        self.handoff(lambda d: d["acceptance_criteria"].append({"id": "AC9", "met": True, "evidence": "x"}))
        self.assertFails("acceptance criterion AC9 is not in the task contract")

    def test_unreported_acceptance_criterion(self) -> None:
        self.handoff(lambda d: d["acceptance_criteria"].pop())
        self.assertFails("acceptance criterion AC2 from the task is not reported")

    def test_met_not_boolean(self) -> None:
        self.handoff(lambda d: d["acceptance_criteria"][0].update(met="mostly"))
        self.assertFails("met must be true or false")

    def test_debt_id_not_allocated(self) -> None:
        self.handoff(lambda d: d.update(new_debt=["TD-012"]))
        self.assertFails("new_debt TD-012 is not in the task's allocated_ids.debt")

    def test_complete_with_failing_check(self) -> None:
        self.handoff(lambda d: d["checks"][0].update(result="fail", note="1 test failed"))
        self.assertFails("status complete requires")

    def test_complete_with_unmet_criterion(self) -> None:
        self.handoff(lambda d: d["acceptance_criteria"][0].update(met=False))
        self.assertFails("status complete requires")

    def test_complete_with_not_run(self) -> None:  # R-B-005-05 (case complete_with_not_run)
        self.handoff(lambda d: d["checks"][1].update(result="not_run"))
        self.assertFails("status complete requires")

    def test_complete_without_l1_that_ran(self) -> None:  # R-B-005-05 (case complete_without_L1)
        self.handoff(lambda d: d["checks"][0].update(level="L2"))
        self.assertFails("status complete requires")

    def test_partial_without_next_steps(self) -> None:
        self.handoff(lambda d: d.update(status="partial"))
        self.assertFails("a partial handoff must say in next_steps")

    def test_bad_change_kind(self) -> None:
        self.handoff(lambda d: d["changes"][0].update(kind="renamed"))
        self.assertFails("changes[0] needs a 'path' and kind in")

    def test_unknown_specialist(self) -> None:
        self.handoff(lambda d: d.update(specialist_review_needed=["luck"]))
        self.assertFails("specialist_review_needed must be a list drawn from")


class NeverCrash(ArtifactCase):
    """Wrong types anywhere give clean findings, never an exception.

    The type fuzz calls the rule functions directly on in-memory data (one
    full run per mutation would cost ~40 ms each); file-level cases below go
    through main()."""

    BAD = (7, "x", ["x"], {"x": 1}, None, [[1]])

    def checker(self) -> Any:
        c = check_artifacts.Checker(self.root)
        c.tags = {CONTRACT.split("@")[0]: CONTRACT.split("@")[1]}
        return c

    def test_task_fields(self) -> None:
        original = self.read(f"{TASKS}/AO-P1-005.task.yaml")
        known = {f"AO-P1-00{i}" for i in range(1, 8)}
        for key in original:
            for bad in self.BAD:
                with self.subTest(key=key, bad=bad):
                    self.checker().check_task("t", {**original, key: bad}, "AO-P1-005", "1", known)

    def test_handoff_fields(self) -> None:
        tasks = {"AO-P1-005": self.read(f"{TASKS}/AO-P1-005.task.yaml")}
        for key in HANDOFF:
            for bad in self.BAD:
                with self.subTest(key=key, bad=bad):
                    self.checker().check_handoff("h", {**HANDOFF, key: bad}, "AO-P1-005", tasks)

    def test_handoff_nested_entries(self) -> None:
        tasks = {"AO-P1-005": self.read(f"{TASKS}/AO-P1-005.task.yaml")}
        for key in ("checks", "acceptance_criteria", "changes"):
            for field in ("id", "level", "ran", "result", "kind", "path", "met"):
                for bad in self.BAD:
                    with self.subTest(key=key, field=field, bad=bad):
                        data = copy.deepcopy(HANDOFF)
                        data[key][0][field] = bad
                        self.checker().check_handoff("h", data, "AO-P1-005", tasks)

    def test_weird_task_types(self) -> None:  # case weird_types
        self.write_text(f"{TASKS}/AO-P1-009.task.yaml", (
            "reviewers: {independent: {a: 1}, specialist: [[1]]}\nowner: x\n"
            "acceptance_criteria: [{id: [1]}, {id: {a: b}}]\n"
            "allocated_ids: {assumptions: [[1]], debt: {x: 1}}\n"
            "depends_on: [[1], {a: 1}]\nowned_paths: [[a], {b: 1}, 3]\n"
            "inputs: {frozen_contracts: [[1]], assumptions: x}\n"))
        self.assertFails("AO-P1-009.task.yaml")

    def test_alias_bomb(self) -> None:  # case alias_hostile
        self.write_text(f"{TASKS}/AO-P1-009.task.yaml",
                        "a: &a [x, x, x, x, x, x, x, x, x]\nb: &b [*a, *a, *a, *a, *a, *a, *a, *a, *a]\n"
                        "c: &c [*b, *b, *b, *b, *b, *b, *b, *b, *b]\ntask_id: *c\n")
        self.assertFails("AO-P1-009.task.yaml")


class ClaimRules(ArtifactCase):
    def setUp(self) -> None:
        super().setUp()
        # Explicit fixture claim: the live claims list changes as tasks merge.
        self.edit(STATE, lambda d: d.update(claims=[{
            "task": "AO-P1-005", "owner": "w4-governance-tooling",
            "paths": ["scripts/check-artifacts.py", "tests/governance/test_check_artifacts.py",
                      "tests/governance/test_workflow.py", "docs/phases/P1-tasks"]}]))

    def test_fixture_claim_passes(self) -> None:
        self.assertEqual(run_inprocess(self.root)[0], 0)

    def test_claim_for_unknown_task(self) -> None:
        self.edit(STATE, lambda d: d["claims"].append({"task": "AO-P1-008", "owner": "rogue", "paths": ["rogue"]}))
        self.assertFails("claim AO-P1-008: no task contract")

    def test_claim_owner_mismatch(self) -> None:
        self.edit(STATE, lambda d: next(c for c in d["claims"] if c["task"] == "AO-P1-005")
                  .update(owner="someone-else"))
        self.assertFails("claim AO-P1-005: owner 'someone-else' differs")

    def test_owned_path_outside_claim(self) -> None:
        self.task(lambda d: d["owned_paths"].append("scripts/check-governance.py"))
        self.assertFails("owned path 'scripts/check-governance.py' is outside the recorded claim")

    def test_claim_with_noncanonical_task_id(self) -> None:  # R-B-005-06 (case claim_P01)
        self.edit(STATE, lambda d: next(c for c in d["claims"] if c["task"] == "AO-P1-005")
                  .update(task="AO-P01-005"))
        self.assertFails("claim 'AO-P01-005': task must be a well-formed id")

    def test_weird_claims(self) -> None:  # case weird_claims
        self.edit(STATE, lambda d: d.update(
            claims=[[1], {"task": ["x"]}, {"task": "AO-P1-005", "owner": [1], "paths": {"a": 1}}]))
        self.assertFails("claim ['x']: task must be a well-formed id", "claim AO-P1-005: owner [1] differs")


class Subprocess(unittest.TestCase):
    """Real process: exit codes and no traceback."""

    def test_real_repository_passes(self) -> None:
        proc = run_subprocess()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS", proc.stdout)

    def test_failure_exit_code_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / TASKS).mkdir(parents=True)
            (root / TASKS / "AO-P1-001.task.yaml").write_text("task_id: [[[" + "\n", encoding="utf-8")
            (root / TASKS / "AO-P1-002.task.yaml").write_text("task_id: " + "[" * 5000 + "\n", encoding="utf-8")
            proc = run_subprocess("--root", tmp)
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 1, out)
        self.assertIn("FAIL", out)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("internal error", out)

    def test_usage_error_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_subprocess("--root", tmp)
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
