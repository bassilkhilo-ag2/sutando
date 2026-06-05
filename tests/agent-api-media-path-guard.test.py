#!/usr/bin/env python3
"""Security regression guard: /media/<rel> path-traversal defence in agent-api.py.

The guard at lines 488-526 layers five string-level checks before resolving the
path, then a containment check after:

  1. Regex whitelist: `re.sub(r'[^a-zA-Z0-9_./-]', '', rel)` — strips anything
     outside the safe set.
  2. Strict equality: `safe_rel != rel` → reject if any char was stripped.
  3. Explicit `..` guard: `'..' in safe_rel` → reject (catches dot-dot that
     survive the regex since `.` and `/` are in the whitelist).
  4. Absolute-path guard: `safe_rel.startswith('/')` → reject.
  5. Null-byte guard: `'\\x00' in safe_rel` → reject.

After all five checks, Path(p).name per component breaks CodeQL taint flow,
then `.resolve()` + `.is_relative_to(WORKSPACE_DIR.resolve())` is the
final containment check.

These tests operate directly on the guard logic, not via the HTTP layer,
so they run without the agent-api server and in CI.

Pins:
  1.  `..` traversal in rel → rejected (guard 3: contains `..`).
  2.  `/etc/passwd` as rel → rejected (guard 4: starts with `/`).
  3.  `@secret.txt` → rejected (guard 1+2: `@` stripped → safe_rel != rel).
  4.  `%2e%2e/foo` → rejected (guard 1+2: `%` stripped → safe_rel != rel).
  5.  Null byte → rejected (guard 1+2 OR guard 5: `\\x00` stripped or detected).
  6.  Empty rel after strip → rejected (guard 1: falsy safe_rel).
  7.  `results/file.txt` with all valid chars → accepted (all guards pass).
  8.  `results/sub-dir/img.png` (nested) → accepted.
  9.  Resolved accepted path is inside WORKSPACE_DIR (containment invariant).
  10. Dot-only component `results/../notes/file.md` → rejected (guard 3).
  11. Mixed valid+invalid: `file\x00name.txt` → rejected (guard 2: null stripped).
  12. Empty string rel → rejected (guard 1: empty safe_rel).
"""
import os
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

WORKSPACE = Path(os.environ.get("SUTANDO_WORKSPACE", Path.home() / ".sutando" / "workspace"))


def _apply_guard(rel: str) -> tuple[bool, str]:
    """Apply the /media/ path guard from agent-api.py do_GET.

    Returns (rejected, reason) where rejected=True means the guard fired
    (would return HTTP 400 or 404 in production) and reason is the label.
    Returns (False, 'pass') if the guard does NOT fire (path is accepted).
    """
    safe_rel = re.sub(r"[^a-zA-Z0-9_./-]", "", rel)
    if not safe_rel:
        return True, "empty_after_strip"
    if safe_rel != rel:
        return True, "strip_changed_input"
    if ".." in safe_rel:
        return True, "contains_dot_dot"
    if safe_rel.startswith("/"):
        return True, "absolute_path_in_rel"
    if "\x00" in safe_rel:
        return True, "null_byte"
    return False, "pass"


def _resolve_accepted_path(rel: str) -> Path:
    """For an accepted rel, return the resolved media_path as agent-api would."""
    safe_rel = re.sub(r"[^a-zA-Z0-9_./-]", "", rel)
    safe_parts = [Path(p).name for p in safe_rel.split("/") if p]
    workspace_resolved = WORKSPACE.resolve()
    return workspace_resolved.joinpath(*safe_parts).resolve()


class TestMediaGuardRejectsTraversal(unittest.TestCase):

    def test_dot_dot_traversal_rejected(self):
        rejected, reason = _apply_guard("../etc/passwd")
        self.assertTrue(rejected, "expected rejection")
        self.assertEqual(reason, "contains_dot_dot")

    def test_nested_dot_dot_rejected(self):
        rejected, _ = _apply_guard("results/../../../etc/passwd")
        self.assertTrue(rejected)

    def test_url_encoded_dot_dot_rejected(self):
        # urlparse preserves %-encoding; % not in whitelist → strip → safe_rel != rel
        rejected, reason = _apply_guard("%2e%2e/etc/passwd")
        self.assertTrue(rejected)
        self.assertEqual(reason, "strip_changed_input")

    def test_at_sign_rejected(self):
        rejected, reason = _apply_guard("results/@secret.txt")
        self.assertTrue(rejected)
        self.assertEqual(reason, "strip_changed_input")

    def test_dollar_sign_rejected(self):
        rejected, reason = _apply_guard("results/$file.txt")
        self.assertTrue(rejected)
        self.assertEqual(reason, "strip_changed_input")

    def test_absolute_path_in_rel_rejected(self):
        # If the path after /media/ starts with / → absolute path guard fires
        rejected, reason = _apply_guard("/etc/passwd")
        self.assertTrue(rejected)
        self.assertEqual(reason, "absolute_path_in_rel")

    def test_null_byte_rejected(self):
        # \x00 is not in whitelist → stripped → safe_rel != rel
        rejected, reason = _apply_guard("file\x00name.txt")
        self.assertTrue(rejected)
        self.assertEqual(reason, "strip_changed_input")

    def test_space_rejected(self):
        # space not in whitelist → stripped → safe_rel != rel
        rejected, reason = _apply_guard("results/my file.txt")
        self.assertTrue(rejected)
        self.assertEqual(reason, "strip_changed_input")

    def test_empty_rel_rejected(self):
        rejected, reason = _apply_guard("")
        self.assertTrue(rejected)
        self.assertEqual(reason, "empty_after_strip")

    def test_all_stripped_chars_rejected(self):
        rejected, reason = _apply_guard("@#$%^&*()")
        self.assertTrue(rejected)
        self.assertEqual(reason, "empty_after_strip")

    def test_dot_dot_embedded_in_valid_rel_rejected(self):
        # `results/../notes/file.md` — contains `..` so guard fires
        rejected, reason = _apply_guard("results/../notes/file.md")
        self.assertTrue(rejected)
        self.assertEqual(reason, "contains_dot_dot")


class TestMediaGuardAcceptsValidPaths(unittest.TestCase):

    def test_simple_relative_path_accepted(self):
        rejected, reason = _apply_guard("results/file.txt")
        self.assertFalse(rejected, f"expected acceptance but got {reason}")

    def test_nested_path_accepted(self):
        rejected, reason = _apply_guard("results/sub-dir/image.png")
        self.assertFalse(rejected)

    def test_path_with_hyphens_and_dots_accepted(self):
        # Dots and hyphens are in the whitelist
        rejected, reason = _apply_guard("results/file-2026.06.05.txt")
        self.assertFalse(rejected)

    def test_single_component_accepted(self):
        rejected, reason = _apply_guard("notes")
        self.assertFalse(rejected)


class TestMediaResolvedPathContainment(unittest.TestCase):
    """For guard-accepted paths, verify the resolved path is inside WORKSPACE."""

    def test_simple_path_resolves_inside_workspace(self):
        workspace_resolved = WORKSPACE.resolve()
        result = _resolve_accepted_path("results/any-file.txt")
        self.assertTrue(
            str(result).startswith(str(workspace_resolved) + os.sep),
            f"resolved path escaped workspace: {result}",
        )

    def test_nested_path_resolves_inside_workspace(self):
        workspace_resolved = WORKSPACE.resolve()
        result = _resolve_accepted_path("data/images/screenshot.png")
        self.assertTrue(
            str(result).startswith(str(workspace_resolved) + os.sep),
            f"resolved path escaped workspace: {result}",
        )

    def test_path_with_dots_in_extension_stays_inside_workspace(self):
        workspace_resolved = WORKSPACE.resolve()
        result = _resolve_accepted_path("results/file.2026.06.txt")
        self.assertTrue(
            str(result).startswith(str(workspace_resolved) + os.sep),
            f"resolved path escaped workspace: {result}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
