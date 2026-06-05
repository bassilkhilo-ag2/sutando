"""Unit tests for src/check-pending-questions.py.

Run: `python3 tests/check-pending-questions.test.py`
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
SRC = ROOT / "src" / "check-pending-questions.py"

sys.path.insert(0, str(ROOT / "src"))


def _load(workspace: Path):
    os.environ["SUTANDO_WORKSPACE"] = str(workspace)
    spec = importlib.util.spec_from_file_location("check_pending_questions", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPresenterModeActive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def _sentinel(self):
        sentinel = self.ws / "state" / "presenter-mode.sentinel"
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        return sentinel

    def test_no_sentinel_returns_false(self):
        self.assertFalse(self.mod.presenter_mode_active())

    def test_future_expiry_returns_true(self):
        s = self._sentinel()
        future = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 3600))
        s.write_text(future)
        self.mod.PRESENTER_SENTINEL = s
        self.assertTrue(self.mod.presenter_mode_active())

    def test_past_expiry_returns_false(self):
        s = self._sentinel()
        past = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 3600))
        s.write_text(past)
        self.mod.PRESENTER_SENTINEL = s
        self.assertFalse(self.mod.presenter_mode_active())

    def test_malformed_content_returns_false(self):
        s = self._sentinel()
        s.write_text("garbage")
        self.mod.PRESENTER_SENTINEL = s
        self.assertFalse(self.mod.presenter_mode_active())

    def test_empty_content_returns_false(self):
        s = self._sentinel()
        s.write_text("")
        self.mod.PRESENTER_SENTINEL = s
        self.assertFalse(self.mod.presenter_mode_active())


class TestVoiceClientConnected(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def _voice_log(self):
        log = self.ws / "logs" / "voice-agent.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        return log

    def test_no_log_returns_false(self):
        self.mod.VOICE_LOG = self.ws / "logs" / "voice-agent.log"
        self.assertFalse(self.mod.voice_client_connected())

    def test_client_true_returns_true(self):
        log = self._voice_log()
        log.write_text("[Health] status=ok client=true latency=20ms\n")
        self.mod.VOICE_LOG = log
        self.assertTrue(self.mod.voice_client_connected())

    def test_client_false_returns_false(self):
        log = self._voice_log()
        log.write_text("[Health] status=ok client=false latency=0ms\n")
        self.mod.VOICE_LOG = log
        self.assertFalse(self.mod.voice_client_connected())

    def test_no_health_line_returns_false(self):
        log = self._voice_log()
        log.write_text("Some other log line without Health keyword\n")
        self.mod.VOICE_LOG = log
        self.assertFalse(self.mod.voice_client_connected())

    def test_most_recent_health_line_wins(self):
        log = self._voice_log()
        log.write_text(
            "[Health] client=true latency=5ms\n"
            "[Health] client=false latency=0ms\n"
        )
        self.mod.VOICE_LOG = log
        # Most recent (last line) says false.
        self.assertFalse(self.mod.voice_client_connected())


class TestGetWaitingQuestions(unittest.TestCase):
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
        self.mod.PQ_FILE = pq
        return pq

    def test_missing_file_returns_empty(self):
        self.mod.PQ_FILE = self.ws / "pending-questions.md"
        self.assertEqual(self.mod.get_waiting_questions(), [])

    def test_free_form_section_counts_as_unanswered(self):
        self._pq("# Pending Questions\n\n## Fix the bug\n\nSome prose description.\n")
        qs = self.mod.get_waiting_questions()
        self.assertEqual(len(qs), 1)
        self.assertIn("Fix the bug", qs[0]["title"])

    def test_explicit_unanswered_status_included(self):
        self._pq("## My question\n\n**Status:** unanswered\n\nDetails.\n")
        qs = self.mod.get_waiting_questions()
        self.assertEqual(len(qs), 1)

    def test_explicit_waiting_status_included(self):
        self._pq("## Waiting question\n\n**Status:** Waiting on Bassil\n")
        qs = self.mod.get_waiting_questions()
        self.assertEqual(len(qs), 1)

    def test_resolved_status_excluded(self):
        self._pq("## Old question\n\n**Status:** resolved\n\nNever mind.\n")
        qs = self.mod.get_waiting_questions()
        self.assertEqual(len(qs), 0)

    def test_done_status_excluded(self):
        self._pq("## Another\n\n**Status:** done\n")
        qs = self.mod.get_waiting_questions()
        self.assertEqual(len(qs), 0)

    def test_resolved_divider_stops_parsing(self):
        content = (
            "## Active question\n\nStill open.\n\n"
            "# Resolved\n\n"
            "## Old question\n\nDone long ago.\n"
        )
        self._pq(content)
        qs = self.mod.get_waiting_questions()
        self.assertEqual(len(qs), 1)
        self.assertIn("Active question", qs[0]["title"])

    def test_multiple_questions(self):
        content = "## Q1\n\nOpen.\n\n## Q2\n\nAlso open.\n"
        self._pq(content)
        qs = self.mod.get_waiting_questions()
        self.assertEqual(len(qs), 2)

    def test_empty_file_returns_empty(self):
        self._pq("")
        self.assertEqual(self.mod.get_waiting_questions(), [])


class TestShouldNotify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_no_last_notify_file_returns_true(self):
        self.mod.LAST_NOTIFY_FILE = self.ws / ".last-pq-notify"
        self.assertTrue(self.mod.should_notify())

    def test_recent_notify_returns_false(self):
        f = self.ws / ".last-pq-notify"
        f.write_text(str(int(time.time())))
        self.mod.LAST_NOTIFY_FILE = f
        self.assertFalse(self.mod.should_notify())

    def test_old_notify_returns_true(self):
        f = self.ws / ".last-pq-notify"
        f.write_text(str(int(time.time())))
        old_mtime = time.time() - 7200  # 2 hours ago
        os.utime(f, (old_mtime, old_mtime))
        self.mod.LAST_NOTIFY_FILE = f
        self.assertTrue(self.mod.should_notify())


class TestNotifyVoice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        results = self.ws / "results"
        results.mkdir()
        self.mod.RESULTS_DIR = results

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_writes_question_file(self):
        questions = [{"title": "Fix the deploy", "id": "Fix the deploy"}]
        self.mod.notify_voice(questions)
        files = list((self.ws / "results").glob("question-*.txt"))
        self.assertEqual(len(files), 1)
        self.assertIn("Fix the deploy", files[0].read_text())


class TestNotifyDiscordDm(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        results = self.ws / "results"
        results.mkdir()
        self.mod.RESULTS_DIR = results

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_writes_proactive_file(self):
        questions = [{"title": "Deploy now?", "id": "Deploy now?"}]
        self.mod.notify_discord_dm(questions)
        files = list((self.ws / "results").glob("proactive-pending-q-*.txt"))
        self.assertEqual(len(files), 1)
        self.assertIn("Deploy now?", files[0].read_text())

    def test_caps_at_five_in_output(self):
        questions = [{"title": f"Q{i}", "id": f"Q{i}"} for i in range(7)]
        self.mod.notify_discord_dm(questions)
        files = list((self.ws / "results").glob("proactive-pending-q-*.txt"))
        body = files[0].read_text()
        self.assertIn("2 more", body)


if __name__ == "__main__":
    unittest.main()
