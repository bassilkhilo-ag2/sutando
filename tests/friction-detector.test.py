#!/usr/bin/env python3
"""
Tests for src/friction-detector.py

Coverage:
  check_pending_questions — no file, empty, "(No pending questions)", single unanswered
                            with/without Asked date (age computed), multiple sections
                            (answered excluded), last section not forgotten (flush)
  check_stale_tasks       — no dir, empty dir, fresh task (<1h), old task (>1h stale)
  check_github_issues     — gh not found, timeout, empty list, recent issue (excluded),
                            stale issue >7d (included), bad JSON handled
  check_overdue_reminders — script absent, overdue line detected, non-overdue silent,
                            subprocess timeout handled
  check_stale_results     — always returns []
  check_notes_without_follow_up — no dir, checkbox marker, todo: marker, follow-up:
                            marker, tags-line todo, action: marker excluded (noisy),
                            note <7d old excluded, fresh note excluded
  main                    — already-done-today skips, no issues → clean message,
                            issues → numbered list written to results/friction-{date}.txt

Run: python3 tests/friction-detector.test.py
Exit code: 0 on pass, 1 on fail.
"""

import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parent.parent
TMPDIR = Path(tempfile.mkdtemp())

_fake_wd = type(sys)("workspace_default")
_fake_wd.resolve_workspace = lambda: TMPDIR
sys.modules["workspace_default"] = _fake_wd

_fake_up = type(sys)("util_paths")
_fake_up.personal_path = lambda name, workspace: str(Path(workspace) / name)
_fake_up.shared_personal_path = lambda name, workspace: str(Path(workspace) / name)
sys.modules["util_paths"] = _fake_up

_spec = importlib.util.spec_from_file_location(
    "friction_detector",
    REPO / "src" / "friction-detector.py",
)
fd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fd)

# Dirs the module writes into.
(TMPDIR / "results").mkdir(parents=True, exist_ok=True)
(TMPDIR / "tasks").mkdir(parents=True, exist_ok=True)
(TMPDIR / "notes").mkdir(parents=True, exist_ok=True)

PQ_FILE = TMPDIR / "pending-questions.md"
TASKS_DIR = TMPDIR / "tasks"
NOTES_DIR = TMPDIR / "notes"
RESULTS_DIR = TMPDIR / "results"


# ── check_pending_questions ───────────────────────────────────────────────────

class TestCheckPendingQuestions(unittest.TestCase):
    def tearDown(self):
        if PQ_FILE.exists():
            PQ_FILE.unlink()

    def test_no_file_returns_empty(self):
        if PQ_FILE.exists():
            PQ_FILE.unlink()
        self.assertEqual(fd.check_pending_questions(), [])

    def test_empty_file_returns_empty(self):
        PQ_FILE.write_text("")
        self.assertEqual(fd.check_pending_questions(), [])

    def test_no_pending_questions_marker_returns_empty(self):
        PQ_FILE.write_text("(No pending questions)")
        self.assertEqual(fd.check_pending_questions(), [])

    def test_unanswered_question_detected(self):
        PQ_FILE.write_text(
            "## Should we deploy?\n"
            "- **Asked:** 2026-01-01\n"
            "- **Status:** unanswered\n"
        )
        issues = fd.check_pending_questions()
        self.assertEqual(len(issues), 1)
        self.assertIn("Should we deploy?", issues[0])

    def test_age_computed_from_asked_date(self):
        past = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        PQ_FILE.write_text(
            f"## Old question\n"
            f"- **Asked:** {past}\n"
            f"- **Status:** unanswered\n"
        )
        issues = fd.check_pending_questions()
        self.assertIn("5d old", issues[0])

    def test_no_asked_date_still_included(self):
        PQ_FILE.write_text(
            "## Undated question\n"
            "- **Status:** unanswered\n"
        )
        issues = fd.check_pending_questions()
        self.assertEqual(len(issues), 1)
        self.assertNotIn("d old", issues[0])

    def test_answered_status_excluded(self):
        PQ_FILE.write_text(
            "## Done\n"
            "- **Asked:** 2026-01-01\n"
            "- **Status:** answered\n"
        )
        self.assertEqual(fd.check_pending_questions(), [])

    def test_multiple_sections_filtered(self):
        PQ_FILE.write_text(
            "## Q1\n- **Status:** unanswered\n\n"
            "## Q2\n- **Status:** answered\n\n"
            "## Q3\n- **Status:** unanswered\n"
        )
        issues = fd.check_pending_questions()
        self.assertEqual(len(issues), 2)

    def test_last_section_flushed(self):
        # Q2 is the last section — flush() after loop must capture it.
        PQ_FILE.write_text(
            "## Q1\n- **Status:** answered\n\n"
            "## Q2\n- **Status:** unanswered\n"
        )
        issues = fd.check_pending_questions()
        self.assertEqual(len(issues), 1)
        self.assertIn("Q2", issues[0])


# ── check_stale_tasks ─────────────────────────────────────────────────────────

class TestCheckStaleTasks(unittest.TestCase):
    def setUp(self):
        for f in TASKS_DIR.glob("task-*.txt"):
            f.unlink()

    def test_no_tasks_dir_returns_empty(self):
        orig = fd.WORKSPACE
        fake_ws = Path(tempfile.mkdtemp())
        fd.WORKSPACE = fake_ws
        try:
            self.assertEqual(fd.check_stale_tasks(), [])
        finally:
            fd.WORKSPACE = orig

    def test_empty_dir_returns_empty(self):
        self.assertEqual(fd.check_stale_tasks(), [])

    def test_fresh_task_not_stale(self):
        f = TASKS_DIR / "task-9999.txt"
        f.write_text("fresh")
        self.assertEqual(fd.check_stale_tasks(), [])
        f.unlink()

    def test_old_task_reported_stale(self):
        f = TASKS_DIR / "task-0001.txt"
        f.write_text("old task")
        old_mtime = time.time() - 7200  # 2 hours ago
        os.utime(f, (old_mtime, old_mtime))
        issues = fd.check_stale_tasks()
        self.assertEqual(len(issues), 1)
        self.assertIn("task-0001.txt", issues[0])
        f.unlink()


# ── check_github_issues ───────────────────────────────────────────────────────

class TestCheckGithubIssues(unittest.TestCase):
    def _run(self, stdout, returncode=0):
        mock = MagicMock()
        mock.returncode = returncode
        mock.stdout = stdout
        with patch("subprocess.run", return_value=mock):
            return fd.check_github_issues()

    def test_gh_not_found_returns_empty(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            self.assertEqual(fd.check_github_issues(), [])

    def test_gh_timeout_returns_empty(self):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 10)):
            self.assertEqual(fd.check_github_issues(), [])

    def test_empty_list_returns_empty(self):
        self.assertEqual(self._run("[]"), [])

    def test_bad_json_returns_empty(self):
        with patch("subprocess.run", MagicMock(return_value=MagicMock(returncode=0, stdout="not json"))):
            self.assertEqual(fd.check_github_issues(), [])

    def test_recent_issue_excluded(self):
        recent = (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        data = json.dumps([{"number": 1, "title": "Recent", "updatedAt": recent}])
        self.assertEqual(self._run(data), [])

    def test_stale_issue_included(self):
        old = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        data = json.dumps([{"number": 42, "title": "Old bug", "updatedAt": old}])
        issues = self._run(data)
        self.assertEqual(len(issues), 1)
        self.assertIn("#42", issues[0])
        self.assertIn("Old bug", issues[0])

    def test_gh_nonzero_exit_returns_empty(self):
        self.assertEqual(self._run("[]", returncode=1), [])


# ── check_overdue_reminders ───────────────────────────────────────────────────

class TestCheckOverdueReminders(unittest.TestCase):
    def test_script_absent_returns_empty(self):
        # WORKSPACE.parent.parent / ".claude" / ... path won't exist in TMPDIR tree
        self.assertEqual(fd.check_overdue_reminders(), [])

    def test_overdue_line_detected(self):
        script_dir = TMPDIR.parent.parent / ".claude" / "skills" / "macos-tools" / "scripts"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / "reminders.py"
        script_path.write_text("# fake")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Buy milk (overdue)\nCall dentist\n"
        try:
            with patch("subprocess.run", return_value=mock_result):
                issues = fd.check_overdue_reminders()
            self.assertEqual(len(issues), 1)
            self.assertIn("overdue", issues[0].lower())
        finally:
            script_path.unlink(missing_ok=True)

    def test_no_overdue_lines_returns_empty(self):
        script_dir = TMPDIR.parent.parent / ".claude" / "skills" / "macos-tools" / "scripts"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / "reminders.py"
        script_path.write_text("# fake")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "All good\nNothing due\n"
        try:
            with patch("subprocess.run", return_value=mock_result):
                issues = fd.check_overdue_reminders()
            self.assertEqual(issues, [])
        finally:
            script_path.unlink(missing_ok=True)

    def test_timeout_returns_empty(self):
        script_dir = TMPDIR.parent.parent / ".claude" / "skills" / "macos-tools" / "scripts"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / "reminders.py"
        script_path.write_text("# fake")
        import subprocess
        try:
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("python3", 10)):
                self.assertEqual(fd.check_overdue_reminders(), [])
        finally:
            script_path.unlink(missing_ok=True)


# ── check_stale_results ───────────────────────────────────────────────────────

class TestCheckStaleResults(unittest.TestCase):
    def test_always_empty(self):
        self.assertEqual(fd.check_stale_results(), [])


# ── check_notes_without_follow_up ────────────────────────────────────────────

class TestCheckNotesWithoutFollowUp(unittest.TestCase):
    def setUp(self):
        for f in NOTES_DIR.glob("*.md"):
            f.unlink()

    def _old_note(self, name: str, content: str) -> Path:
        p = NOTES_DIR / name
        p.write_text(content)
        old_mtime = time.time() - 8 * 86400  # 8 days old
        os.utime(p, (old_mtime, old_mtime))
        return p

    def test_no_notes_dir_returns_empty(self):
        orig = fd.WORKSPACE
        fake_ws = Path(tempfile.mkdtemp())
        fd.WORKSPACE = fake_ws
        try:
            self.assertEqual(fd.check_notes_without_follow_up(), [])
        finally:
            fd.WORKSPACE = orig

    def test_checkbox_marker_detected(self):
        self._old_note("check.md", "# Title\n\n- [ ] Buy coffee\n")
        issues = fd.check_notes_without_follow_up()
        self.assertEqual(len(issues), 1)

    def test_todo_marker_detected(self):
        self._old_note("todo.md", "# Title\n\ntodo: write tests\n")
        issues = fd.check_notes_without_follow_up()
        self.assertEqual(len(issues), 1)

    def test_follow_up_marker_detected(self):
        self._old_note("follow.md", "# Title\n\nfollow-up: send email\n")
        issues = fd.check_notes_without_follow_up()
        self.assertEqual(len(issues), 1)

    def test_todo_in_tags_line_detected(self):
        self._old_note("tagged.md", "---\ntags: [todo, meeting]\n---\n# Title\n")
        issues = fd.check_notes_without_follow_up()
        self.assertEqual(len(issues), 1)

    def test_action_marker_excluded(self):
        # "action:" was removed as too noisy — must not trigger
        self._old_note("action.md", "# Title\n\naction: Get Contents of URL\n")
        issues = fd.check_notes_without_follow_up()
        self.assertEqual(issues, [])

    def test_plain_note_excluded(self):
        self._old_note("plain.md", "# Title\n\nJust a note, nothing to do.\n")
        self.assertEqual(fd.check_notes_without_follow_up(), [])

    def test_fresh_note_with_todo_excluded(self):
        p = NOTES_DIR / "fresh.md"
        p.write_text("# Title\n\n- [ ] Still new\n")
        # mtime is now (default) — less than 7 days
        issues = fd.check_notes_without_follow_up()
        self.assertEqual(issues, [])
        p.unlink()


# ── main ──────────────────────────────────────────────────────────────────────

class TestMain(unittest.TestCase):
    def _friction_file(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        return RESULTS_DIR / f"friction-{today}.txt"

    def setUp(self):
        p = self._friction_file()
        if p.exists():
            p.unlink()

    def tearDown(self):
        p = self._friction_file()
        if p.exists():
            p.unlink()

    def test_already_done_skips_rerun(self):
        p = self._friction_file()
        p.write_text("existing result")
        fd.main()
        self.assertEqual(p.read_text(), "existing result")

    def test_no_issues_writes_clean_message(self):
        with patch.object(fd, "check_pending_questions", return_value=[]), \
             patch.object(fd, "check_stale_tasks", return_value=[]), \
             patch.object(fd, "check_github_issues", return_value=[]), \
             patch.object(fd, "check_overdue_reminders", return_value=[]), \
             patch.object(fd, "check_notes_without_follow_up", return_value=[]):
            fd.main()
        content = self._friction_file().read_text()
        self.assertIn("No friction", content)

    def test_issues_written_as_numbered_list(self):
        with patch.object(fd, "check_pending_questions", return_value=["Issue A"]), \
             patch.object(fd, "check_stale_tasks", return_value=["Issue B"]), \
             patch.object(fd, "check_github_issues", return_value=[]), \
             patch.object(fd, "check_overdue_reminders", return_value=[]), \
             patch.object(fd, "check_notes_without_follow_up", return_value=[]):
            fd.main()
        content = self._friction_file().read_text()
        self.assertIn("Issue A", content)
        self.assertIn("Issue B", content)
        self.assertIn("2 item", content)

    def test_output_file_created_in_results_dir(self):
        with patch.object(fd, "check_pending_questions", return_value=[]), \
             patch.object(fd, "check_stale_tasks", return_value=[]), \
             patch.object(fd, "check_github_issues", return_value=[]), \
             patch.object(fd, "check_overdue_reminders", return_value=[]), \
             patch.object(fd, "check_notes_without_follow_up", return_value=[]):
            fd.main()
        self.assertTrue(self._friction_file().exists())


if __name__ == "__main__":
    unittest.main()
