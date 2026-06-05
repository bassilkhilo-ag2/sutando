#!/usr/bin/env python3
"""Security regression guard: answer-question task file path guard in agent-api.py.

At lines 748-758, the POST /answer handler sanitizes `qid` before writing an
`answer-{safe_qid}-{ts}.txt` file to the tasks/ directory:

    safe_qid = re.sub(r'[^a-zA-Z0-9_\\-.]', '', qid)
    if safe_qid:
        task_dir_real = os.path.realpath(WORKSPACE_DIR / "tasks")
        task_file_str = os.path.realpath(
            os.path.join(task_dir_real, f"answer-{safe_qid}-{ts}.txt")
        )
        if task_file_str.startswith(task_dir_real + os.sep):
            Path(task_file_str).write_text(...)

Unlike `_resolve_note_path` (strict equality), this guard silently strips chars
and continues — same posture as `_safe_path`. The `answer-` prefix and `-{ts}.txt`
suffix make the resulting path component a filename, never a relative traversal.

Invariants pinned here:
  1.  A valid qid survives stripping unchanged.
  2.  Characters outside `[a-zA-Z0-9_\\-.]` are stripped, not rejected.
  3.  A qid composed entirely of stripped chars produces empty safe_qid → the
      guard short-circuits (no file is written).
  4.  Slash traversal is stripped → `../` chars removed → safe_qid has no `/`.
  5.  Null byte is stripped → safe part continues.
  6.  The resolved answer path is inside WORKSPACE tasks/ dir (containment).
  7.  `..` in qid (dots are in the whitelist) becomes part of the safe name but
      cannot escape because: (a) `/` is stripped so there's no path separator,
      and (b) `answer-` prefix + `-{ts}.txt` suffix make the name a flat file.
  8.  An at-sign is stripped; rest of qid survives.
"""
import os
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

WORKSPACE = Path(os.environ.get("SUTANDO_WORKSPACE", Path.home() / ".sutando" / "workspace"))
FAKE_TS = 9999999999999


def _apply_qid_guard(qid: str) -> tuple[str, bool]:
    """Mirror the answer-qid guard from agent-api.py do_POST.

    Returns (safe_qid, would_write) — safe_qid is the sanitized value,
    would_write is True if the guard would allow a file write.
    """
    safe_qid = re.sub(r"[^a-zA-Z0-9_\-.]", "", qid)
    would_write = bool(safe_qid)
    return safe_qid, would_write


def _resolved_answer_path(safe_qid: str) -> str:
    """Return the realpath of the answer file for the given safe_qid."""
    task_dir_real = os.path.realpath(WORKSPACE / "tasks")
    return os.path.realpath(
        os.path.join(task_dir_real, f"answer-{safe_qid}-{FAKE_TS}.txt")
    )


def _is_inside_tasks(resolved_path: str) -> bool:
    task_dir_real = os.path.realpath(WORKSPACE / "tasks")
    return resolved_path.startswith(task_dir_real + os.sep)


class TestQidSanitization(unittest.TestCase):

    def test_valid_qid_survives_unchanged(self):
        safe, would_write = _apply_qid_guard("q-12345abcDEF_test.1")
        self.assertEqual(safe, "q-12345abcDEF_test.1")
        self.assertTrue(would_write)

    def test_slash_stripped(self):
        safe, would_write = _apply_qid_guard("../../etc/passwd")
        # Slashes and dots — slashes are stripped, dots stay
        self.assertNotIn("/", safe)
        self.assertNotIn("\\", safe)
        # The surviving chars are still written (dots survived)
        self.assertTrue(would_write)

    def test_at_sign_stripped(self):
        safe, _ = _apply_qid_guard("q@host.txt")
        self.assertNotIn("@", safe)
        self.assertEqual(safe, "qhost.txt")

    def test_null_byte_stripped(self):
        safe, _ = _apply_qid_guard("q\x00id")
        self.assertNotIn("\x00", safe)
        self.assertEqual(safe, "qid")

    def test_all_stripped_chars_yields_no_write(self):
        safe, would_write = _apply_qid_guard("@#$%^&*()")
        self.assertEqual(safe, "")
        self.assertFalse(would_write)

    def test_empty_qid_yields_no_write(self):
        safe, would_write = _apply_qid_guard("")
        self.assertEqual(safe, "")
        self.assertFalse(would_write)

    def test_dot_dot_survives_as_safe_name(self):
        # Dots are whitelisted — `..` is NOT stripped.
        # The resulting filename `answer-..-{ts}.txt` is a flat file name, not a traversal.
        safe, would_write = _apply_qid_guard("..")
        self.assertEqual(safe, "..")
        self.assertTrue(would_write)

    def test_space_stripped(self):
        safe, _ = _apply_qid_guard("q id")
        self.assertEqual(safe, "qid")


class TestQidContainment(unittest.TestCase):
    """After sanitization, the resolved path must stay inside tasks/."""

    def test_valid_qid_resolves_inside_tasks(self):
        safe, would_write = _apply_qid_guard("q-abc123")
        self.assertTrue(would_write)
        resolved = _resolved_answer_path(safe)
        self.assertTrue(
            _is_inside_tasks(resolved),
            f"resolved path escaped tasks/: {resolved}",
        )

    def test_dot_dot_qid_resolves_inside_tasks(self):
        # Even though `..` survives stripping, the hardcoded `answer-` prefix
        # and `-{ts}.txt` suffix make the path component a plain filename.
        safe, would_write = _apply_qid_guard("..")
        self.assertTrue(would_write)
        resolved = _resolved_answer_path(safe)
        self.assertTrue(
            _is_inside_tasks(resolved),
            f"dot-dot qid escaped tasks/: {resolved}",
        )

    def test_traversal_attempt_resolves_inside_tasks(self):
        # `../../../etc/passwd` → slashes stripped → `......etcpasswd` → inside tasks/
        qid = "../../../etc/passwd"
        safe, would_write = _apply_qid_guard(qid)
        self.assertTrue(would_write)
        resolved = _resolved_answer_path(safe)
        self.assertTrue(
            _is_inside_tasks(resolved),
            f"traversal-attempt qid escaped tasks/: {resolved}",
        )

    def test_empty_qid_never_resolves(self):
        _, would_write = _apply_qid_guard("@#$")
        self.assertFalse(would_write)  # no path resolution happens


if __name__ == "__main__":
    unittest.main(verbosity=2)
