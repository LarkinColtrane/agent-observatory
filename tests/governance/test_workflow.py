"""Tests for .github/workflows/governance.yml against ADR-0005 section 5.

The ruleset requires one status check, `governance`. ADR-0005 makes that an
aggregator job so the single required check covers every job:

  (a) triggers include pull_request, with no workflow-level `paths` /
      `paths-ignore` filters (a filtered-out run leaves the check missing);
  (b) job `governance` lists every other job in `needs`, has `if: always()`,
      and fails unless EACH needs.<job>.result == 'success'. This is tested
      by behaviour, not by reading text: the aggregator must have a step whose
      env feeds `${{ toJSON(needs) }}`; its `run` script is executed with bash
      against synthetic needs and must exit 0 only when every job succeeded
      (each job failed / cancelled / skipped, and `{}`, must exit non-zero);
  (c) no `continue-on-error` anywhere (it turns a failed job into success);
  (d) default and job-level token permissions are read-only.

Until AO-P1-006 adds the application jobs, the workflow has exactly one job
named `governance`; only the aggregator assertion skips (with a message) in
that case. The other rules and the fixture tests always run.
Run: python3 -I -m unittest discover -s tests/governance -t . -v
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "governance.yml"
AGGREGATOR = "governance"
NON_SUCCESS = ("failure", "cancelled", "skipped")
READ_ONLY = {"read", "none"}
BASH = shutil.which("bash")


def _expr(value: Any) -> str:
    """Normalise a GitHub expression: drop ${{ }} and whitespace."""
    text = str(value).strip()
    m = re.fullmatch(r"\$\{\{(.*)\}\}", text, re.S)
    return re.sub(r"\s+", "", m.group(1) if m else text)


def triggers(wf: dict[Any, Any]) -> Any:
    # PyYAML (YAML 1.1) reads the bare key `on` as boolean True.
    return wf.get("on", wf.get(True))


def trigger_problems(wf: dict[Any, Any]) -> list[str]:
    on = triggers(wf)
    events = [on] if isinstance(on, str) else list(on) if isinstance(on, (list, dict)) else []
    problems = [] if "pull_request" in events else ["workflow must run on pull_request"]
    if isinstance(on, dict):
        problems += [f"workflow-level '{key}' filter on '{event}' (ADR-0005 section 5 forbids it)"
                     for event, cfg in on.items() if isinstance(cfg, dict)
                     for key in ("paths", "paths-ignore") if key in cfg]
    return problems


def _read_only(perms: Any) -> bool:
    if perms in ("read-all", {}):
        return True
    return isinstance(perms, dict) and all(level in READ_ONLY for level in perms.values())


def permission_problems(wf: dict[Any, Any]) -> list[str]:
    problems = [] if _read_only(wf.get("permissions")) else [
        f"top-level permissions must be read-only, got {wf.get('permissions')!r}"]
    for name, job in (wf.get("jobs") or {}).items():
        if isinstance(job, dict) and "permissions" in job and not _read_only(job["permissions"]):
            problems.append(f"job '{name}' permissions must be read-only, got {job['permissions']!r}")
    return problems


def continue_on_error_problems(wf: dict[Any, Any]) -> list[str]:
    problems = []
    for name, job in (wf.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        if "continue-on-error" in job:
            problems.append(f"job '{name}' sets continue-on-error")
        for i, step in enumerate(job.get("steps") or []):
            if isinstance(step, dict) and "continue-on-error" in step:
                problems.append(f"job '{name}' step {i} sets continue-on-error")
    return problems


def run_needs_step(step: dict[str, Any], var: str, needs: dict[str, Any]) -> int:
    """Execute the step's bash `run` like a runner would, with NEEDS fed via env."""
    shell = step.get("shell")
    flags = ["-e"] if shell is None else ["--noprofile", "--norc", "-eo", "pipefail"]
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "step.sh"
        script.write_text(step["run"], encoding="utf-8")
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), var: json.dumps(needs)}
        proc = subprocess.run([BASH or "bash", *flags, str(script)], cwd=tmp, env=env,
                              capture_output=True, text=True, timeout=30, check=False)
    return proc.returncode


def needs_step_problems(step: Any, jobs: list[str]) -> list[str]:
    """Problems with one candidate aggregator step; [] means it enforces success-only."""
    if not isinstance(step, dict) or not isinstance(step.get("env"), dict):
        return ["no env"]
    var = next((k for k, v in step["env"].items() if _expr(v).lower() == "tojson(needs)"), None)
    if var is None:
        return ["env does not feed ${{ toJSON(needs) }}"]
    if not isinstance(step.get("run"), str) or "uses" in step:
        return ["step has no run script"]
    if step.get("if") is not None and _expr(step["if"]) not in ("always()", "success()"):
        return [f"step is conditional ({step['if']!r})"]
    if step.get("shell") not in (None, "bash"):
        return [f"step shell must be bash, got {step['shell']!r}"]
    if "${{" in step["run"] or any("${{" in str(v) for k, v in step["env"].items() if k != var):
        return ["step uses other expressions; it cannot be evaluated faithfully"]

    def needs(results: dict[str, str]) -> dict[str, Any]:
        return {j: {"result": r, "outputs": {}} for j, r in results.items()}

    problems = []
    if run_needs_step(step, var, needs({j: "success" for j in jobs})) != 0:
        problems.append("exits non-zero when every job succeeded")
    if run_needs_step(step, var, {}) == 0:
        problems.append("exits 0 for empty needs {}")
    for job in jobs:
        for result in NON_SUCCESS:
            if run_needs_step(step, var, needs({j: result if j == job else "success" for j in jobs})) == 0:
                problems.append(f"exits 0 when {job} is {result}")
    return problems


def aggregator_problems(wf: dict[Any, Any]) -> list[str]:
    jobs = wf.get("jobs")
    if not isinstance(jobs, dict) or not isinstance(jobs.get(AGGREGATOR), dict):
        return [f"no job named '{AGGREGATOR}'"]
    agg = jobs[AGGREGATOR]
    others = sorted(j for j in jobs if j != AGGREGATOR)
    problems: list[str] = []
    needs = agg.get("needs", [])
    needs = [needs] if isinstance(needs, str) else needs if isinstance(needs, list) else []
    if missing := sorted(set(others) - set(needs)):
        problems.append(f"aggregator needs is missing job(s) {missing}")
    if unknown := sorted(set(needs) - set(others)):
        problems.append(f"aggregator needs names unknown job(s) {unknown}")
    if _expr(agg.get("if", "")) != "always()":
        problems.append(f"aggregator must have exactly 'if: always()', got {agg.get('if')!r}")
    findings = [needs_step_problems(step, others) for step in agg.get("steps") or []]
    if not any(f == [] for f in findings):
        detail = "; ".join(", ".join(f) for f in findings) or "no steps"
        problems.append("aggregator has no step that fails unless every needs.<job>.result == 'success' "
                        f"(toJSON(needs) step, executed): {detail}")
    return problems


def all_problems(wf: dict[Any, Any]) -> list[str]:
    return (trigger_problems(wf) + permission_problems(wf) + continue_on_error_problems(wf)
            + aggregator_problems(wf))


def load(path: Path = WORKFLOW) -> dict[Any, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path} is not a mapping"
    return data


class RealWorkflow(unittest.TestCase):
    def setUp(self) -> None:
        self.wf = load()

    def test_triggers(self) -> None:
        self.assertEqual(trigger_problems(self.wf), [])

    def test_permissions_read_only(self) -> None:
        self.assertEqual(permission_problems(self.wf), [])

    def test_no_continue_on_error(self) -> None:
        self.assertEqual(continue_on_error_problems(self.wf), [])

    def test_aggregator_rule(self) -> None:
        if list(self.wf.get("jobs") or {}) == [AGGREGATOR]:
            self.skipTest("pre-aggregation: governance.yml has a single 'governance' job; the ADR-0005 "
                          "section 5 aggregator assertions apply once AO-P1-006 adds the other jobs")
        self.assertEqual(aggregator_problems(self.wf), [])


JOBS = ["governance-core", "backend", "backend-integration", "frontend", "containers"]
# Same shape as the AO-P1-006 aggregator step: bash heredoc running python3 -I -.
GOOD_RUN = """python3 -I - <<'PY'
import json, os, sys
needs = json.loads(os.environ["NEEDS_JSON"])
bad = {job: v.get("result") for job, v in needs.items() if v.get("result") != "success"}
if not needs or bad:
    print(f"FAIL: not successful: {bad or 'no jobs'}")
    sys.exit(1)
print("OK")
PY
"""


def fixture(on: Any = None, **changes: Any) -> dict[Any, Any]:
    """A valid aggregated workflow in the ADR-0005 shape, with overrides."""
    wf: dict[Any, Any] = {
        "name": "governance",
        True: on if on is not None else {"pull_request": None, "push": {"branches": ["main"]}},
        "permissions": {"contents": "read"},
        "jobs": {j: {"runs-on": "ubuntu-24.04", "steps": [{"run": "true"}]} for j in JOBS},
    }
    wf["jobs"][AGGREGATOR] = {
        "if": "always()",
        "needs": list(JOBS),
        "runs-on": "ubuntu-24.04",
        "steps": [{"name": "Every required job succeeded",
                   "env": {"NEEDS_JSON": "${{ toJSON(needs) }}"}, "run": GOOD_RUN}],
    }
    wf.update(changes)
    return wf


def agg_steps(wf: dict[Any, Any], steps: list[dict[str, Any]]) -> dict[Any, Any]:
    wf["jobs"][AGGREGATOR]["steps"] = steps
    return wf


def tojson_step(run: str, **extra: Any) -> dict[str, Any]:
    return {"env": {"NEEDS_JSON": "${{ toJSON(needs) }}"}, "run": run, **extra}


@unittest.skipIf(BASH is None, "bash is required to execute the aggregator step")
class Fixtures(unittest.TestCase):
    """The rule checks themselves: the valid shape passes, each breakage is caught."""

    def assertAggregatorRejected(self, wf: dict[Any, Any]) -> None:
        problems = aggregator_problems(wf)
        self.assertTrue(any("no step that fails unless" in p for p in problems), problems)

    def test_valid_fixture_passes(self) -> None:
        self.assertEqual(all_problems(fixture()), [])

    def test_failure_detail_names_job_and_result(self) -> None:
        wf = agg_steps(fixture(), [tojson_step(GOOD_RUN.replace('if not needs or bad', 'if not needs'))])
        problems = aggregator_problems(wf)
        self.assertTrue(any("exits 0 when backend is cancelled" in p for p in problems), problems)

    # Reviewer B probes C1-C5 (R-B-005-01): all must be rejected.
    def test_c1_tojson_printed_never_compared(self) -> None:
        self.assertAggregatorRejected(agg_steps(fixture(), [tojson_step("echo \"$NEEDS_JSON\"; echo success")]))

    def test_c2_per_job_script_never_fails(self) -> None:
        run = "\n".join(f'[ "${{{{ needs.{j}.result }}}}" = "success" ] || true' for j in JOBS)
        self.assertAggregatorRejected(agg_steps(fixture(), [{"run": run}]))

    def test_c3_gate_neutralised(self) -> None:
        self.assertAggregatorRejected(agg_steps(fixture(), [
            {"if": f"needs.{j}.result != 'success' && false", "run": "exit 1"} for j in JOBS]))

    def test_c4_exit_only_in_echo(self) -> None:
        self.assertAggregatorRejected(agg_steps(fixture(), [
            {"if": f"needs.{j}.result != 'success'", "run": "echo would exit 1 here"} for j in JOBS]))

    def test_c5_negated_contains(self) -> None:
        cond = "!(" + " || ".join(f"contains(needs.*.result, '{r}')" for r in NON_SUCCESS) + ")"
        self.assertAggregatorRejected(agg_steps(fixture(), [{"if": cond, "run": "exit 1"}]))

    def test_contains_failure_only_rejected(self) -> None:
        self.assertAggregatorRejected(agg_steps(fixture(), [
            {"if": "${{ contains(needs.*.result, 'failure') }}", "run": "exit 1"}]))

    def test_tojson_check_missing_cancelled_rejected(self) -> None:
        run = GOOD_RUN.replace('!= "success"', 'in ("failure", "skipped")')
        self.assertAggregatorRejected(agg_steps(fixture(), [tojson_step(run)]))

    def test_tojson_check_accepting_empty_needs_rejected(self) -> None:
        self.assertAggregatorRejected(agg_steps(fixture(), [tojson_step(GOOD_RUN.replace("not needs or ", ""))]))

    def test_tojson_step_conditional_rejected(self) -> None:
        self.assertAggregatorRejected(agg_steps(fixture(), [tojson_step(GOOD_RUN, **{"if": "failure()"})]))

    def test_tojson_step_with_other_expressions_rejected(self) -> None:
        self.assertAggregatorRejected(agg_steps(fixture(), [tojson_step("[ '${{ github.ref }}' ] && " + GOOD_RUN)]))

    # R-B-005-02: continue-on-error anywhere.
    def test_member_job_continue_on_error_rejected(self) -> None:  # probe C6
        wf = fixture()
        wf["jobs"]["backend"]["continue-on-error"] = True
        self.assertEqual(continue_on_error_problems(wf), ["job 'backend' sets continue-on-error"])

    def test_step_continue_on_error_rejected(self) -> None:
        wf = fixture()
        wf["jobs"][AGGREGATOR]["steps"][0]["continue-on-error"] = True
        self.assertEqual(continue_on_error_problems(wf), ["job 'governance' step 0 sets continue-on-error"])

    def test_missing_job_in_needs_rejected(self) -> None:
        wf = fixture()
        wf["jobs"][AGGREGATOR]["needs"].remove("backend-integration")
        self.assertIn("aggregator needs is missing job(s) ['backend-integration']", aggregator_problems(wf))

    def test_new_job_not_in_needs_rejected(self) -> None:
        wf = fixture()
        wf["jobs"]["docs"] = {"runs-on": "ubuntu-24.04", "steps": [{"run": "true"}]}
        self.assertIn("aggregator needs is missing job(s) ['docs']", aggregator_problems(wf))

    def test_missing_or_weakened_always_rejected(self) -> None:
        for value in (None, "success()", "always() && github.event_name == 'push'"):
            with self.subTest(value=value):
                wf = fixture()
                wf["jobs"][AGGREGATOR]["if"] = value
                self.assertTrue(any("if: always()" in p for p in aggregator_problems(wf)))

    def test_aggregator_absent_rejected(self) -> None:
        wf = fixture()
        del wf["jobs"][AGGREGATOR]
        self.assertEqual(aggregator_problems(wf), [f"no job named '{AGGREGATOR}'"])

    def test_workflow_level_path_filters_rejected(self) -> None:
        self.assertEqual(trigger_problems(fixture(on={"pull_request": {"paths": ["backend/**"]}})),
                         ["workflow-level 'paths' filter on 'pull_request' (ADR-0005 section 5 forbids it)"])
        self.assertTrue(trigger_problems(fixture(on={"pull_request": {"paths-ignore": ["docs/**"]}})))

    def test_no_pull_request_trigger_rejected(self) -> None:  # probe C9
        self.assertEqual(trigger_problems(fixture(on={"workflow_dispatch": None})),
                         ["workflow must run on pull_request"])

    def test_write_permissions_rejected(self) -> None:  # incl. probe C10
        self.assertTrue(permission_problems(fixture(permissions={"contents": "write"})))
        self.assertTrue(permission_problems(fixture(permissions="write-all")))
        wf = fixture()
        del wf["permissions"]
        self.assertTrue(permission_problems(wf))
        wf = fixture()
        wf["jobs"]["backend"]["permissions"] = {"contents": "write"}
        self.assertEqual(permission_problems(wf), ["job 'backend' permissions must be read-only, "
                                                   "got {'contents': 'write'}"])

    def test_deliberately_broken_workflow_rejected(self) -> None:
        """Missing a job in needs + no if: always() + workflow-level paths filter."""
        wf = fixture(on={"pull_request": {"paths": ["backend/**"]}})
        wf["jobs"][AGGREGATOR]["needs"].remove("frontend")
        del wf["jobs"][AGGREGATOR]["if"]
        problems = all_problems(wf)
        self.assertEqual(len(problems), 3, problems)
        self.assertTrue(any("'paths'" in p for p in problems))
        self.assertTrue(any("['frontend']" in p for p in problems))
        self.assertTrue(any("if: always()" in p for p in problems))

    def test_yaml_on_key_parsed_as_boolean(self) -> None:
        wf = yaml.safe_load("on:\n  pull_request:\n    paths: [x]\njobs: {}\n")
        self.assertTrue(any("'paths'" in p for p in trigger_problems(wf)))


if __name__ == "__main__":
    unittest.main()
