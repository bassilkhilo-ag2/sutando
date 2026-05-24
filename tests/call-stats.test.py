#!/usr/bin/env python3
"""
Tests for src/call-stats.py

Coverage:
  load_calls        — no file, empty file, valid JSONL, invalid JSON line skipped,
                      mixed valid/invalid lines
  parse_ts          — Z suffix, +00:00 suffix, empty string, non-date string, None
  mask_phone        — 11-digit US number, "unknown", None, short (<10 digits),
                      10-digit (non-11 branch)
  filter_by_window  — days=None (all), recent call included, old call excluded,
                      call with no timestamp excluded
  compute_stats     — empty list yields zeros, single call aggregation, meetings/
                      owner_calls counted, no-duration calls excluded from avg,
                      peak_hour and busiest_day populated
  format_text       — no duration → fallback message, with duration → avg/longest/
                      shortest, unknown purposes skipped, unknown callers skipped
  main              — no calls → stderr message, --json output, --all flag,
                      --days N flag, default 7-day window

Run: python3 tests/call-stats.test.py
Exit code: 0 on pass, 1 on fail.
"""

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
TMPDIR = Path(tempfile.mkdtemp())

_fake_wd = type(sys)("workspace_default")
_fake_wd.resolve_workspace = lambda: TMPDIR
sys.modules["workspace_default"] = _fake_wd

_spec = importlib.util.spec_from_file_location(
    "call_stats",
    REPO / "src" / "call-stats.py",
)
cs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cs)

CALLS_DIR = TMPDIR / "results" / "calls"
CALLS_DIR.mkdir(parents=True, exist_ok=True)


def _write_calls(*records):
    cs.CALLS_FILE.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n"
    )


class TestLoadCalls(unittest.TestCase):
    def setUp(self):
        cs.CALLS_FILE = CALLS_DIR / "calls.jsonl"
        if cs.CALLS_FILE.exists():
            cs.CALLS_FILE.unlink()

    def test_no_file_returns_empty(self):
        self.assertEqual(cs.load_calls(), [])

    def test_empty_file_returns_empty(self):
        cs.CALLS_FILE.write_text("")
        self.assertEqual(cs.load_calls(), [])

    def test_valid_jsonl_parsed(self):
        _write_calls({"callSid": "CA1"}, {"callSid": "CA2"})
        calls = cs.load_calls()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["callSid"], "CA1")

    def test_invalid_json_line_skipped(self):
        cs.CALLS_FILE.write_text('{"callSid":"CA1"}\nnot json\n{"callSid":"CA2"}\n')
        calls = cs.load_calls()
        self.assertEqual(len(calls), 2)

    def test_blank_lines_skipped(self):
        cs.CALLS_FILE.write_text('\n{"callSid":"CA1"}\n\n')
        self.assertEqual(len(cs.load_calls()), 1)


class TestParseTs(unittest.TestCase):
    def test_z_suffix_parsed(self):
        result = cs.parse_ts("2026-05-01T12:00:00Z")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)

    def test_offset_suffix_parsed(self):
        result = cs.parse_ts("2026-05-01T12:00:00+00:00")
        self.assertIsNotNone(result)

    def test_empty_string_returns_none(self):
        self.assertIsNone(cs.parse_ts(""))

    def test_none_returns_none(self):
        self.assertIsNone(cs.parse_ts(None))

    def test_non_date_string_returns_none(self):
        self.assertIsNone(cs.parse_ts("not-a-date"))

    def test_result_is_datetime(self):
        result = cs.parse_ts("2026-01-15T09:30:00Z")
        self.assertIsInstance(result, datetime)


class TestMaskPhone(unittest.TestCase):
    def test_11_digit_us_number(self):
        result = cs.mask_phone("+14256716122")
        self.assertEqual(result, "+1-425-XXX-XXXX")

    def test_unknown_passthrough(self):
        self.assertEqual(cs.mask_phone("unknown"), "unknown")

    def test_none_returns_unknown(self):
        self.assertEqual(cs.mask_phone(None), "unknown")

    def test_short_number_returned_as_is(self):
        result = cs.mask_phone("12345")
        self.assertEqual(result, "12345")

    def test_country_and_area_code_preserved(self):
        result = cs.mask_phone("+12125551234")
        self.assertIn("212", result)
        self.assertIn("XXX-XXXX", result)

    def test_digits_only_input(self):
        result = cs.mask_phone("14256716122")
        self.assertIn("XXX-XXXX", result)


class TestFilterByWindow(unittest.TestCase):
    def _call(self, days_ago):
        ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        return {"start_time": ts}

    def test_none_window_returns_all(self):
        calls = [self._call(1), self._call(30), self._call(365)]
        self.assertEqual(len(cs.filter_by_window(calls, None)), 3)

    def test_recent_call_included(self):
        calls = [self._call(1)]
        self.assertEqual(len(cs.filter_by_window(calls, 7)), 1)

    def test_old_call_excluded(self):
        calls = [self._call(10)]
        self.assertEqual(len(cs.filter_by_window(calls, 7)), 0)

    def test_call_without_timestamp_excluded(self):
        calls = [{"callSid": "CA1"}]  # no start_time or timestamp
        self.assertEqual(len(cs.filter_by_window(calls, 7)), 0)

    def test_timestamp_field_fallback(self):
        ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        calls = [{"timestamp": ts}]
        self.assertEqual(len(cs.filter_by_window(calls, 7)), 1)

    def test_boundary_exact(self):
        # Call exactly at window start should be included (>=).
        ts = (datetime.now(timezone.utc) - timedelta(days=7, seconds=60)).isoformat()
        calls = [{"start_time": ts}]
        self.assertEqual(len(cs.filter_by_window(calls, 7)), 0)


class TestComputeStats(unittest.TestCase):
    def _call(self, **kwargs):
        return {"start_time": "2026-05-01T14:00:00Z", **kwargs}

    def test_empty_returns_zero_total(self):
        stats = cs.compute_stats([])
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["avg_duration_seconds"], 0)
        self.assertIsNone(stats["peak_hour"])

    def test_total_count_correct(self):
        calls = [self._call(), self._call(), self._call()]
        self.assertEqual(cs.compute_stats(calls)["total"], 3)

    def test_duration_stats_computed(self):
        calls = [
            self._call(duration_seconds=60),
            self._call(duration_seconds=120),
        ]
        stats = cs.compute_stats(calls)
        self.assertEqual(stats["avg_duration_seconds"], 90.0)
        self.assertEqual(stats["longest_seconds"], 120)
        self.assertEqual(stats["shortest_seconds"], 60)

    def test_zero_duration_excluded_from_avg(self):
        calls = [self._call(duration_seconds=0), self._call(duration_seconds=100)]
        stats = cs.compute_stats(calls)
        self.assertEqual(stats["with_duration"], 1)
        self.assertEqual(stats["avg_duration_seconds"], 100.0)

    def test_meetings_counted(self):
        calls = [self._call(is_meeting=True), self._call(is_meeting=False)]
        self.assertEqual(cs.compute_stats(calls)["meetings"], 1)

    def test_owner_calls_counted(self):
        calls = [self._call(is_owner=True), self._call()]
        self.assertEqual(cs.compute_stats(calls)["owner_calls"], 1)

    def test_peak_hour_populated(self):
        calls = [self._call(start_time="2026-05-01T14:00:00Z")] * 3
        stats = cs.compute_stats(calls)
        self.assertIsNotNone(stats["peak_hour"])
        self.assertEqual(stats["peak_hour"][0], 14)

    def test_top_purposes_aggregated(self):
        calls = [
            self._call(purpose="sales"),
            self._call(purpose="sales"),
            self._call(purpose="support"),
        ]
        stats = cs.compute_stats(calls)
        self.assertEqual(stats["top_purposes"][0], ("sales", 2))

    def test_top_callers_masked(self):
        calls = [self._call(caller="+14256716122")] * 2
        stats = cs.compute_stats(calls)
        num, count = stats["top_callers"][0]
        self.assertIn("XXX-XXXX", num)
        self.assertEqual(count, 2)


class TestFormatText(unittest.TestCase):
    def _minimal_stats(self, **overrides):
        base = {
            "total": 5,
            "with_duration": 0,
            "avg_duration_seconds": 0,
            "longest_seconds": 0,
            "shortest_seconds": 0,
            "total_minutes": 0,
            "meetings": 0,
            "owner_calls": 0,
            "peak_hour": None,
            "quiet_hours": [],
            "busiest_day": None,
            "top_purposes": [],
            "top_callers": [],
        }
        base.update(overrides)
        return base

    def test_no_duration_shows_fallback_message(self):
        text = cs.format_text(self._minimal_stats(), "last 7 days")
        self.assertIn("no duration data yet", text)

    def test_with_duration_shows_avg(self):
        stats = self._minimal_stats(
            with_duration=3,
            avg_duration_seconds=90.0,
            longest_seconds=120,
            shortest_seconds=60,
            total_minutes=4.5,
        )
        text = cs.format_text(stats, "last 7 days")
        self.assertIn("90.0s", text)
        self.assertIn("120s", text)

    def test_unknown_purposes_skipped(self):
        stats = self._minimal_stats(top_purposes=[("unknown", 5)])
        text = cs.format_text(stats, "last 7 days")
        self.assertNotIn("Purposes:", text)

    def test_known_purposes_shown(self):
        stats = self._minimal_stats(top_purposes=[("sales", 3)])
        text = cs.format_text(stats, "last 7 days")
        self.assertIn("sales: 3", text)

    def test_unknown_callers_skipped(self):
        stats = self._minimal_stats(top_callers=[("unknown", 5)])
        text = cs.format_text(stats, "last 7 days")
        self.assertNotIn("Top callers:", text)

    def test_meetings_shown_when_present(self):
        stats = self._minimal_stats(meetings=2)
        text = cs.format_text(stats, "all time")
        self.assertIn("Meetings: 2", text)

    def test_window_label_in_output(self):
        text = cs.format_text(self._minimal_stats(), "last 30 days")
        self.assertIn("last 30 days", text)


class TestMain(unittest.TestCase):
    def setUp(self):
        cs.CALLS_FILE = CALLS_DIR / "calls.jsonl"
        if cs.CALLS_FILE.exists():
            cs.CALLS_FILE.unlink()

    def test_no_file_prints_to_stderr(self):
        with patch("sys.argv", ["call-stats.py"]), \
             patch("sys.stderr", new_callable=StringIO) as mock_err:
            cs.main()
        self.assertIn("No calls", mock_err.getvalue())

    def test_json_flag_outputs_json(self):
        _write_calls({"start_time": "2026-05-01T10:00:00Z", "duration_seconds": 60})
        with patch("sys.argv", ["call-stats.py", "--all", "--json"]), \
             patch("sys.stdout", new_callable=StringIO) as mock_out:
            cs.main()
        data = json.loads(mock_out.getvalue())
        self.assertIn("total", data)
        self.assertEqual(data["total"], 1)

    def test_all_flag_skips_window_filter(self):
        old_ts = "2020-01-01T00:00:00Z"
        _write_calls({"start_time": old_ts, "duration_seconds": 30})
        with patch("sys.argv", ["call-stats.py", "--all", "--json"]), \
             patch("sys.stdout", new_callable=StringIO) as mock_out:
            cs.main()
        data = json.loads(mock_out.getvalue())
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["window"], "all time")

    def test_default_7_day_window(self):
        old_ts = "2020-01-01T00:00:00Z"
        _write_calls({"start_time": old_ts})
        with patch("sys.argv", ["call-stats.py", "--json"]), \
             patch("sys.stdout", new_callable=StringIO), \
             patch("sys.stderr", new_callable=StringIO) as mock_err:
            cs.main()
        self.assertIn("No calls", mock_err.getvalue())

    def test_days_flag_respected(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        _write_calls({"start_time": recent, "duration_seconds": 45})
        with patch("sys.argv", ["call-stats.py", "--days", "3", "--json"]), \
             patch("sys.stdout", new_callable=StringIO) as mock_out:
            cs.main()
        data = json.loads(mock_out.getvalue())
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["window"], "last 3 days")


if __name__ == "__main__":
    unittest.main()
