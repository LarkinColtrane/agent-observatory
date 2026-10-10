"""Adversarial tests for scripts/check-governance.py.

Each test copies the real governance baseline into a throwaway git repository,
breaks one thing, and asserts the checker FAILS with a specific message and
without a traceback. One test asserts the unmodified baseline passes, so the
negative tests are meaningful (a checker that always fails would not pass it).

Synthetic secrets are assembled at runtime so this file itself contains no
matching literals. Run: python3 -I -m unittest discover -s tests/governance -t . -v
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable

import yaml

class _IndentedDumper(yaml.SafeDumper):
    """Indent sequences like the hand-written state file, so text-based
    fixture edits keep matching after a YAML round-trip."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        super().increase_indent(flow, False)


REPO = Path(__file__).resolve().parents[2]
REAL_REMOTE = "https://github.com/LarkinColtrane/agent-observatory.git"
CHECKER = REPO / "scripts" / "check-governance.py"
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
    "HOME": tempfile.gettempdir(),
}

# Synthetic secret material, built so no literal in this file matches a pattern.
FAKE = {
    "aws": "AKIA" + "Q7" * 8,
    "github_pat": "github_" + "pat_" + "A1b2C3d4" * 6,
    "cred_url": "postgres://admin:" + "hunter2pw" + "@db.internal:5432/app",
    "jwt": "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0" + "." + "c2lnbmF0dXJlX3ZhbHVlX2hlcmU",
    "slack_webhook": "https://hooks.slack.com/" + "services/" + "T0000000/B0000000/" + "X" * 24,
    "google": "AIza" + "Sy" + "D" * 33,
    "generic": "api_key" + " = " + "'" + "Zx9" * 6 + "'",
}


class CheckerCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="gov-test-"))
        for item in ("docs", "scripts", ".gitignore"):
            src = REPO / item
            if src.is_dir():
                shutil.copytree(src, self.tmp / item)
            else:
                shutil.copy2(src, self.tmp / item)
        self.git("init", "-q", "-b", "main")
        # Mirror the real repository: a dedicated repo has its GitHub remote.
        if re.search(r"^\s*dedicated:\s*true", (self.tmp / "docs/governance-state.yaml").read_text(), re.M):
            self.git("remote", "add", "origin", REAL_REMOTE)
        self.commit("baseline")
        # Mirror the real repository's recorded P0 gate tag (annotated) when P0 is closed.
        m = re.search(r"^\s*gate_tag:\s*(phase-P0-v[\d.]+)", (self.tmp / "docs/governance-state.yaml").read_text(), re.M)
        if m:
            self.git("tag", "-a", m.group(1), "-m", "mirror of the real gate tag")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------------------------------------------------------- helpers

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.tmp), *args], check=True, env=GIT_ENV, capture_output=True)

    def commit(self, msg: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)

    def path(self, rel: str) -> Path:
        return self.tmp / rel

    def set_dedicated(self, dedicated: bool) -> None:
        """Set repository.dedicated and the matching remote, independent of
        the real repository's current state."""
        st = self.path("docs/governance-state.yaml")
        st.write_text(re.sub(r"^(\s*dedicated:\s*)(true|false)", rf"\g<1>{str(dedicated).lower()}", st.read_text(), count=1, flags=re.M))
        subprocess.run(["git", "-C", str(self.tmp), "remote", "remove", "origin"], env=GIT_ENV, capture_output=True)
        if dedicated:
            self.git("remote", "add", "origin", REAL_REMOTE)

    def update_state(self, fn: Callable[[dict[str, Any]], None]) -> None:
        """Edit docs/governance-state.yaml structurally (not by string match),
        so fixtures do not depend on how the live file is formatted."""
        st = self.path("docs/governance-state.yaml")
        data = yaml.safe_load(st.read_text())
        fn(data)
        st.write_text(yaml.dump(data, Dumper=_IndentedDumper, sort_keys=False, default_flow_style=False))

    def set_phase(self, pid: str, **fields: Any) -> None:
        def apply(d: dict[str, Any]) -> None:
            next(p for p in d["phases"] if p["id"] == pid).update(fields)
        self.update_state(apply)

    def set_claims(self, claims: list[dict[str, Any]]) -> None:
        self.update_state(lambda d: d.__setitem__("claims", claims))

    def edit(self, rel: str, old: str, new: str, count: int = 1) -> None:
        p = self.path(rel)
        text = p.read_text()
        self.assertIn(old, text, f"fixture drift: {old!r} not in {rel}")
        p.write_text(text.replace(old, new, count))

    def run_checker(self, root: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-I", str(CHECKER), "--root", str(root or self.tmp)],
            capture_output=True,
            text=True,
            env=GIT_ENV,
        )

    def assertFails(self, *expected: str) -> str:
        res = self.run_checker()
        out = res.stdout + res.stderr
        self.assertEqual(res.returncode, 1, f"expected FAIL (rc=1), got rc={res.returncode}:\n{out}")
        self.assertNotIn("Traceback", out)
        self.assertNotIn("internal error", out, "checker crashed instead of reporting a finding")
        for e in expected:
            self.assertRegex(out, e)
        return out


class TestBaseline(CheckerCase):
    def test_unmodified_baseline_passes(self) -> None:
        res = self.run_checker()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("PASS", res.stdout)
        self.assertRegex(res.stdout, r"register counts: assumptions=\d+, debt=\d+")


class TestRequiredFiles(CheckerCase):
    def test_missing_required_governance_file(self) -> None:
        self.path("docs/rollback-policy.md").unlink()
        self.assertFails(r"missing required file: docs/rollback-policy\.md")

    def test_missing_adr(self) -> None:
        self.path("docs/adr/0001-adopt-development-operating-system.md").unlink()
        self.assertFails(r"missing required file: docs/adr/0001", r"lists missing ADR 0001")

    def test_missing_docs_dir_is_usage_error(self) -> None:
        shutil.rmtree(self.path("docs"))
        res = self.run_checker()
        self.assertEqual(res.returncode, 2)
        self.assertNotIn("Traceback", res.stderr)


class TestRegisters(CheckerCase):
    def test_invalid_yaml_syntax(self) -> None:
        self.path("docs/assumptions.yaml").write_text("assumptions: [\n  - id: A-001\n")
        self.assertFails(r"docs/assumptions\.yaml: invalid YAML")

    def test_top_level_list_is_clean_failure(self) -> None:
        self.path("docs/assumptions.yaml").write_text("- id: A-001\n")
        self.assertFails(r"docs/assumptions\.yaml: top level must be a mapping")

    def test_scalar_entry_is_clean_failure(self) -> None:
        self.edit("docs/technical-debt.yaml", "debt:\n", "debt:\n  - just-a-string\n")
        self.assertFails(r"debt\[0\] must be a mapping")

    def test_empty_register(self) -> None:
        self.path("docs/technical-debt.yaml").write_text("schema_version: 2\ndebt: []\n")
        self.assertFails(r"'debt' must be a non-empty list")

    def test_duplicate_id(self) -> None:
        self.edit("docs/assumptions.yaml", "id: A-002", "id: A-001")
        self.assertFails(r"duplicate id A-001")

    def test_malformed_id(self) -> None:
        self.edit("docs/technical-debt.yaml", "id: TD-005", "id: debt5")
        self.assertFails(r"id missing or malformed")

    def test_invalid_enums(self) -> None:
        self.edit("docs/assumptions.yaml", "confidence: medium", "confidence: banana")
        self.edit("docs/technical-debt.yaml", "severity: low\n    status: accepted", "severity: catastrophic\n    status: accepted")
        self.assertFails(r"'confidence' must be one of", r"'severity' must be one of")

    def test_empty_required_text(self) -> None:
        self.edit("docs/assumptions.yaml", "owner: coordinator", 'owner: ""')
        self.edit("docs/technical-debt.yaml", "repayment_trigger: When a contributor", "repayment_trigger: null\n    x: When a contributor")
        self.assertFails(r"'owner' must be non-empty text", r"'repayment_trigger' must be non-empty text")

    def test_unknown_component_reference(self) -> None:
        self.edit("docs/assumptions.yaml", "affects: [C5, C6]", "affects: [C99, TD-777]")
        self.edit("docs/technical-debt.yaml", "component: C11", "component: C42")
        self.assertFails(r"unknown component 'C99'", r"unknown component 'C42'")

    def test_invalid_review_phase_and_blocks(self) -> None:
        self.edit("docs/assumptions.yaml", "review_phase: P4", "review_phase: P99")
        self.edit("docs/technical-debt.yaml", "blocks: []", "blocks: [Phase1]")
        self.assertFails(r"'review_phase' must be a phase id", r"'blocks' must be a list of phase ids")


class TestGovernanceState(CheckerCase):
    STATE = "docs/governance-state.yaml"

    def test_phase_reorder_rejected(self) -> None:
        self.edit(self.STATE, "{id: P2, name: Universal agent event protocol,", "{id: P2, name: Adapter / SDK layer,")
        self.assertFails(r"canonical order and names")

    def test_unknown_phase_status(self) -> None:
        self.edit(self.STATE, "{id: P3, name: Adapter / SDK layer, status: not_started", "{id: P3, name: Adapter / SDK layer, status: wibble")
        self.assertFails(r"phase P3: invalid status 'wibble'")

    def test_phase_cannot_start_before_predecessor_closed(self) -> None:
        self.edit(self.STATE, "{id: P2, name: Universal agent event protocol, status: not_started", "{id: P2, name: Universal agent event protocol, status: in_progress")
        self.set_phase("P1", status="not_started")
        self.assertFails(r"phase P2: is 'in_progress' but P1 is not closed")
        self.set_phase("P1", status="in_progress")
        self.assertFails(r"more than one phase active")

    def test_p1_cannot_start_outside_dedicated_repo(self) -> None:
        self.set_dedicated(False)
        self.make_p1_blocker()
        self.set_phase("P1", status="in_progress")
        self.assertFails(r"cannot start while the project is not in its dedicated repository", r"while blocked by open debt TD-006")

    def test_closed_with_unrun_gate_item_rejected(self) -> None:
        # Regression for review findings B-01 / A-01 ("closed with exception").
        self.reopen_p0()
        self.edit(self.STATE, "    status: gate_review\n", "    status: closed\n")
        self.edit(self.STATE, "gate_tag: null", "gate_tag: phase-P0-v1.1.0")
        self.assertFails(r"phase P0: closed but gate item 12 is 'not_run'")

    def test_closed_without_tag_rejected(self) -> None:
        self.reopen_p0()
        self.edit(self.STATE, "    status: gate_review\n", "    status: closed\n")
        self.assertFails(r"phase P0: closed without a gate_tag of the form phase-P0-v<semver>")

    def pending_review(self) -> None:
        """Reset the copied records to the pre-verdict state, so tests do not
        depend on whatever review state the real repository has recorded."""
        rec = self.path("docs/reviews/pre-phase-1-review-resolution.md")
        text = rec.read_text()
        marker = "<!-- final-verdicts -->"
        self.assertIn(marker, text)
        rec.write_text(text.split(marker, 1)[0] + marker + "\n")
        st = self.path(self.STATE)
        st.write_text(st.read_text().replace("    status: approved\n    reviewed_by: [reviewer-a, reviewer-b]",
                                             "    status: in_review\n    reviewed_by: []"))
        self.set_gate_row(10, "no", "not_run")

    def record_verdicts(self, a: str, b: str) -> None:
        rec = self.path("docs/reviews/pre-phase-1-review-resolution.md")
        rec.write_text(rec.read_text() + f"\n- **Reviewer A final outcome:** {a}\n- **Reviewer B final outcome:** {b}\n")

    def set_gate_row(self, item: int, ran: str, result: str) -> None:
        report = self.path("docs/phases/P0-gate-report.md")
        new, n = re.subn(rf"^(\|\s*{item}\s*\|[^|]*\|[^|]*\|)\s*\w+\s*\|\s*\w+\s*\|", rf"\1 {ran} | {result} |",
                         report.read_text(), count=1, flags=re.M)
        self.assertEqual(n, 1, f"fixture drift: gate row {item}")
        report.write_text(new)

    def make_p1_blocker(self, debt_id: str = "TD-006", recorded_in_state: bool = True) -> None:
        """Make an open debt item block P1 inside the fixture only, so tests do
        not depend on whether the real register currently blocks P1."""
        reg = self.path("docs/technical-debt.yaml")
        text = reg.read_text()
        start = text.index(f"  - id: {debt_id}\n")
        end = text.find("\n  - id: ", start + 1)
        end = len(text) if end == -1 else end
        block = text[start:end]
        self.assertIn("    status: open\n", block, f"fixture drift: {debt_id} not open")
        reg.write_text(text[:start] + re.sub(r"(?m)^    blocks: \[.*\]$", "    blocks: [P1]", block, count=1) + text[end:])
        self.set_phase("P1", blocked_by=[debt_id] if recorded_in_state else [])

    def reopen_p0(self) -> None:
        """Return P0 to gate_review (tag removed, item 12 not_run), so closure
        tests exercise the path to closure regardless of the real state."""
        st = self.path(self.STATE)
        text = st.read_text().replace("    status: closed\n    plan: docs/phases/P0-plan.md", "    status: gate_review\n    plan: docs/phases/P0-plan.md", 1)
        st.write_text(re.sub(r"^(\s*gate_tag:).*$", r"\1 null", text, count=1, flags=re.M))
        self.set_gate_row(12, "no", "not_run")
        subprocess.run(["git", "-C", str(self.tmp), "tag", "-d", "phase-P0-v1.1.0"], env=GIT_ENV, capture_output=True)

    def close_p0(self, tag: str = "phase-P0-v1.1.0") -> None:
        self.set_gate_row(10, "yes", "pass")
        self.set_gate_row(12, "yes", "pass")
        self.edit(self.STATE, "    status: gate_review\n", "    status: closed\n")
        self.edit(self.STATE, "gate_tag: null", f"gate_tag: {tag}")

    def test_review_pass_without_recorded_verdicts(self) -> None:
        # Regression for N-01 / B-16.
        self.pending_review()
        self.set_gate_row(10, "yes", "pass")
        self.assertFails(r"phase P0: gate item 10 is 'pass' but no recorded final verdict")

    def test_closed_with_nonexistent_tag(self) -> None:
        # Regression for B-19 / N-05 (s1): self-attested closure.
        self.reopen_p0()
        self.pending_review()
        self.record_verdicts("APPROVE", "APPROVE")
        self.close_p0()
        self.assertFails(r"gate_tag 'phase-P0-v1\.1\.0' does not exist as an annotated git tag")

    def test_closed_with_lightweight_tag(self) -> None:
        self.reopen_p0()
        self.pending_review()
        self.record_verdicts("APPROVE", "APPROVE")
        self.close_p0()
        self.git("tag", "phase-P0-v1.1.0")
        self.assertFails(r"does not exist as an annotated git tag")

    def make_dedicated(self) -> None:
        self.set_dedicated(True)

    def test_legitimate_closure_passes(self) -> None:
        # Control: the rules are satisfiable (no deadlock) when evidence is real,
        # following the documented closure sequence.
        self.reopen_p0()
        self.pending_review()
        self.record_verdicts("REQUEST_CHANGES", "REQUEST_CHANGES")
        self.record_verdicts("APPROVE", "APPROVE_WITH_NOTES")
        self.make_dedicated()
        self.commit("gate commit")
        self.git("tag", "-a", "phase-P0-v1.1.0", "-m", "P0")
        self.close_p0()
        self.commit("record closure")
        res = self.run_checker()
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_closed_outside_dedicated_repository(self) -> None:
        self.reopen_p0()
        self.set_dedicated(False)
        # Regression for B-24 (N1): local annotated tag in the practice repo.
        self.pending_review()
        self.record_verdicts("APPROVE", "APPROVE")
        self.git("tag", "-a", "phase-P0-v1.1.0", "-m", "P0")
        self.close_p0()
        self.assertFails(r"phase P0: cannot be closed outside the dedicated repository")

    def test_gate_tag_must_be_ancestor_of_head(self) -> None:
        self.reopen_p0()
        self.pending_review()
        self.record_verdicts("APPROVE", "APPROVE")
        self.make_dedicated()
        self.commit("prepared")  # keep the reopened state on main across branch switches
        self.git("checkout", "-q", "--orphan", "elsewhere")
        self.commit("unrelated")
        self.git("tag", "-a", "phase-P0-v1.1.0", "-m", "P0")
        self.git("checkout", "-q", "main")
        self.close_p0()
        self.assertFails(r"gate_tag 'phase-P0-v1\.1\.0' is not an ancestor of HEAD")

    def test_verdicts_in_html_comment_or_fence_ignored(self) -> None:
        # Regression for B-23 (N1/N3).
        self.pending_review()
        rec = self.path("docs/reviews/pre-phase-1-review-resolution.md")
        rec.write_text(rec.read_text() + "\n<!--\n- **Reviewer A final outcome:** APPROVE\n-->\n"
                       "```\n- **Reviewer B final outcome:** APPROVE\n```\n")
        self.set_gate_row(10, "yes", "pass")
        self.assertFails(r"no recorded final verdict from \['reviewer-a', 'reviewer-b'\]")

    def test_verdicts_before_marker_ignored(self) -> None:
        self.pending_review()
        rec = self.path("docs/reviews/pre-phase-1-review-resolution.md")
        rec.write_text("- **Reviewer A final outcome:** APPROVE\n- **Reviewer B final outcome:** APPROVE\n" + rec.read_text())
        self.set_gate_row(10, "yes", "pass")
        self.assertFails(r"no recorded final verdict")

    def test_review_record_outside_reviews_dir(self) -> None:
        # Regression for B-23 (N2/N3).
        self.pending_review()
        for bad in ("/etc/hostname", "docs/adr/0000-template.md", "docs/reviews/../adr/0000-template.md"):
            with self.subTest(record=bad):
                st = self.path(self.STATE)
                original = st.read_text()
                st.write_text(original.replace("    review_record: docs/reviews/pre-phase-1-review-resolution.md\n", f"    review_record: {bad}\n", 1))
                self.set_gate_row(10, "yes", "pass")
                self.assertFails(r"must be an existing file under docs/reviews/")
                st.write_text(original)

    def test_fake_table_above_early_superseded_heading(self) -> None:
        # Regression for B-19 (b5): a second "Superseded runs" heading hides the real table.
        report = self.path("docs/phases/P0-gate-report.md")
        report.write_text(report.read_text().replace("| # | Check |", "## Superseded runs\n\n| # | Check |", 1))
        self.assertFails(r"'Superseded runs' heading appears more than once")

    def test_dedicated_repository_requires_matching_remote(self) -> None:
        # Regression for B-19 / N-05 (s2/b6).
        self.set_dedicated(True)
        self.git("remote", "remove", "origin")
        self.assertFails(r"no git remote points at 'LarkinColtrane/agent-observatory'")
        self.git("remote", "add", "origin", "https://example.invalid/evil/agent-observatory.git")
        self.assertFails(r"no git remote points at 'LarkinColtrane/agent-observatory'")  # B-24 (N4)
        for bad in ("https://evil.example.invalid/github.com/LarkinColtrane/agent-observatory.git",  # N4b
                    "https://github.com/LarkinColtrane/agent-observatory-fork.git"):
            self.git("remote", "set-url", "origin", bad)
            self.assertFails(r"no git remote points at 'LarkinColtrane/agent-observatory'")
        self.git("remote", "set-url", "origin", "https://github.com/LarkinColtrane/agent-observatory.git")
        out = self.run_checker().stdout
        self.assertNotIn("no git remote points", out)

    def test_unapproved_not_applicable(self) -> None:
        self.edit(self.STATE, "approved_not_applicable: [1, 3, 4, 6, 7, 9]", "approved_not_applicable: [1, 3, 4, 6, 7]")
        self.assertFails(r"gate item 9 is not_applicable without plan approval")

    def test_invalid_ran_result_combination(self) -> None:
        self.reopen_p0()
        report = self.path("docs/phases/P0-gate-report.md")
        text = report.read_text()
        # Edit only the current run's row (superseded runs keep older tables).
        new, n = re.subn(r"^(\|\s*12\s*\|.*?\|.*?\|)\s*no\s*\|\s*not_run\s*\|", r"\1 no | pass |", text, count=1, flags=re.M)
        self.assertEqual(n, 1, "fixture drift: gate row 12 not found")
        report.write_text(new)
        self.assertFails(r"item 12: invalid \(ran=no, result=pass\)")

    def test_gate_report_missing(self) -> None:
        self.path("docs/phases/P0-gate-report.md").unlink()
        self.assertFails(r"gate report missing")

    def test_gate_report_missing_row(self) -> None:
        report = self.path("docs/phases/P0-gate-report.md")
        report.write_text(re.sub(r"^\|\s*10\s*\|.*\n", "", report.read_text(), count=1, flags=re.M))
        self.assertFails(r"gate items missing: \[10\]")

    def test_open_blocking_debt_missing_from_blocked_by(self) -> None:
        self.make_p1_blocker(recorded_in_state=False)
        self.assertFails(r"phase P1: open debt TD-006 blocks it but is not in blocked_by")

    def test_blocked_by_repaid_or_unknown_debt(self) -> None:
        self.make_p1_blocker()
        self.set_phase("P1", blocked_by=["TD-006", "TD-003", "TD-999"])
        self.assertFails(r"blocked_by 'TD-003' is not open debt", r"unknown debt 'TD-999'")

    def test_event_protocol_cannot_be_drafted_before_p2(self) -> None:
        self.edit(self.STATE, "  - id: event-protocol\n    path: null\n    version: null\n    status: not_drafted",
                  "  - id: event-protocol\n    path: docs/roadmap.md\n    version: 1.0.0\n    status: frozen\n    reviewed_by: [reviewer-a, reviewer-b]")
        self.assertFails(r"contract event-protocol: is 'frozen' but may not be drafted before P2 starts")

    def approve_contract(self, cid: str = "task-contract", status: str = "approved") -> None:
        block = self.path(self.STATE).read_text()
        anchor = f"  - id: {cid}\n"
        i = block.index(anchor)
        j = block.index("    tag: null\n", i)
        seg = block[i:j].replace("status: in_review", f"status: {status}").replace("reviewed_by: []", "reviewed_by: [reviewer-a, reviewer-b]")
        self.path(self.STATE).write_text(block[:i] + seg + block[j:])

    def test_contract_review_claimed_without_recorded_verdicts(self) -> None:
        # Regression for N-01 / B-16: review recorded before it happened.
        self.pending_review()
        self.approve_contract()
        self.assertFails(r"contract task-contract: claims review but no recorded final verdict")

    def test_contract_review_with_rejecting_latest_verdict(self) -> None:
        self.pending_review()
        self.approve_contract()
        self.record_verdicts("APPROVE", "APPROVE")
        self.record_verdicts("APPROVE", "REQUEST_CHANGES")  # latest wins
        self.assertFails(r"latest verdicts are not approvals: \['reviewer-b=REQUEST_CHANGES'\]")

    def test_approved_contract_requires_existing_path(self) -> None:
        self.pending_review()
        self.record_verdicts("APPROVE", "APPROVE_WITH_NOTES")
        self.approve_contract()
        self.edit(self.STATE, "path: docs/agent-task-contract.md", "path: docs/does-not-exist.md")
        self.assertFails(r"contract task-contract: approved but path 'docs/does-not-exist\.md' does not exist")

    def test_approved_contract_requires_both_reviewers(self) -> None:
        self.pending_review()
        self.record_verdicts("APPROVE", "APPROVE")
        self.edit(self.STATE, "    status: in_review\n    reviewed_by: []", "    status: approved\n    reviewed_by: [reviewer-a]")
        self.assertFails(r"contract operating-contract: 'approved' without review by both reviewers")

    def test_frozen_contract_requires_existing_annotated_tag(self) -> None:
        self.pending_review()
        self.record_verdicts("APPROVE", "APPROVE")
        self.approve_contract(status="frozen")
        self.edit(self.STATE, "status: frozen\n    reviewed_by: [reviewer-a, reviewer-b]\n    tag: null",
                  "status: frozen\n    reviewed_by: [reviewer-a, reviewer-b]\n    tag: contract-task-contract-v1.1.0")
        self.assertFails(r"frozen tag 'contract-task-contract-v1\.1\.0' does not exist as an annotated git tag")

    def test_invalid_contract_status(self) -> None:
        self.pending_review()
        self.edit(self.STATE, "    status: in_review\n", "    status: wibble@9.9.9\n")
        self.assertFails(r"invalid status 'wibble@9\.9\.9'")

    def test_event_protocol_entry_cannot_be_removed(self) -> None:
        # Regression for B-17: deleting the entry must not lift the deferral.
        self.edit(self.STATE, "  - id: event-protocol\n    path: null\n    version: null\n    status: not_drafted\n    not_before_phase: P2\n", "")
        self.assertFails(r"contract event-protocol: must be registered \(deferred to P2")

    def test_event_protocol_deferral_cannot_be_dropped(self) -> None:
        self.edit(self.STATE, "    status: not_drafted\n    not_before_phase: P2", "    status: draft")
        self.assertFails(r"contract event-protocol: not_before_phase must be P2")

    def approve_p1_contract(self, verdicts: bool = True) -> None:
        def apply(d: dict[str, Any]) -> None:
            c = next(c for c in d["contracts"] if c["id"] == "phase1-foundation")
            c.update(status="approved", reviewed_by=["reviewer-a", "reviewer-b"])
        self.update_state(apply)
        if verdicts:
            rec = self.path("docs/reviews/phase-1-contract-review.md")
            rec.write_text(rec.read_text().split("<!-- final-verdicts -->")[0] + "<!-- final-verdicts -->\n"
                           "- **Reviewer A final outcome:** APPROVE\n- **Reviewer B final outcome:** APPROVE\n")

    def set_pending(self, *entries: dict[str, Any]) -> None:
        self.update_state(lambda d: d.__setitem__("pending_tags", list(entries)))

    def test_pending_contract_tag_requires_approval(self) -> None:
        # Review P1A-05: no tag for a contract that is not approved by both reviewers.
        self.set_pending({"tag": "contract-phase1-foundation-v1.0.0", "commit": "self", "message": "m"})
        self.assertFails(r"contract phase1-foundation v1\.0\.0 is not approved")

    def test_pending_contract_tag_requires_verdicts(self) -> None:
        self.approve_p1_contract(verdicts=False)
        self.set_pending({"tag": "contract-phase1-foundation-v1.0.0", "commit": "self", "message": "m"})
        self.assertFails(r"pending_tags\[0\] contract-phase1-foundation-v1\.0\.0: no recorded final verdict")

    def test_pending_contract_tag_version_must_match(self) -> None:
        self.approve_p1_contract()
        self.set_pending({"tag": "contract-phase1-foundation-v2.0.0", "commit": "self", "message": "m"})
        self.assertFails(r"contract phase1-foundation v2\.0\.0 is not approved")

    def test_pending_tag_shape_and_phase_rules(self) -> None:
        self.set_pending({"tag": "refs/heads/main", "commit": "self", "message": "m"},
                         {"tag": "contract-nope-v1.0.0", "commit": "HEAD", "message": ""},
                         {"tag": "phase-P1-v1.0.0", "commit": "self", "message": "m"})
        self.assertFails(r"pending_tags\[0\]: invalid tag name 'refs/heads/main'",
                         r"pending_tags\[1\] contract-nope-v1\.0\.0: commit must be a 40-hex sha or 'self'",
                         r"pending_tags\[1\] contract-nope-v1\.0\.0: message must be non-empty",
                         r"unknown contract 'nope'",
                         r"pending_tags\[2\] phase-P1-v1\.0\.0: phase P1 is not in gate_review/closed")

    def test_existing_tag_entry_is_an_audit_record(self) -> None:
        # Review P1B-10: once created, a kept entry must not fail CI when the
        # contract later changes (e.g. back to in_review for a v2 draft).
        self.set_pending({"tag": "contract-phase1-foundation-v1.0.0", "commit": "self", "message": "m"})
        self.commit("entry")
        self.git("tag", "-a", "contract-phase1-foundation-v1.0.0", "-m", "m")
        res = self.run_checker()
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_pending_contract_tag_for_approved_contract_passes(self) -> None:
        # Control: the rule is satisfiable once both verdicts are recorded.
        self.approve_p1_contract()
        self.set_pending({"tag": "contract-phase1-foundation-v1.0.0", "commit": "self", "message": "m"})
        res = self.run_checker()
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_overlapping_claims(self) -> None:
        self.set_claims([{"task": "AO-P1-001", "owner": "impl-1", "paths": ["backend/"]},
                         {"task": "AO-P1-002", "owner": "impl-2", "paths": ["backend/src/ingest"]}])
        self.assertFails(r"claims: 'backend/src/ingest' \(AO-P1-002\) overlaps 'backend' \(AO-P1-001\)")

    def test_claim_overlap_is_case_insensitive(self) -> None:
        self.set_claims([{"task": "AO-P1-001", "owner": "impl-1", "paths": ["Core/ingest/"]},
                         {"task": "AO-P1-002", "owner": "impl-2", "paths": ["./core/ingest"]}])
        self.assertFails(r"'\./core/ingest' \(AO-P1-002\) overlaps 'core/ingest' \(AO-P1-001\)")

    def test_claim_glob_dotslash_duplicate_and_phase(self) -> None:
        # Regression for B-18 / N-05.
        self.set_phase("P1", status="not_started")
        self.set_claims([{"task": "AO-P1-001", "owner": "impl-1", "paths": ["backend/**"]},
                         {"task": "AO-P1-002", "owner": "impl-2", "paths": ["frontend"]},
                         {"task": "AO-P1-003", "owner": "impl-3", "paths": ["./frontend/app/"]},
                         {"task": "AO-P1-003", "owner": "impl-4", "paths": ["docs/x"]},
                         {"task": "AO-P1-004", "owner": "impl-5", "paths": ["../outside"]}])
        self.assertFails(
            r"'backend/\*\*' uses glob characters",
            r"'./frontend/app/' \(AO-P1-003\) overlaps 'frontend' \(AO-P1-002\)",
            r"task AO-P1-003 claimed more than once",
            r"claim AO-P1-001: phase P1 is not in_progress",
            r"'../outside' must be a relative path inside the repository",
        )


class TestAdrs(CheckerCase):
    def test_unindexed_adr(self) -> None:
        self.path("docs/adr/0005-sneaky.md").write_text("# ADR-0005\n\n- Status: accepted\n")
        self.assertFails(r"docs/adr/0005-sneaky\.md: not listed")

    def test_adr_related_unknown_ids(self) -> None:
        self.edit("docs/adr/0002-phase-1-technology-stack.md", "- Related: A-004", "- Related: A-999, TD-404, A-004")
        self.assertFails(r"unknown id A-999", r"unknown id TD-404")

    def test_adr_invalid_status(self) -> None:
        self.edit("docs/adr/0003-phase-order-and-event-protocol-deferral.md", "- Status: accepted", "- Status: maybe")
        self.assertFails(r"0003-.*: missing or invalid Status line")


class TestLinks(CheckerCase):
    def test_broken_inline_link(self) -> None:
        self.edit("docs/agent-efficiency.md", "## Principles", "## Principles\n\nSee [x](missing.md).")
        self.assertFails(r"agent-efficiency\.md: broken link -> missing\.md")

    def test_broken_reference_link(self) -> None:
        self.edit("docs/agent-efficiency.md", "## Principles", "## Principles\n\nSee [y][ref].\n\n[ref]: nowhere.md")
        self.assertFails(r"broken link -> nowhere\.md")

    def test_broken_autolink(self) -> None:
        self.edit("docs/agent-efficiency.md", "## Principles", "## Principles\n\nSee <gone.md>.")
        self.assertFails(r"broken link -> gone\.md")

    def test_link_escaping_repository(self) -> None:
        self.edit("docs/agent-efficiency.md", "## Principles", "## Principles\n\nSee [p](../../../../../../etc/passwd).")
        self.assertFails(r"link escapes repository")

    def test_required_doc_not_linked_from_index(self) -> None:
        self.edit("docs/README.md", "| [rollback-policy.md](rollback-policy.md) | Checkpoints, tags, reverting, secret incidents |\n", "")
        self.assertFails(r"required document not linked from index: rollback-policy\.md")


class TestSecretPatterns(CheckerCase):
    def assertSecretFlagged(self, where: str, kind: str, value: str) -> None:
        out = self.assertFails(rf"possible secret \({kind}\) in .*\({where}\)")
        self.assertNotIn(value, out, "checker must never print the secret value")

    def test_working_tree_secret(self) -> None:
        self.path("config.txt").write_text(f"key={FAKE['aws']}\n")
        self.assertSecretFlagged("working tree", "aws-access-key-id", FAKE["aws"])

    def test_staged_only_secret(self) -> None:
        self.path("staged.txt").write_text(f"key={FAKE['aws']}\n")
        self.git("add", "staged.txt")
        self.path("staged.txt").write_text("clean\n")
        self.assertSecretFlagged("index", "aws-access-key-id", FAKE["aws"])

    def test_history_only_secret(self) -> None:
        self.path("leak.txt").write_text(f"key={FAKE['aws']}\n")
        self.commit("leak")
        self.git("rm", "-q", "leak.txt")
        self.commit("remove leak")
        self.assertSecretFlagged("history", "aws-access-key-id", FAKE["aws"])

    def test_non_utf8_file(self) -> None:
        self.path("blob.bin").write_bytes(b"\xff\xfe\x00" + FAKE["aws"].encode() + b"\x80\x81")
        self.assertSecretFlagged("working tree", "aws-access-key-id", FAKE["aws"])

    def test_common_formats(self) -> None:
        kinds = {
            "github_pat": "github-fine-grained-pat",
            "cred_url": "credentialed-url",
            "jwt": "jwt",
            "slack_webhook": "slack-webhook",
            "google": "google-api-key",
            "generic": "generic-secret-assignment",
        }
        for key, kind in kinds.items():
            with self.subTest(kind=kind):
                f = self.path(f"cfg-{key}.yaml")
                f.write_text(f"value: {FAKE[key]}\n" if key != "generic" else FAKE[key] + "\n")
                self.assertSecretFlagged("working tree", kind, FAKE[key])
                f.unlink()

    def test_commit_message_secret(self) -> None:
        self.git("commit", "-q", "--allow-empty", "-m", f"oops {FAKE['aws']}")
        self.assertSecretFlagged("commit message", "aws-access-key-id", FAKE["aws"])

    def test_tag_message_secret(self) -> None:
        self.git("tag", "-a", "v0", "-m", f"oops {FAKE['aws']}")
        self.assertSecretFlagged("tag message", "aws-access-key-id", FAKE["aws"])

    def test_large_file_is_not_silently_skipped(self) -> None:
        self.path("big.txt").write_bytes(b"x" * (6 * 1024 * 1024))
        self.assertFails(r"big\.txt \(working tree\) exceeds \d+ bytes; not scanned")

    def test_literal_still_flagged_next_to_code(self) -> None:
        value = "Zx9" * 6
        self.path("settings_code.py").write_text('token = os.environ.get("X")\nfallback_token = "' + value + '"\n')
        self.assertSecretFlagged("working tree", "generic-secret-assignment", value)

    def test_prefixed_password_and_userless_url(self) -> None:
        cases = {
            "generic-secret-assignment": "DB_" + "PASSWORD=" + "s3cr3tVal!",
            "credentialed-url": "redis://:" + "pw" + "@cache.internal:6379/0",
        }
        for kind, value in cases.items():
            with self.subTest(kind=kind):
                f = self.path("settings.env.txt")
                f.write_text(value + "\n")
                self.assertSecretFlagged("working tree", kind, value)
                f.unlink()

    def test_placeholders_not_flagged(self) -> None:
        self.path(".env.example").write_text("API_KEY=<your-key-here>\npassword: changeme-placeholder\n")
        self.path("settings_code.py").write_text('token = os.environ.get("GITHUB_TOKEN")\napi_key = load_secret("x")\n')
        res = self.run_checker()
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_not_a_git_repository_is_clean_failure(self) -> None:
        shutil.rmtree(self.path(".git"))
        self.assertFails(r"not a git repository")


if __name__ == "__main__":
    unittest.main()
