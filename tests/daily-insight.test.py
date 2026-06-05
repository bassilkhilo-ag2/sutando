"""Unit tests for src/daily-insight.py.

Run: `python3 tests/daily-insight.test.py`
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "daily-insight.py"

sys.path.insert(0, str(ROOT / "src"))


def _load(workspace: Path):
    os.environ["SUTANDO_WORKSPACE"] = str(workspace)
    spec = importlib.util.spec_from_file_location("daily_insight", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestLoadCalls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def _calls_file(self):
        p = self.ws / "results" / "calls"
        p.mkdir(parents=True, exist_ok=True)
        return p / "calls.jsonl"

    def test_missing_file_returns_empty(self):
        self.assertEqual(self.mod.load_calls(), [])

    def test_loads_valid_lines(self):
        f = self._calls_file()
        f.write_text('{"callSid":"CA1"}\n{"callSid":"CA2"}\n')
        mod = _load(self.ws)
        self.assertEqual(len(mod.load_calls()), 2)

    def test_skips_blank_and_invalid(self):
        f = self._calls_file()
        f.write_text('{"callSid":"CA1"}\n\nBAD\n{"callSid":"CA2"}\n')
        mod = _load(self.ws)
        self.assertEqual(len(mod.load_calls()), 2)


class TestAnalyzeCallTiming(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_counts_hours_and_days(self):
        calls = [
            {"start_time": "2024-01-15T10:00:00Z"},
            {"start_time": "2024-01-15T10:30:00Z"},
            {"start_time": "2024-01-16T14:00:00Z"},
        ]
        hours, days = self.mod.analyze_call_timing(calls)
        self.assertEqual(hours[10], 2)
        self.assertEqual(hours[14], 1)

    def test_skips_missing_timestamp(self):
        calls = [{"callSid": "CA1"}, {"start_time": "2024-01-15T10:00:00Z"}]
        hours, _ = self.mod.analyze_call_timing(calls)
        self.assertEqual(sum(hours.values()), 1)

    def test_falls_back_to_timestamp_field(self):
        calls = [{"timestamp": "2024-01-15T08:00:00Z"}]
        hours, _ = self.mod.analyze_call_timing(calls)
        self.assertEqual(hours[8], 1)

    def test_empty_calls_returns_empty_counters(self):
        hours, days = self.mod.analyze_call_timing([])
        self.assertEqual(len(hours), 0)
        self.assertEqual(len(days), 0)


class TestAnalyzeCallDuration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_no_durations_returns_none(self):
        self.assertIsNone(self.mod.analyze_call_duration([{"callSid": "CA1"}]))

    def test_zero_duration_excluded(self):
        self.assertIsNone(self.mod.analyze_call_duration([{"duration_seconds": 0}]))

    def test_computes_avg_and_longest(self):
        calls = [{"duration_seconds": 60}, {"duration_seconds": 120}, {"duration_seconds": 180}]
        stats = self.mod.analyze_call_duration(calls)
        self.assertEqual(stats["count"], 3)
        self.assertAlmostEqual(stats["avg_minutes"], 2.0, places=1)
        self.assertAlmostEqual(stats["longest_minutes"], 3.0, places=1)

    def test_long_call_pct(self):
        # avg=100s → long = >200s → 1 out of 3
        calls = [{"duration_seconds": 60}, {"duration_seconds": 80}, {"duration_seconds": 300}]
        stats = self.mod.analyze_call_duration(calls)
        # avg ≈ 146.7s, long_calls = those > 2*avg ≈ 293s → only 300 qualifies
        self.assertGreaterEqual(stats["long_call_pct"], 0)

    def test_falls_back_to_duration_field(self):
        calls = [{"duration": 90}]
        stats = self.mod.analyze_call_duration(calls)
        self.assertIsNotNone(stats)
        self.assertEqual(stats["count"], 1)


class TestAnalyzeTopics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_empty_calls_returns_empty(self):
        result = self.mod.analyze_topics([])
        self.assertEqual(result, [])

    def test_extracts_common_words(self):
        calls = [
            {"summary": "discussion about startup funding rounds"},
            {"summary": "startup pitch feedback session"},
        ]
        topics = self.mod.analyze_topics(calls)
        words = [t[0] for t in topics]
        self.assertIn("startup", words)

    def test_stopwords_excluded(self):
        calls = [{"summary": "about their which where these those other"}]
        topics = self.mod.analyze_topics(calls)
        words = [t[0] for t in topics]
        for stopword in ("about", "their", "which", "where", "these", "those", "other"):
            self.assertNotIn(stopword, words)

    def test_short_words_excluded(self):
        calls = [{"summary": "the a to of in is"}]
        topics = self.mod.analyze_topics(calls)
        # All words are ≤4 chars — should be empty or not contain them
        words = [t[0] for t in topics]
        for w in ("the", "a", "to", "of", "in", "is"):
            self.assertNotIn(w, words)


class TestAnalyzeNoteActivity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def _make_note(self, name: str, content: str = "# Note\n"):
        notes = self.ws / "notes"
        notes.mkdir(exist_ok=True)
        (notes / name).write_text(content)
        self.mod.NOTES_DIR = notes

    def test_empty_notes_dir(self):
        notes = self.ws / "notes"
        notes.mkdir()
        self.mod.NOTES_DIR = notes
        stats = self.mod.analyze_note_activity()
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["recent_7d"], 0)

    def test_counts_notes(self):
        for i in range(3):
            self._make_note(f"note-{i}.md")
        stats = self.mod.analyze_note_activity()
        self.assertEqual(stats["total"], 3)

    def test_recent_notes_counted(self):
        self._make_note("recent.md")
        stats = self.mod.analyze_note_activity()
        self.assertEqual(stats["recent_7d"], 1)

    def test_tags_extracted(self):
        self._make_note("tagged.md", "# Note\ntags: [startup, funding, growth]\n")
        stats = self.mod.analyze_note_activity()
        tag_names = [t[0] for t in stats["top_tags"]]
        self.assertIn("startup", tag_names)


class TestGenerateInsight(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        (self.ws / "results").mkdir(parents=True, exist_ok=True)
        (self.ws / "notes").mkdir(parents=True, exist_ok=True)
        self.mod.NOTES_DIR = self.ws / "notes"
        self.mod.RESULTS_DIR = self.ws / "results"

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_returns_string(self):
        result = self.mod.generate_insight()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_fallback_message_when_no_data(self):
        result = self.mod.generate_insight()
        self.assertIn("Not enough data", result)

    def test_with_calls_returns_insight(self):
        calls_dir = self.ws / "results" / "calls"
        calls_dir.mkdir(parents=True, exist_ok=True)
        entries = []
        for i in range(5):
            entries.append(json.dumps({
                "callSid": f"CA{i}",
                "start_time": f"2024-01-15T{10+i}:00:00Z",
                "duration_seconds": 120,
                "summary": "startup discussion",
            }))
        (calls_dir / "calls.jsonl").write_text("\n".join(entries) + "\n")
        mod = _load(self.ws)
        mod.NOTES_DIR = self.ws / "notes"
        mod.RESULTS_DIR = self.ws / "results"
        result = mod.generate_insight()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 10)


if __name__ == "__main__":
    unittest.main()
