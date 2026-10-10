"""Tests for scripts/release-tags.py input validation (ADR-0005 §7).

The git side effects run only in the release-tags workflow; `validate` is
pure and decides what that workflow is allowed to attempt.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "release_tags", Path(__file__).resolve().parents[2] / "scripts" / "release-tags.py"
)
rt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rt)  # type: ignore[union-attr]

SHA = "8ce0ed38198fc02fbcf14cb7a370844470567a6e"


def entry(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {"tag": "contract-phase1-foundation-v1.0.0", "commit": SHA, "message": "m"}
    base.update(kw)
    return base


class TestValidate(unittest.TestCase):
    def test_empty_and_valid(self) -> None:
        self.assertEqual(rt.validate(None), [])
        self.assertEqual(rt.validate([]), [])
        self.assertEqual(rt.validate([entry(), entry(tag="phase-P1-v1.0.0", commit="self")]), [])

    def test_rejects_arbitrary_ref_names(self) -> None:
        for bad in ("main", "refs/heads/main", "v1.0.0", "phase-P1-v1", "contract-X-v1.0.0",
                    "phase-P1-v1.0.0;rm", "../phase-P1-v1.0.0", "phase-P1-v1.0.0 "):
            with self.subTest(tag=bad):
                self.assertTrue(any("invalid tag name" in p for p in rt.validate([entry(tag=bad)])))

    def test_rejects_short_or_symbolic_commits(self) -> None:
        for bad in ("8ce0ed3", "HEAD", "main", SHA.upper(), SHA + "0", "Self", "self~1"):
            with self.subTest(commit=bad):
                self.assertTrue(any("40-hex" in p for p in rt.validate([entry(commit=bad)])))

    def test_rejects_duplicates_missing_message_and_bad_shapes(self) -> None:
        self.assertTrue(any("duplicate" in p for p in rt.validate([entry(), entry()])))
        self.assertTrue(any("message" in p for p in rt.validate([entry(message="  ")])))
        self.assertEqual(rt.validate("x"), ["pending_tags must be a list"])
        self.assertTrue(any("mapping" in p for p in rt.validate(["x"])))


def state(pending: list[str], status: str = "approved", comment: str = "") -> str:
    lines = [f"# {comment}" if comment else "", "contracts:",
             "  - {id: phase1-foundation, version: 1.0.0, status: " + status + "}", "pending_tags:"]
    lines += [f"  - {{tag: {t}, commit: self, message: m}}" for t in pending] or ["  []"]
    return "\n".join(lines) + "\n"


TAG = "contract-phase1-foundation-v1.0.0"


class TestResolveSelf(unittest.TestCase):
    """Reviews P1A-09 / P1B-09: `self` is the commit that added the parsed entry."""

    def test_mention_in_comment_is_ignored(self) -> None:
        hist = [("c1", state([], comment=TAG)), ("c2", state([TAG])), ("c3", state([TAG]))]
        self.assertEqual(rt.resolve_self_from(hist, TAG), "c2")

    def test_contract_tag_field_mention_is_ignored(self) -> None:
        early = "contracts:\n  - {id: phase1-foundation, version: 1.0.0, status: draft, tag: " + TAG + "}\n"
        hist = [("c1", early), ("c2", state([TAG]))]
        self.assertEqual(rt.resolve_self_from(hist, TAG), "c2")

    def test_stable_across_later_unrelated_commits(self) -> None:
        hist = [("c1", state([])), ("c2", state([TAG])), ("c3", state([TAG, "phase-P1-v1.0.0"])), ("c4", state([TAG]))]
        self.assertEqual(rt.resolve_self_from(hist, TAG), "c2")

    def test_removed_and_readded_uses_latest_addition(self) -> None:
        hist = [("c1", state([TAG])), ("c2", state([])), ("c3", state([TAG]))]
        self.assertEqual(rt.resolve_self_from(hist, TAG), "c3")

    def test_removed_entry_does_not_resolve(self) -> None:
        self.assertIsNone(rt.resolve_self_from([("c1", state([TAG])), ("c2", state([]))], TAG))

    def test_contract_not_approved_at_introduction_does_not_resolve(self) -> None:
        hist = [("c1", state([TAG], status="in_review")), ("c2", state([TAG], status="approved"))]
        self.assertIsNone(rt.resolve_self_from(hist, TAG))

    def test_unparseable_or_missing_versions_are_safe(self) -> None:
        hist = [("c1", None), ("c2", "{{not yaml"), ("c3", state([TAG]))]
        self.assertEqual(rt.resolve_self_from(hist, TAG), "c3")


if __name__ == "__main__":
    unittest.main()
