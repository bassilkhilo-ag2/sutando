#!/usr/bin/env python3
"""
Tests for src/check-pending-questions.py

Coverage:
  get_waiting_questions — no file, empty, unanswered/waiting/answered/resolved/no-status,
    multi-section filtering, title truncation at 40 chars, legacy Q1 format
  should_notify          — no sentinel (first run), recent sentinel (cooldown), old sentinel
  presenter_mode_active  — no sentinel, future expiry, past expiry, malformed content,
    digit-guard blocks compare-trick
  voice_client_connected — no log, client=true, client=false, last health line wins,
    no health line, health line without client field
  notify_discord_dm      — file created in results/, contains title, singular/plural
    wording, >5 truncation, contains instructions
  notify_voice           — file created in results/, contains title, multiple titles
    joined, singular/plural wording

Run: python3 tests/check-pending-questions.test.py
Exit code: 0 on pass, 1 on fail.
"""

import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TMPDIR = Path(tempfile.mkdtemp())

# Inject fake dependencies before exec_module resolves them at import time.
_fake_wd = type(sys)("workspace_default")
_fake_wd.resolve_workspace = lambda: TMPDIR
sys.modules["workspace_default"] = _fake_wd

_fake_up = type(sys)("util_paths")
_fake_up.personal_path = lambda name, workspace: str(Path(workspace) / name)
sys.modules["util_paths"] = _fake_up

_spec = importlib.util.spec_from_file_location(
    "check_pending_questions",
    REPO / "src" / "check-pending-questions.py",
)
cpq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cpq)

# Create dirs the module writes into.
for _d in ("state", "results", "logs"):
    (TMPDIR / _d).mkdir(parents=True, exist_ok=True)


class TestGetWaitingQuestions(unittest.TestCase):
    def tearDown(self):
        if cpq.PQ_FILE.exists():
            cpq.PQ_FILE.unlink()

    def test_no_file_returns_empty(self):
        if cpq.PQ_FILE.exists():
            cpq.PQ_FILE.unlink()
        self.assertEqual(cpq.get_waiting_questions(), [])

    def test_empty_file_returns_empty(self):
        cpq.PQ_FILE.write_text("")
        self.assertEqual(cpq.get_waiting_questions(), [])

    def test_unanswered_status_detected(self):
        cpq.PQ_FILE.write_text(
            "## Should we migrate the DB?\n\n**Status:** unanswered\n\nDetails.\n"
        )
        qs = cpq.get_waiting_questions()
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0]["title"], "Should we migrate the DB?")

    def test_waiting_status_detected(self):
        cpq.PQ_FILE.write_text(
            "## Approve the PR?\n\n**Status:** waiting on Bassil\n"
        )
        qs = cpq.get_waiting_questions()
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0]["title"], "Approve the PR?")

    def test_answered_status_excluded(self):
        cpq.PQ_FILE.write_text("## Old question\n\n**Status:** answered\n")
        self.assertEqual(cpq.get_waiting_questions(), [])

    def test_resolved_status_excluded(self):
        cpq.PQ_FILE.write_text("## Done\n\n**Status:** resolved\n")
        self.assertEqual(cpq.get_waiting_questions(), [])

    def test_no_status_field_excluded(self):
        cpq.PQ_FILE.write_text("## No status here\n\nJust text.\n")
        self.assertEqual(cpq.get_waiting_questions(), [])

    def test_multiple_sections_filtered(self):
        cpq.PQ_FILE.write_text(
            "## Q1\n\n**Status:** unanswered\n\n"
            "## Q2\n\n**Status:** answered\n\n"
            "## Q3\n\n**Status:** waiting\n"
        )
        qs = cpq.get_waiting_questions()
        self.assertEqual(len(qs), 2)
        titles = [q["title"] for q in qs]
        self.assertIn("Q1", titles)
        self.assertIn("Q3", titles)
        self.assertNotIn("Q2", titles)

    def test_title_truncated_at_40_chars(self):
        long_title = "A" * 50
        cpq.PQ_FILE.write_text(f"## {long_title}\n\n**Status:** unanswered\n")
        qs = cpq.get_waiting_questions()
        self.assertEqual(len(qs), 1)
        self.assertLessEqual(len(qs[0]["id"]), 40)

    def test_legacy_q1_format(self):
        cpq.PQ_FILE.write_text(
            "## Q1 — Old style question\n\n**Status:** unanswered\n"
        )
        qs = cpq.get_waiting_questions()
        self.assertEqual(len(qs), 1)
        self.assertIn("Q1", qs[0]["title"])


class TestShouldNotify(unittest.TestCase):
    def tearDown(self):
        if cpq.LAST_NOTIFY_FILE.exists():
            cpq.LAST_NOTIFY_FILE.unlink()

    def test_no_sentinel_returns_true(self):
        if cpq.LAST_NOTIFY_FILE.exists():
            cpq.LAST_NOTIFY_FILE.unlink()
        self.assertTrue(cpq.should_notify())

    def test_recent_sentinel_returns_false(self):
        cpq.LAST_NOTIFY_FILE.write_text(str(int(time.time())))
        self.assertFalse(cpq.should_notify())

    def test_old_sentinel_returns_true(self):
        cpq.LAST_NOTIFY_FILE.write_text("x")
        old_mtime = time.time() - 7200  # 2 hours ago
        os.utime(cpq.LAST_NOTIFY_FILE, (old_mtime, old_mtime))
        self.assertTrue(cpq.should_notify())


class TestPresenterModeActive(unittest.TestCase):
    def tearDown(self):
        if cpq.PRESENTER_SENTINEL.exists():
            cpq.PRESENTER_SENTINEL.unlink()

    def test_no_sentinel_returns_false(self):
        if cpq.PRESENTER_SENTINEL.exists():
            cpq.PRESENTER_SENTINEL.unlink()
        self.assertFalse(cpq.presenter_mode_active())

    def test_future_expiry_returns_true(self):
        future = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
        cpq.PRESENTER_SENTINEL.write_text(future)
        self.assertTrue(cpq.presenter_mode_active())

    def test_past_expiry_returns_false(self):
        past = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
        cpq.PRESENTER_SENTINEL.write_text(past)
        self.assertFalse(cpq.presenter_mode_active())

    def test_malformed_garbage_returns_false(self):
        # Starts with 'g', not a digit — digit guard fires.
        cpq.PRESENTER_SENTINEL.write_text("garbage content")
        self.assertFalse(cpq.presenter_mode_active())

    def test_empty_sentinel_returns_false(self):
        cpq.PRESENTER_SENTINEL.write_text("")
        self.assertFalse(cpq.presenter_mode_active())

    def test_digit_guard_blocks_compare_trick(self):
        # "yes" < any ISO date — without the digit guard this would appear active.
        cpq.PRESENTER_SENTINEL.write_text("yes still active")
        self.assertFalse(cpq.presenter_mode_active())


class TestVoiceClientConnected(unittest.TestCase):
    def setUp(self):
        cpq.VOICE_LOG.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if cpq.VOICE_LOG.exists():
            cpq.VOICE_LOG.unlink()

    def test_no_log_file_returns_false(self):
        if cpq.VOICE_LOG.exists():
            cpq.VOICE_LOG.unlink()
        self.assertFalse(cpq.voice_client_connected())

    def test_client_true_in_last_health_line(self):
        cpq.VOICE_LOG.write_text(
            "[Info] Some log\n[Health] latency=20ms client=true models=2\n"
        )
        self.assertTrue(cpq.voice_client_connected())

    def test_client_false_in_last_health_line(self):
        cpq.VOICE_LOG.write_text("[Health] latency=20ms client=false models=0\n")
        self.assertFalse(cpq.voice_client_connected())

    def test_last_health_line_wins_over_earlier_line(self):
        # Reversed iteration — last [Health] in file is first match.
        cpq.VOICE_LOG.write_text(
            "[Health] client=false\n[Info] something\n[Health] client=true\n"
        )
        self.assertTrue(cpq.voice_client_connected())

    def test_no_health_line_returns_false(self):
        cpq.VOICE_LOG.write_text("[Info] only info\n[Debug] debug stuff\n")
        self.assertFalse(cpq.voice_client_connected())

    def test_health_line_without_client_field_returns_false(self):
        cpq.VOICE_LOG.write_text("[Health] latency=30ms models=1\n")
        self.assertFalse(cpq.voice_client_connected())


class TestNotifyDiscordDm(unittest.TestCase):
    def _results_files(self):
        return list(cpq.RESULTS_DIR.glob("proactive-pending-q-*.txt"))

    def tearDown(self):
        for f in self._results_files():
            f.unlink()

    def test_creates_file_in_results(self):
        cpq.notify_discord_dm([{"id": "Q1", "title": "Fix the bug?"}])
        self.assertEqual(len(self._results_files()), 1)

    def test_file_contains_question_title(self):
        cpq.notify_discord_dm([{"id": "Q1", "title": "Can we deploy today?"}])
        content = self._results_files()[0].read_text()
        self.assertIn("Can we deploy today?", content)

    def test_single_question_singular_wording(self):
        cpq.notify_discord_dm([{"id": "Q1", "title": "Any title"}])
        content = self._results_files()[0].read_text()
        self.assertIn("1 pending question", content)
        self.assertNotIn("1 pending questions", content)

    def test_multiple_questions_plural_wording(self):
        qs = [{"id": f"Q{i}", "title": f"Title {i}"} for i in range(3)]
        cpq.notify_discord_dm(qs)
        content = self._results_files()[0].read_text()
        self.assertIn("3 pending questions", content)

    def test_more_than_5_shows_overflow_count(self):
        qs = [{"id": f"Q{i}", "title": f"Title {i}"} for i in range(7)]
        cpq.notify_discord_dm(qs)
        content = self._results_files()[0].read_text()
        self.assertIn("2 more", content)

    def test_file_contains_resolve_instructions(self):
        cpq.notify_discord_dm([{"id": "Q1", "title": "Any"}])
        content = self._results_files()[0].read_text()
        self.assertIn("pending-questions.md", content)


class TestNotifyVoice(unittest.TestCase):
    def _results_files(self):
        return list(cpq.RESULTS_DIR.glob("question-*.txt"))

    def tearDown(self):
        for f in self._results_files():
            f.unlink()

    def test_creates_question_file(self):
        cpq.notify_voice([{"id": "Q1", "title": "What should we do?"}])
        self.assertEqual(len(self._results_files()), 1)

    def test_file_contains_title(self):
        cpq.notify_voice([{"id": "Q1", "title": "What should we do?"}])
        content = self._results_files()[0].read_text()
        self.assertIn("What should we do?", content)

    def test_multiple_titles_both_present(self):
        qs = [{"id": "Q1", "title": "First?"}, {"id": "Q2", "title": "Second?"}]
        cpq.notify_voice(qs)
        content = self._results_files()[0].read_text()
        self.assertIn("First?", content)
        self.assertIn("Second?", content)

    def test_singular_wording_for_one(self):
        cpq.notify_voice([{"id": "Q1", "title": "Solo"}])
        content = self._results_files()[0].read_text()
        self.assertIn("1 pending question ", content)
        self.assertNotIn("1 pending questions", content)

    def test_plural_wording_for_many(self):
        qs = [{"id": f"Q{i}", "title": f"T{i}"} for i in range(3)]
        cpq.notify_voice(qs)
        content = self._results_files()[0].read_text()
        self.assertIn("3 pending questions", content)


if __name__ == "__main__":
    unittest.main()
