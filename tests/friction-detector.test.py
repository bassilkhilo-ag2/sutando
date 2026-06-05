"""Unit tests for src/friction-detector.py.

Run: `python3 tests/friction-detector.test.py`
"""
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "friction-detector.py"

sys.path.insert(0, str(ROOT / "src"))

# Patch util_paths before loading the module so shared_personal_path and
# personal_path resolve to tmp workspace subdirs rather than real paths.
import util_paths as _up  # noqa: E402


def _load(workspace: Path):
    os.environ["SUTANDO_WORKSPACE"] = str(workspace)
    orig_shared = _up.shared_personal_path
    orig_personal = _up.personal_path
    _up.shared_personal_path = lambda name, ws=None: str(workspace / name)
    _up.personal_path = lambda name, ws=None: str(workspace / name)
    try:
        spec = importlib.util.spec_from_file_location("friction_detector", SRC)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        _up.shared_personal_path = orig_shared
        _up.personal_path = orig_personal
    mod.WORKSPACE = workspace
    mod.RESULTS_DIR = workspace / "results"
    return mod


class TestCheckPendingQuestions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def _pq(self, content: str):
        pq = self.ws / "pending-questions.md"
        pq.write_text(content)

    def test_missing_file_returns_empty(self):
        self.assertEqual(self.mod.check_pending_questions(), [])

    def test_no_pending_marker_returns_empty(self):
        self._pq("(No pending questions)")
        self.assertEqual(self.mod.check_pending_questions(), [])

    def test_unanswered_question_detected(self):
        self._pq(
            "## Should I open the PR?\n\n"
            "- **Asked:** 2024-01-01\n"
            "- **Status:** unanswered\n\n"
            "Details.\n"
        )
        issues = self.mod.check_pending_questions()
        self.assertEqual(len(issues), 1)
        self.assertIn("Should I open the PR", issues[0])

    def test_resolved_status_excluded(self):
        self._pq(
            "## Old question\n\n"
            "- **Asked:** 2024-01-01\n"
            "- **Status:** resolved\n\n"
            "Never mind.\n"
        )
        self.assertEqual(self.mod.check_pending_questions(), [])

    def test_age_included_in_output(self):
        self._pq(
            "## Age test\n\n"
            "- **Asked:** 2024-01-01\n"
            "- **Status:** unanswered\n"
        )
        issues = self.mod.check_pending_questions()
        self.assertEqual(len(issues), 1)
        self.assertIn("d old", issues[0])

    def test_multiple_questions_mixed_status(self):
        self._pq(
            "## Pending one\n\n- **Asked:** 2024-01-01\n- **Status:** unanswered\n\n"
            "## Already done\n\n- **Asked:** 2024-01-02\n- **Status:** resolved\n\n"
            "## Pending two\n\n- **Asked:** 2024-01-03\n- **Status:** unanswered\n"
        )
        issues = self.mod.check_pending_questions()
        self.assertEqual(len(issues), 2)

    def test_no_status_field_not_included(self):
        # Sections without a Status field are not flagged as unanswered
        self._pq("## Question without status\n\nSome prose.\n")
        self.assertEqual(self.mod.check_pending_questions(), [])


class TestCheckStaleTasks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_no_tasks_dir_returns_empty(self):
        self.assertEqual(self.mod.check_stale_tasks(), [])

    def test_empty_tasks_dir_returns_empty(self):
        (self.ws / "tasks").mkdir()
        self.assertEqual(self.mod.check_stale_tasks(), [])

    def test_recent_task_not_flagged(self):
        tasks = self.ws / "tasks"
        tasks.mkdir()
        (tasks / "task-123.txt").write_text("id: task-123")
        self.assertEqual(self.mod.check_stale_tasks(), [])

    def test_stale_task_flagged(self):
        tasks = self.ws / "tasks"
        tasks.mkdir()
        stale = tasks / "task-456.txt"
        stale.write_text("id: task-456")
        old_mtime = time.time() - 7200  # 2 hours ago
        os.utime(stale, (old_mtime, old_mtime))
        issues = self.mod.check_stale_tasks()
        self.assertEqual(len(issues), 1)
        self.assertIn("task-456.txt", issues[0])
        self.assertIn("2h", issues[0])

    def test_only_task_prefix_files_scanned(self):
        tasks = self.ws / "tasks"
        tasks.mkdir()
        other = tasks / "result-123.txt"
        other.write_text("not a task")
        old_mtime = time.time() - 7200
        os.utime(other, (old_mtime, old_mtime))
        self.assertEqual(self.mod.check_stale_tasks(), [])

    def test_multiple_stale_tasks(self):
        tasks = self.ws / "tasks"
        tasks.mkdir()
        for i in range(3):
            f = tasks / f"task-{i}.txt"
            f.write_text(f"id: task-{i}")
            old_mtime = time.time() - 7200
            os.utime(f, (old_mtime, old_mtime))
        self.assertEqual(len(self.mod.check_stale_tasks()), 3)


class TestCheckGithubIssues(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_gh_not_found_returns_empty(self):
        # FileNotFoundError → caught, returns []
        with patch("subprocess.run", side_effect=FileNotFoundError):
            self.assertEqual(self.mod.check_github_issues(), [])

    def test_gh_timeout_returns_empty(self):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 10)):
            self.assertEqual(self.mod.check_github_issues(), [])

    def test_stale_issue_flagged(self):
        import json as _json
        import subprocess
        stale_date = "2020-01-01T00:00:00Z"
        payload = _json.dumps([
            {"number": 99, "title": "Old bug", "updatedAt": stale_date}
        ])
        fake = type("R", (), {"returncode": 0, "stdout": payload})()
        with patch("subprocess.run", return_value=fake):
            issues = self.mod.check_github_issues()
        self.assertEqual(len(issues), 1)
        self.assertIn("#99", issues[0])
        self.assertIn("Old bug", issues[0])

    def test_recent_issue_not_flagged(self):
        import json as _json
        from datetime import datetime, timezone
        recent = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = _json.dumps([
            {"number": 1, "title": "Fresh", "updatedAt": recent}
        ])
        fake = type("R", (), {"returncode": 0, "stdout": payload})()
        with patch("subprocess.run", return_value=fake):
            issues = self.mod.check_github_issues()
        self.assertEqual(issues, [])

    def test_gh_nonzero_exit_returns_empty(self):
        fake = type("R", (), {"returncode": 1, "stdout": ""})()
        with patch("subprocess.run", return_value=fake):
            self.assertEqual(self.mod.check_github_issues(), [])


class TestCheckNotesWithoutFollowUp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        self.notes = self.ws / "notes"
        self.notes.mkdir()
        # Override shared_personal_path to point to tmp notes dir
        import util_paths as up
        self._orig_shared = up.shared_personal_path
        up.shared_personal_path = lambda name, ws=None: str(self.ws / name)

    def tearDown(self):
        import util_paths as up
        up.shared_personal_path = self._orig_shared
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def _note(self, name: str, content: str, days_old: float = 0):
        p = self.notes / name
        p.write_text(content)
        if days_old > 0:
            mtime = time.time() - days_old * 86400
            os.utime(p, (mtime, mtime))
        return p

    def test_no_notes_dir_returns_empty(self):
        import shutil
        shutil.rmtree(self.notes)
        self.assertEqual(self.mod.check_notes_without_follow_up(), [])

    def test_recent_checkbox_note_not_flagged(self):
        self._note("recent.md", "# Plan\n- [ ] fix thing\n", days_old=0)
        self.assertEqual(self.mod.check_notes_without_follow_up(), [])

    def test_old_checkbox_note_flagged(self):
        self._note("old-plan.md", "# Old Plan\n- [ ] fix thing\n", days_old=8)
        issues = self.mod.check_notes_without_follow_up()
        self.assertEqual(len(issues), 1)
        self.assertIn("Old Plan", issues[0])

    def test_old_todo_prefix_flagged(self):
        self._note("tasks.md", "# Tasks\ntodo: review the PR\n", days_old=8)
        issues = self.mod.check_notes_without_follow_up()
        self.assertGreater(len(issues), 0)

    def test_old_follow_up_prefix_flagged(self):
        self._note("followup.md", "# Note\nfollow-up: check status\n", days_old=8)
        issues = self.mod.check_notes_without_follow_up()
        self.assertGreater(len(issues), 0)

    def test_action_colon_not_flagged(self):
        # 'action:' was removed from markers — too noisy (Apple Shortcuts prose)
        self._note("action.md", "# Shortcut\naction: Get Contents of URL\n", days_old=8)
        issues = self.mod.check_notes_without_follow_up()
        action_issues = [i for i in issues if "Action" in i]
        self.assertEqual(action_issues, [])

    def test_tags_todo_flagged(self):
        self._note("tagged.md", "# Tagged\ntags: [startup, todo, funding]\n", days_old=8)
        issues = self.mod.check_notes_without_follow_up()
        self.assertGreater(len(issues), 0)

    def test_note_without_markers_not_flagged(self):
        self._note("clean.md", "# Clean\nJust some prose notes here.\n", days_old=8)
        self.assertEqual(self.mod.check_notes_without_follow_up(), [])


class TestMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        self.mod.RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_main_creates_results_file(self):
        with patch.object(self.mod, "check_pending_questions", return_value=[]):
            with patch.object(self.mod, "check_stale_tasks", return_value=[]):
                with patch.object(self.mod, "check_github_issues", return_value=[]):
                    with patch.object(self.mod, "check_overdue_reminders", return_value=[]):
                        with patch.object(self.mod, "check_notes_without_follow_up", return_value=[]):
                            self.mod.main()
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        output = self.mod.RESULTS_DIR / f"friction-{today}.txt"
        self.assertTrue(output.exists())
        self.assertIn("No friction", output.read_text())

    def test_main_skips_if_already_done_today(self):
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        output = self.mod.RESULTS_DIR / f"friction-{today}.txt"
        output.write_text("already done")
        # If called again, should not overwrite
        with patch.object(self.mod, "check_pending_questions", return_value=["issue"]) as mock_check:
            self.mod.main()
            mock_check.assert_not_called()
        self.assertEqual(output.read_text(), "already done")

    def test_main_lists_issues_when_found(self):
        with patch.object(self.mod, "check_pending_questions", return_value=["Q1 unanswered"]):
            with patch.object(self.mod, "check_stale_tasks", return_value=[]):
                with patch.object(self.mod, "check_github_issues", return_value=[]):
                    with patch.object(self.mod, "check_overdue_reminders", return_value=[]):
                        with patch.object(self.mod, "check_notes_without_follow_up", return_value=[]):
                            self.mod.main()
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        content = (self.mod.RESULTS_DIR / f"friction-{today}.txt").read_text()
        self.assertIn("1 item", content)
        self.assertIn("Q1 unanswered", content)


if __name__ == "__main__":
    unittest.main()
