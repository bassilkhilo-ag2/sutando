#!/usr/bin/env python3
"""Security regression guard: `_resolve_note_path` in dashboard.py.

`_resolve_note_path(raw_slug)` is the CodeQL-recognised path-injection guard
for the `/note/<slug>` endpoint — it resolves `notes/{slug}.md` and rejects
any slug that requires sanitization (stricter than `_safe_path`: if ANY char
is stripped, the whole slug is rejected rather than silently sanitised).

Invariants pinned here:
  1. A valid slug (only `[\\w-]` chars) returns a Path inside the notes dir.
  2. A slug containing `.` (not in the whitelist) is rejected because
     strip ≠ raw — so `..` and filenames like `foo.bar` are always None.
  3. A slug containing `/` is rejected.
  4. A slug containing `\\` is rejected.
  5. A slug containing `@` or other specials is rejected.
  6. An empty string returns None.
  7. A slug that is all numeric is accepted (`\\w` includes digits).
  8. A slug with hyphens is accepted (`-` is in `[\\w-]`).
  9. The returned path ends with `.md`.
  10. The returned path is absolute (realpath-normalised).
  11. The path is under the notes directory (not escaped via traversal).

The key security property: because `slug != raw_slug` triggers an immediate
return of None, there is no silent sanitisation that could allow a forged slug
to resolve to an unintended location.
"""
import importlib.util
import os
import sys
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


db = _load("dashboard", REPO / "src" / "dashboard.py")


class TestValidSlugs(unittest.TestCase):

    def test_simple_alphanumeric_slug_returns_path(self):
        result = db._resolve_note_path("my-note-2026")
        self.assertIsNotNone(result, "valid slug should return a Path")

    def test_slug_with_hyphens_accepted(self):
        result = db._resolve_note_path("linkedin-wwdc-2026-draft-a-fire-ready")
        self.assertIsNotNone(result)

    def test_all_digit_slug_accepted(self):
        # \\w includes digits
        result = db._resolve_note_path("20260605")
        self.assertIsNotNone(result)

    def test_result_ends_with_md(self):
        result = db._resolve_note_path("some-note")
        self.assertIsNotNone(result)
        self.assertTrue(str(result).endswith(".md"), f"expected .md, got {result}")

    def test_result_is_absolute(self):
        result = db._resolve_note_path("some-note")
        self.assertIsNotNone(result)
        self.assertTrue(result.is_absolute(), f"expected absolute path, got {result}")

    def test_result_is_inside_notes_dir(self):
        # The returned path must be under the workspace notes/ directory.
        result = db._resolve_note_path("any-slug-here")
        self.assertIsNotNone(result)
        notes_real = os.path.realpath(db.shared_personal_path("notes"))
        self.assertTrue(
            str(result).startswith(notes_real + os.sep),
            f"path escaped notes dir: {result}",
        )


class TestInvalidSlugs(unittest.TestCase):

    def test_dot_in_slug_rejected(self):
        # `.` is not in `[\\w-]`; strip would change it, so raw != sanitised → None
        self.assertIsNone(db._resolve_note_path("foo.bar"))

    def test_double_dot_rejected(self):
        # Classic traversal attempt — dots not in whitelist → immediate None
        self.assertIsNone(db._resolve_note_path(".."))

    def test_slash_in_slug_rejected(self):
        self.assertIsNone(db._resolve_note_path("../etc/passwd"))

    def test_backslash_rejected(self):
        self.assertIsNone(db._resolve_note_path("..\\..\\etc\\passwd"))

    def test_at_sign_rejected(self):
        self.assertIsNone(db._resolve_note_path("user@host"))

    def test_null_byte_rejected(self):
        self.assertIsNone(db._resolve_note_path("note\x00name"))

    def test_space_rejected(self):
        self.assertIsNone(db._resolve_note_path("note name"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(db._resolve_note_path(""))

    def test_path_separator_in_slug_rejected(self):
        # Even a single forward slash makes strip ≠ raw → None
        self.assertIsNone(db._resolve_note_path("valid/path"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
