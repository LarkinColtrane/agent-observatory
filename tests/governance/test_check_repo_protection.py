"""Tests for scripts/check-repo-protection.py decision logic (review B-25).

The network call is not exercised here; `evaluate` is pure.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_repo_protection", Path(__file__).resolve().parents[2] / "scripts" / "check-repo-protection.py"
)
crp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(crp)  # type: ignore[union-attr]

UNPROTECTED = {"protected": False, "protection": {"enabled": False, "required_status_checks": {"contexts": [], "checks": []}}}
PROTECTED_NO_CHECK = {"protected": True, "protection": {"enabled": True, "required_status_checks": {"contexts": [], "checks": []}}}
PROTECTED_OK = {"protected": True, "protection": {"enabled": True, "required_status_checks": {"contexts": ["governance"], "checks": [{"context": "governance"}]}}}


class TestEvaluate(unittest.TestCase):
    def test_open_debt_never_fails(self) -> None:
        for status in ("open", "scheduled", None):
            self.assertEqual(crp.evaluate(status, UNPROTECTED), [])

    def test_repaid_but_unprotected_fails(self) -> None:
        problems = crp.evaluate("repaid", UNPROTECTED)
        self.assertTrue(any("not protected" in p for p in problems))
        self.assertTrue(any("'governance' is not a required check" in p for p in problems))

    def test_repaid_but_check_not_required_fails(self) -> None:
        self.assertEqual(len(crp.evaluate("repaid", PROTECTED_NO_CHECK)), 1)

    def test_repaid_and_protected_passes(self) -> None:
        self.assertEqual(crp.evaluate("repaid", PROTECTED_OK), [])

    def test_checks_field_alone_is_recognised(self) -> None:
        branch = {"protected": True, "protection": {"required_status_checks": {"checks": [{"context": "governance"}]}}}
        self.assertEqual(crp.evaluate("repaid", branch), [])

    def test_ruleset_only_protection_passes(self) -> None:
        # Review N-B: a ruleset may protect main without classic protection fields.
        rules = [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "pull_request", "parameters": {"required_approving_review_count": 0}},
            {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "governance"}]}},
        ]
        self.assertEqual(crp.evaluate("repaid", UNPROTECTED, rules), [])

    def test_ruleset_without_governance_check_fails(self) -> None:
        rules = [{"type": "pull_request"}, {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "other"}]}}]
        problems = crp.evaluate("repaid", UNPROTECTED, rules)
        self.assertEqual(problems, ["TD-004 is recorded as repaid but 'governance' is not a required check on main"])

    def test_unrelated_rules_do_not_count_as_protection(self) -> None:
        self.assertEqual(len(crp.evaluate("repaid", PROTECTED_NO_CHECK | {"protected": False}, [{"type": "creation"}])), 2)

    def test_missing_protection_block_is_handled(self) -> None:
        self.assertEqual(len(crp.evaluate("repaid", {"protected": True})), 1)


class TestFetchBranch(unittest.TestCase):
    def test_non_https_api_url_rejected(self) -> None:
        import os
        from unittest import mock

        for url in ("file:///etc/passwd", "http://api.github.com", "ftp://x"):
            with self.subTest(url=url), mock.patch.dict(os.environ, {"GITHUB_API_URL": url}):
                with self.assertRaises(ValueError):
                    crp.fetch_branch("o/r")


if __name__ == "__main__":
    unittest.main()
