"""Unit tests for src/morning-briefing.py.

Run: `python3 tests/morning-briefing.test.py`
"""
import importlib.util
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "morning-briefing.py"

sys.path.insert(0, str(ROOT / "src"))


def _load(workspace: Path):
    os.environ["SUTANDO_WORKSPACE"] = str(workspace)
    spec = importlib.util.spec_from_file_location("morning_briefing", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.WORKSPACE = workspace
    mod.RESULTS_DIR = workspace / "results"
    mod.LOGS_DIR = workspace / "logs"
    mod.STATE_DIR = workspace / "state"
    return mod


class TestGetPendingQuestions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def _pq(self, content: str):
        f = self.ws / "pending-questions.md"
        f.write_text(content)

    def test_missing_file_returns_empty(self):
        self.assertEqual(self.mod.get_pending_questions(), [])

    def test_unanswered_question_returned(self):
        self._pq("## Should I open the PR?\n\nDetails.\n")
        qs = self.mod.get_pending_questions()
        self.assertEqual(len(qs), 1)
        self.assertIn("Should I open the PR", qs[0])

    def test_multiple_questions_all_returned(self):
        self._pq("## Q1\n\nText.\n\n## Q2\n\nMore.\n")
        self.assertEqual(len(self.mod.get_pending_questions()), 2)

    def test_resolved_divider_stops_parsing(self):
        self._pq("## Active\n\nOpen.\n\n# Resolved\n\n## Old\n\nDone.\n")
        qs = self.mod.get_pending_questions()
        self.assertEqual(len(qs), 1)
        self.assertIn("Active", qs[0])

    def test_dated_prefix_stripped(self):
        self._pq("## [2026-05-27] Fix the deploy\n\nDetails.\n")
        qs = self.mod.get_pending_questions()
        self.assertEqual(len(qs), 1)
        self.assertNotIn("[2026-05-27]", qs[0])
        self.assertIn("Fix the deploy", qs[0])

    def test_title_truncated_at_60_chars(self):
        long_title = "A" * 100
        self._pq(f"## {long_title}\n\nText.\n")
        qs = self.mod.get_pending_questions()
        self.assertEqual(len(qs), 1)
        self.assertLessEqual(len(qs[0]), 60)


class TestGetOvernightDiscord(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        self.logs = self.ws / "logs"
        self.logs.mkdir()
        self.mod.LOGS_DIR = self.logs

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_missing_log_returns_empty(self):
        self.assertEqual(self.mod.get_overnight_discord(), [])

    def test_dm_message_extracted(self):
        log = self.logs / "discord-bridge.log"
        log.write_text("[msg] #DM @alice: hello there (mentions: [] is_dm: True)\n")
        msgs = self.mod.get_overnight_discord()
        self.assertEqual(len(msgs), 1)
        self.assertIn("alice", msgs[0])
        self.assertIn("hello there", msgs[0])

    def test_sutando_bot_messages_filtered(self):
        log = self.logs / "discord-bridge.log"
        log.write_text("[msg] #DM @Sutando: my response (mentions: [] is_dm: True)\n")
        self.assertEqual(self.mod.get_overnight_discord(), [])

    def test_non_dm_lines_skipped(self):
        log = self.logs / "discord-bridge.log"
        log.write_text("[msg] #general @alice: public (mentions: [])\n")
        self.assertEqual(self.mod.get_overnight_discord(), [])

    def test_capped_at_five(self):
        log = self.logs / "discord-bridge.log"
        lines = "\n".join(
            f"[msg] #DM @user{i}: msg (mentions: [] is_dm: True)"
            for i in range(10)
        )
        log.write_text(lines + "\n")
        msgs = self.mod.get_overnight_discord()
        self.assertLessEqual(len(msgs), 5)


class TestSynthesize(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def _synth(self, weather=None, events=None, reminders=None,
               discord=None, pending=None, health=None, insight=None):
        return self.mod.synthesize(
            weather,
            events or [],
            reminders or [],
            discord or [],
            pending or [],
            health or [],
            insight,
        )

    def test_starts_with_greeting(self):
        result = self._synth()
        self.assertTrue(
            result.startswith("Good morning") or
            result.startswith("Good afternoon") or
            result.startswith("Good evening")
        )

    def test_weather_included(self):
        result = self._synth(weather="72°F and clear, high of 80, low of 60")
        self.assertIn("72°F", result)

    def test_no_weather_no_weather_text(self):
        result = self._synth()
        self.assertNotIn("°F", result)

    def test_clear_calendar_message(self):
        result = self._synth()
        self.assertIn("clear today", result)

    def test_one_event_singular(self):
        result = self._synth(events=[{"raw": "10:00am Standup", "calendar": "Work"}])
        self.assertIn("One meeting today", result)
        self.assertIn("10:00am Standup", result)

    def test_multiple_events_shows_first(self):
        events = [{"raw": "9am A", "calendar": "W"}, {"raw": "11am B", "calendar": "W"}]
        result = self._synth(events=events)
        self.assertIn("2 meetings", result)
        self.assertIn("9am A", result)

    def test_reminders_included(self):
        result = self._synth(reminders=["Buy milk", "Call dentist"])
        self.assertIn("Reminders due", result)
        self.assertIn("Buy milk", result)

    def test_one_pending_question_singular(self):
        result = self._synth(pending=["Fix the PR?"])
        self.assertIn("One pending question", result)
        self.assertIn("Fix the PR?", result)

    def test_multiple_pending_questions(self):
        result = self._synth(pending=["Q1", "Q2"])
        self.assertIn("2 pending questions", result)
        self.assertIn("Q1", result)

    def test_discord_messages_mentioned(self):
        result = self._synth(discord=["alice: hello"])
        self.assertIn("Discord message", result)

    def test_multiple_discord_messages_plural(self):
        result = self._synth(discord=["alice: hi", "bob: hey"])
        self.assertIn("2 Discord messages", result)

    def test_health_issues_included(self):
        result = self._synth(health=["api: port down"])
        self.assertIn("System note", result)
        self.assertIn("api: port down", result)

    def test_clean_day_closing_message(self):
        result = self._synth()
        self.assertIn("Good day for deep work", result)

    def test_insight_included_when_valid(self):
        result = self._synth(insight="Peak call hours are 10am. More data here.")
        self.assertIn("Insight:", result)
        self.assertIn("Peak call hours are 10am", result)

    def test_insight_skipped_when_raw_data(self):
        # Contains '{' → skip as raw JSON/dict data
        result = self._synth(insight='{"calls": 5, "hours": [10, 11]}')
        self.assertNotIn("Insight:", result)

    def test_insight_skipped_when_too_short(self):
        # First sentence ≤ 20 chars → skip
        result = self._synth(insight="Meh. More here.")
        self.assertNotIn("Insight:", result)

    def test_insight_skipped_when_too_many_colons(self):
        # First sentence has > 2 colons (raw data marker)
        result = self._synth(insight="key: val: other: more than two colons here.")
        self.assertNotIn("Insight:", result)

    def test_clean_day_suppressed_when_events_present(self):
        result = self._synth(events=[{"raw": "9am Meeting", "calendar": "W"}])
        self.assertNotIn("Good day for deep work", result)


class TestWeatherCodes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_clear_code(self):
        self.assertEqual(self.mod.WEATHER_CODES[0], "clear")

    def test_stormy_code(self):
        self.assertEqual(self.mod.WEATHER_CODES[95], "stormy")

    def test_unknown_code_fallback(self):
        self.assertEqual(self.mod.WEATHER_CODES.get(999, "variable"), "variable")

    def test_rain_codes_present(self):
        self.assertIn(61, self.mod.WEATHER_CODES)
        self.assertEqual(self.mod.WEATHER_CODES[65], "heavy rain")


class TestMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        self.mod.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        self.mod.STATE_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def _run_main(self):
        with patch.object(self.mod, "get_weather", return_value="72°F and clear"):
            with patch.object(self.mod, "get_calendar_events", return_value=[]):
                with patch.object(self.mod, "get_reminders", return_value=[]):
                    with patch.object(self.mod, "get_overnight_discord", return_value=[]):
                        with patch.object(self.mod, "get_daily_insight", return_value=None):
                            with patch.object(self.mod, "get_pending_questions", return_value=[]):
                                with patch.object(self.mod, "get_health_issues", return_value=[]):
                                    self.mod.main()

    def test_creates_result_file(self):
        self._run_main()
        files = list(self.mod.RESULTS_DIR.glob("proactive-morning-*.txt"))
        self.assertEqual(len(files), 1)
        self.assertGreater(len(files[0].read_text()), 0)

    def test_creates_sentinel(self):
        self._run_main()
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertTrue((self.mod.STATE_DIR / f"morning-briefing-{today}.sentinel").exists())

    def test_skips_if_sentinel_exists(self):
        today = datetime.now().strftime("%Y-%m-%d")
        sentinel = self.mod.STATE_DIR / f"morning-briefing-{today}.sentinel"
        sentinel.write_text("already done")
        with patch.object(self.mod, "get_weather") as mock_w:
            self.mod.main()
            mock_w.assert_not_called()
        # Result file NOT created (skipped)
        self.assertEqual(len(list(self.mod.RESULTS_DIR.glob("proactive-morning-*.txt"))), 0)

    def test_result_contains_greeting(self):
        self._run_main()
        files = list(self.mod.RESULTS_DIR.glob("proactive-morning-*.txt"))
        content = files[0].read_text().lower()
        self.assertTrue(
            "good morning" in content or
            "good afternoon" in content or
            "good evening" in content
        )


if __name__ == "__main__":
    unittest.main()
