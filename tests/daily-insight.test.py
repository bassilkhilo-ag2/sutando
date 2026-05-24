#!/usr/bin/env python3
"""
Tests for src/daily-insight.py

Coverage:
  load_calls            — no file, empty file, valid JSONL, invalid JSON skipped,
                          blank lines skipped
  analyze_call_timing   — empty list yields empty counters, Z suffix parsed,
                          +offset suffix parsed, invalid ts skipped, hour/day
                          populated correctly
  analyze_call_duration — no durations → None, zero/negative excluded,
                          avg correct, long_call_pct threshold (>avg*2),
                          duration field alias ("duration" key)
  analyze_topics        — empty calls → empty list, stopwords excluded,
                          short words (<5 chars) excluded, counts aggregated,
                          punctuation stripped from words
  analyze_task_patterns — no task files → empty Counter, discord/telegram/
                          voice/other classification, last-50 cap
  analyze_note_activity — no notes dir → zeros, recent_7d count, tag parsing,
                          no tags → empty top_tags, total count
  generate_insight      — no data → fallback message, picks longest insight,
                          hour/day/duration/notes/task branches each produce output
  main                  — sentinel blocks rerun, writes insight to both
                          results/ and state/, output matches generated insight

Run: python3 tests/daily-insight.test.py
Exit code: 0 on pass, 1 on fail.
"""

import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

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
    "daily_insight",
    REPO / "src" / "daily-insight.py",
)
di = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(di)

CALLS_DIR = TMPDIR / "results" / "calls"
RESULTS_DIR = TMPDIR / "results"
STATE_DIR = TMPDIR / "state"
NOTES_DIR = TMPDIR / "notes"

for d in (CALLS_DIR, RESULTS_DIR, STATE_DIR, NOTES_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _write_calls(*records):
    di.CALLS_FILE.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n"
    )


def _clear_calls():
    if di.CALLS_FILE.exists():
        di.CALLS_FILE.unlink()


# ── load_calls ────────────────────────────────────────────────────────────────

class TestLoadCalls(unittest.TestCase):
    def setUp(self):
        di.CALLS_FILE = CALLS_DIR / "calls.jsonl"
        _clear_calls()

    def test_no_file_returns_empty(self):
        self.assertEqual(di.load_calls(), [])

    def test_empty_file_returns_empty(self):
        di.CALLS_FILE.write_text("")
        self.assertEqual(di.load_calls(), [])

    def test_valid_jsonl_parsed(self):
        _write_calls({"callSid": "CA1"}, {"callSid": "CA2"})
        calls = di.load_calls()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["callSid"], "CA1")

    def test_invalid_json_line_skipped(self):
        di.CALLS_FILE.write_text('{"callSid":"CA1"}\nnot json\n{"callSid":"CA2"}\n')
        self.assertEqual(len(di.load_calls()), 2)

    def test_blank_lines_skipped(self):
        di.CALLS_FILE.write_text('\n{"callSid":"CA1"}\n\n')
        self.assertEqual(len(di.load_calls()), 1)


# ── analyze_call_timing ───────────────────────────────────────────────────────

class TestAnalyzeCallTiming(unittest.TestCase):
    def test_empty_list_yields_empty_counters(self):
        hour_counts, day_counts = di.analyze_call_timing([])
        self.assertEqual(len(hour_counts), 0)
        self.assertEqual(len(day_counts), 0)

    def test_z_suffix_parsed(self):
        calls = [{"start_time": "2026-05-01T14:00:00Z"}]
        hour_counts, _ = di.analyze_call_timing(calls)
        self.assertEqual(hour_counts[14], 1)

    def test_offset_suffix_parsed(self):
        calls = [{"start_time": "2026-05-01T09:00:00+00:00"}]
        hour_counts, _ = di.analyze_call_timing(calls)
        self.assertEqual(hour_counts[9], 1)

    def test_invalid_timestamp_skipped(self):
        calls = [{"start_time": "not-a-date"}, {"start_time": "2026-05-01T10:00:00Z"}]
        hour_counts, _ = di.analyze_call_timing(calls)
        self.assertEqual(sum(hour_counts.values()), 1)

    def test_no_timestamp_skipped(self):
        calls = [{"callSid": "CA1"}]
        hour_counts, day_counts = di.analyze_call_timing(calls)
        self.assertEqual(len(hour_counts), 0)

    def test_day_of_week_populated(self):
        calls = [{"start_time": "2026-05-01T10:00:00Z"}]  # Friday
        _, day_counts = di.analyze_call_timing(calls)
        self.assertIn("Friday", day_counts)

    def test_timestamp_field_fallback(self):
        calls = [{"timestamp": "2026-05-01T16:00:00Z"}]
        hour_counts, _ = di.analyze_call_timing(calls)
        self.assertEqual(hour_counts[16], 1)

    def test_multiple_calls_same_hour_accumulated(self):
        calls = [
            {"start_time": "2026-05-01T14:00:00Z"},
            {"start_time": "2026-05-02T14:30:00Z"},
            {"start_time": "2026-05-03T09:00:00Z"},
        ]
        hour_counts, _ = di.analyze_call_timing(calls)
        self.assertEqual(hour_counts[14], 2)
        self.assertEqual(hour_counts[9], 1)


# ── analyze_call_duration ─────────────────────────────────────────────────────

class TestAnalyzeCallDuration(unittest.TestCase):
    def test_no_durations_returns_none(self):
        calls = [{"callSid": "CA1"}, {"callSid": "CA2"}]
        self.assertIsNone(di.analyze_call_duration(calls))

    def test_zero_duration_excluded(self):
        calls = [{"duration_seconds": 0}, {"duration_seconds": 120}]
        stats = di.analyze_call_duration(calls)
        self.assertEqual(stats["count"], 1)

    def test_negative_duration_excluded(self):
        calls = [{"duration_seconds": -10}, {"duration_seconds": 60}]
        stats = di.analyze_call_duration(calls)
        self.assertEqual(stats["count"], 1)

    def test_average_correct(self):
        calls = [{"duration_seconds": 60}, {"duration_seconds": 120}]
        stats = di.analyze_call_duration(calls)
        self.assertAlmostEqual(stats["avg_minutes"], 1.5)

    def test_longest_computed(self):
        calls = [
            {"duration_seconds": 60},
            {"duration_seconds": 300},
            {"duration_seconds": 120},
        ]
        stats = di.analyze_call_duration(calls)
        self.assertAlmostEqual(stats["longest_minutes"], 5.0)

    def test_long_call_pct_above_threshold(self):
        # 1 call at avg*2+ out of 2 total = 50%
        calls = [{"duration_seconds": 60}, {"duration_seconds": 300}]
        stats = di.analyze_call_duration(calls)
        # avg = 180s, threshold = 360s. 300 < 360 → no long calls
        self.assertEqual(stats["long_call_pct"], 0.0)

    def test_long_call_pct_with_outlier(self):
        # avg=100, threshold=200; 500 qualifies
        calls = [{"duration_seconds": 100}, {"duration_seconds": 500}]
        stats = di.analyze_call_duration(calls)
        # avg = 300, threshold = 600. Neither qualifies.
        # Let's use values where one clearly qualifies:
        # durations [60, 60, 600] → avg=240, threshold=480 → 600 qualifies (1/3 = 33%)
        calls2 = [
            {"duration_seconds": 60},
            {"duration_seconds": 60},
            {"duration_seconds": 600},
        ]
        stats2 = di.analyze_call_duration(calls2)
        self.assertGreater(stats2["long_call_pct"], 0)

    def test_duration_alias_key(self):
        calls = [{"duration": 90}]
        stats = di.analyze_call_duration(calls)
        self.assertIsNotNone(stats)
        self.assertEqual(stats["count"], 1)

    def test_empty_list_returns_none(self):
        self.assertIsNone(di.analyze_call_duration([]))


# ── analyze_topics ────────────────────────────────────────────────────────────

class TestAnalyzeTopics(unittest.TestCase):
    def test_empty_calls_returns_empty(self):
        self.assertEqual(di.analyze_topics([]), [])

    def test_short_words_excluded(self):
        # "dog" is 3 chars — excluded (<= 4 chars excluded means len > 4)
        calls = [{"summary": "dog ran fast from home"}]
        topics = dict(di.analyze_topics(calls))
        self.assertNotIn("dog", topics)
        self.assertNotIn("ran", topics)
        self.assertNotIn("fast", topics)
        self.assertNotIn("from", topics)
        self.assertNotIn("home", topics)

    def test_five_char_word_included(self):
        calls = [{"summary": "sales calls today"}]
        topics = dict(di.analyze_topics(calls))
        self.assertIn("sales", topics)
        self.assertIn("calls", topics)

    def test_stopwords_excluded(self):
        stopwords = ["about", "their", "there", "would", "could", "should",
                     "which", "where", "these", "those", "other", "after",
                     "before", "between", "under", "above", "through"]
        for word in stopwords:
            calls = [{"summary": f"this is {word} us"}]
            topics = dict(di.analyze_topics(calls))
            self.assertNotIn(word, topics, f"stopword '{word}' should be excluded")

    def test_punctuation_stripped(self):
        calls = [{"summary": "sales, sales. sales!"}]
        topics = dict(di.analyze_topics(calls))
        self.assertIn("sales", topics)
        self.assertEqual(topics["sales"], 3)

    def test_counts_aggregated_across_calls(self):
        calls = [
            {"summary": "sales update"},
            {"summary": "sales review"},
        ]
        topics = dict(di.analyze_topics(calls))
        self.assertEqual(topics["sales"], 2)

    def test_topic_field_fallback(self):
        calls = [{"topic": "budget planning"}]
        topics = dict(di.analyze_topics(calls))
        self.assertIn("budget", topics)

    def test_top_10_returned(self):
        # 15 distinct 5-char words → only top 10 returned
        calls = [{"summary": " ".join(f"word{i}" for i in range(15))}]
        topics = di.analyze_topics(calls)
        self.assertLessEqual(len(topics), 10)

    def test_lowercased(self):
        calls = [{"summary": "SALES calls SALES"}]
        topics = dict(di.analyze_topics(calls))
        self.assertIn("sales", topics)
        self.assertEqual(topics["sales"], 2)


# ── analyze_task_patterns ─────────────────────────────────────────────────────

class TestAnalyzeTaskPatterns(unittest.TestCase):
    def setUp(self):
        di.RESULTS_DIR = RESULTS_DIR
        # Clear task files
        for f in RESULTS_DIR.glob("task-*.txt"):
            f.unlink()

    def tearDown(self):
        for f in RESULTS_DIR.glob("task-*.txt"):
            f.unlink()

    def test_no_task_files_returns_empty(self):
        sources = di.analyze_task_patterns()
        self.assertEqual(sum(sources.values()), 0)

    def test_discord_classified(self):
        (RESULTS_DIR / "task-001.txt").write_text("received via discord channel")
        sources = di.analyze_task_patterns()
        self.assertEqual(sources["Discord"], 1)

    def test_telegram_classified(self):
        (RESULTS_DIR / "task-002.txt").write_text("message from telegram bot")
        sources = di.analyze_task_patterns()
        self.assertEqual(sources["Telegram"], 1)

    def test_voice_classified(self):
        (RESULTS_DIR / "task-003.txt").write_text("voice command received")
        sources = di.analyze_task_patterns()
        self.assertEqual(sources["Voice"], 1)

    def test_other_classified(self):
        (RESULTS_DIR / "task-004.txt").write_text("unknown source task here")
        sources = di.analyze_task_patterns()
        self.assertEqual(sources["Other"], 1)

    def test_mixed_sources(self):
        (RESULTS_DIR / "task-010.txt").write_text("discord message")
        (RESULTS_DIR / "task-011.txt").write_text("telegram update")
        (RESULTS_DIR / "task-012.txt").write_text("voice command")
        (RESULTS_DIR / "task-013.txt").write_text("other source")
        sources = di.analyze_task_patterns()
        self.assertEqual(sources["Discord"], 1)
        self.assertEqual(sources["Telegram"], 1)
        self.assertEqual(sources["Voice"], 1)
        self.assertEqual(sources["Other"], 1)

    def test_last_50_cap(self):
        # Create 60 files — should only count 50
        for i in range(60):
            (RESULTS_DIR / f"task-{i:04d}.txt").write_text("other content")
        sources = di.analyze_task_patterns()
        self.assertEqual(sum(sources.values()), 50)


# ── analyze_note_activity ─────────────────────────────────────────────────────

class TestAnalyzeNoteActivity(unittest.TestCase):
    def setUp(self):
        di.NOTES_DIR = NOTES_DIR
        for f in NOTES_DIR.glob("*.md"):
            f.unlink()

    def tearDown(self):
        for f in NOTES_DIR.glob("*.md"):
            f.unlink()

    def test_no_notes_returns_zeros(self):
        stats = di.analyze_note_activity()
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["recent_7d"], 0)
        self.assertEqual(stats["top_tags"], [])

    def test_total_count(self):
        (NOTES_DIR / "a.md").write_text("# Note A")
        (NOTES_DIR / "b.md").write_text("# Note B")
        stats = di.analyze_note_activity()
        self.assertEqual(stats["total"], 2)

    def test_recent_7d_count(self):
        # Fresh note — within 7 days
        (NOTES_DIR / "fresh.md").write_text("# Recent")
        # Old note — 8 days ago
        old = NOTES_DIR / "old.md"
        old.write_text("# Old")
        old_mtime = time.time() - 8 * 86400
        os.utime(old, (old_mtime, old_mtime))

        stats = di.analyze_note_activity()
        self.assertEqual(stats["recent_7d"], 1)
        self.assertEqual(stats["total"], 2)

    def test_tag_parsing(self):
        (NOTES_DIR / "tagged.md").write_text(
            "---\ntags: [ideas, projects]\n---\n# Title\n"
        )
        stats = di.analyze_note_activity()
        top_tags = dict(stats["top_tags"])
        self.assertIn("ideas", top_tags)
        self.assertIn("projects", top_tags)

    def test_no_tags_line_yields_empty_tags(self):
        (NOTES_DIR / "notag.md").write_text("# No tags here\n\nJust content.\n")
        stats = di.analyze_note_activity()
        self.assertEqual(stats["top_tags"], [])

    def test_no_notes_dir_returns_zeros(self):
        import tempfile
        fake_ws = Path(tempfile.mkdtemp())
        orig = di.NOTES_DIR
        di.NOTES_DIR = fake_ws / "notes"  # does not exist
        try:
            stats = di.analyze_note_activity()
            self.assertEqual(stats["total"], 0)
        finally:
            di.NOTES_DIR = orig


# ── generate_insight ──────────────────────────────────────────────────────────

class TestGenerateInsight(unittest.TestCase):
    def setUp(self):
        di.CALLS_FILE = CALLS_DIR / "calls.jsonl"
        di.RESULTS_DIR = RESULTS_DIR
        di.NOTES_DIR = NOTES_DIR
        _clear_calls()
        for f in RESULTS_DIR.glob("task-*.txt"):
            f.unlink()
        for f in NOTES_DIR.glob("*.md"):
            f.unlink()

    def tearDown(self):
        _clear_calls()
        for f in RESULTS_DIR.glob("task-*.txt"):
            f.unlink()
        for f in NOTES_DIR.glob("*.md"):
            f.unlink()

    def test_no_data_returns_fallback(self):
        insight = di.generate_insight()
        self.assertIn("Not enough data", insight)

    def test_returns_string(self):
        insight = di.generate_insight()
        self.assertIsInstance(insight, str)
        self.assertGreater(len(insight), 0)

    def test_picks_longest_insight(self):
        # With many calls across many hours, the timing branch fires and produces
        # a long insight. The fallback is short. Longest wins.
        calls = []
        for hour in range(9, 22):
            for _ in range(3):
                calls.append({"start_time": f"2026-05-01T{hour:02d}:00:00Z"})
        _write_calls(*calls)
        insight = di.generate_insight()
        self.assertNotIn("Not enough data", insight)

    def test_task_patterns_branch(self):
        (RESULTS_DIR / "task-001.txt").write_text("discord message here")
        (RESULTS_DIR / "task-002.txt").write_text("discord message here")
        insight = di.generate_insight()
        self.assertIsInstance(insight, str)

    def test_notes_active_branch(self):
        # Create 6 fresh notes to trigger the active notes branch
        for i in range(6):
            (NOTES_DIR / f"note{i}.md").write_text(f"---\ntags: [ideas]\n---\n# Note {i}\n")
        insight = di.generate_insight()
        self.assertIsInstance(insight, str)

    def test_notes_dormant_branch(self):
        # >10 total notes, none recent → dormant branch
        for i in range(11):
            p = NOTES_DIR / f"old{i}.md"
            p.write_text(f"# Old {i}\n")
            old_mtime = time.time() - 8 * 86400
            os.utime(p, (old_mtime, old_mtime))
        insight = di.generate_insight()
        self.assertIsInstance(insight, str)


# ── main ──────────────────────────────────────────────────────────────────────

class TestMain(unittest.TestCase):
    def setUp(self):
        di.CALLS_FILE = CALLS_DIR / "calls.jsonl"
        di.RESULTS_DIR = RESULTS_DIR
        di.STATE_DIR = STATE_DIR
        di.NOTES_DIR = NOTES_DIR
        _clear_calls()
        for f in RESULTS_DIR.glob("task-*.txt"):
            f.unlink()
        for f in NOTES_DIR.glob("*.md"):
            f.unlink()
        # Remove sentinel and results file for today
        today = datetime.now().strftime("%Y-%m-%d")
        sentinel = STATE_DIR / f"daily-insight-{today}.sentinel"
        results_file = RESULTS_DIR / f"insight-{today}.txt"
        if sentinel.exists():
            sentinel.unlink()
        if results_file.exists():
            results_file.unlink()

    def tearDown(self):
        today = datetime.now().strftime("%Y-%m-%d")
        sentinel = STATE_DIR / f"daily-insight-{today}.sentinel"
        results_file = RESULTS_DIR / f"insight-{today}.txt"
        if sentinel.exists():
            sentinel.unlink()
        if results_file.exists():
            results_file.unlink()

    def _today_paths(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return (
            RESULTS_DIR / f"insight-{today}.txt",
            STATE_DIR / f"daily-insight-{today}.sentinel",
        )

    def test_writes_results_file(self):
        di.main()
        results_file, _ = self._today_paths()
        self.assertTrue(results_file.exists())

    def test_writes_sentinel(self):
        di.main()
        _, sentinel = self._today_paths()
        self.assertTrue(sentinel.exists())

    def test_sentinel_contains_insight(self):
        di.main()
        results_file, sentinel = self._today_paths()
        self.assertEqual(results_file.read_text(), sentinel.read_text())

    def test_sentinel_blocks_rerun(self):
        di.main()
        _, sentinel = self._today_paths()
        first_content = sentinel.read_text()

        # Overwrite the results file to detect if main regenerates
        results_file, _ = self._today_paths()
        results_file.write_text("MODIFIED")

        di.main()
        # Results file should still be "MODIFIED" since sentinel blocked rerun
        self.assertEqual(results_file.read_text(), "MODIFIED")

    def test_state_dir_created_if_missing(self):
        # Point to a fresh tmpdir with no state/ subdir
        import tempfile
        fresh_tmp = Path(tempfile.mkdtemp())
        orig_state = di.STATE_DIR
        orig_results = di.RESULTS_DIR
        fresh_results = fresh_tmp / "results"
        fresh_results.mkdir()
        di.STATE_DIR = fresh_tmp / "state"
        di.RESULTS_DIR = fresh_results
        try:
            di.main()
            self.assertTrue(di.STATE_DIR.exists())
        finally:
            di.STATE_DIR = orig_state
            di.RESULTS_DIR = orig_results


if __name__ == "__main__":
    unittest.main()
