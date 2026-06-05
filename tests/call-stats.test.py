"""Unit tests for src/call-stats.py.

Run: `python3 tests/call-stats.test.py`
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "call-stats.py"

sys.path.insert(0, str(ROOT / "src"))


def _load(workspace: Path):
    os.environ["SUTANDO_WORKSPACE"] = str(workspace)
    spec = importlib.util.spec_from_file_location("call_stats", SRC)
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

    def _calls_path(self):
        p = self.ws / "results" / "calls"
        p.mkdir(parents=True, exist_ok=True)
        return p / "calls.jsonl"

    def test_missing_file_returns_empty(self):
        self.assertEqual(self.mod.load_calls(), [])

    def test_loads_valid_jsonl(self):
        calls_file = self._calls_path()
        calls_file.write_text('{"callSid":"CA1","duration_seconds":30}\n{"callSid":"CA2","duration_seconds":60}\n')
        # Reload so CALLS_FILE is resolved under the new workspace.
        mod = _load(self.ws)
        result = mod.load_calls()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["callSid"], "CA1")

    def test_skips_blank_lines(self):
        calls_file = self._calls_path()
        calls_file.write_text('{"callSid":"CA1"}\n\n{"callSid":"CA2"}\n')
        mod = _load(self.ws)
        self.assertEqual(len(mod.load_calls()), 2)

    def test_skips_invalid_json(self):
        calls_file = self._calls_path()
        calls_file.write_text('{"callSid":"CA1"}\nNOT JSON\n{"callSid":"CA2"}\n')
        mod = _load(self.ws)
        self.assertEqual(len(mod.load_calls()), 2)


class TestParseTs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_none_returns_none(self):
        self.assertIsNone(self.mod.parse_ts(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(self.mod.parse_ts(""))

    def test_z_suffix_parsed(self):
        dt = self.mod.parse_ts("2024-01-15T10:00:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 10)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_offset_iso_parsed(self):
        dt = self.mod.parse_ts("2024-01-15T10:00:00+04:00")
        self.assertIsNotNone(dt)

    def test_invalid_string_returns_none(self):
        self.assertIsNone(self.mod.parse_ts("not-a-date"))


class TestMaskPhone(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_us_number_masked(self):
        result = self.mod.mask_phone("+14256716122")
        self.assertIn("XXX", result)
        self.assertIn("425", result)
        self.assertNotIn("6716122", result)

    def test_unknown_passthrough(self):
        self.assertEqual(self.mod.mask_phone("unknown"), "unknown")

    def test_none_returns_unknown(self):
        self.assertEqual(self.mod.mask_phone(None), "unknown")

    def test_empty_string_returns_unknown(self):
        self.assertEqual(self.mod.mask_phone(""), "unknown")

    def test_short_number_returned_as_is(self):
        result = self.mod.mask_phone("555")
        self.assertEqual(result, "555")


class TestFilterByWindow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def _ts(self, days_ago: float) -> str:
        dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
        return dt.isoformat()

    def test_none_days_returns_all(self):
        calls = [{"start_time": self._ts(100)}, {"start_time": self._ts(1)}]
        result = self.mod.filter_by_window(calls, None)
        self.assertEqual(len(result), 2)

    def test_recent_call_included(self):
        calls = [{"start_time": self._ts(1)}]
        result = self.mod.filter_by_window(calls, 7)
        self.assertEqual(len(result), 1)

    def test_old_call_excluded(self):
        calls = [{"start_time": self._ts(30)}]
        result = self.mod.filter_by_window(calls, 7)
        self.assertEqual(len(result), 0)

    def test_missing_timestamp_excluded(self):
        calls = [{"callSid": "CA1"}]
        result = self.mod.filter_by_window(calls, 7)
        self.assertEqual(len(result), 0)

    def test_falls_back_to_timestamp_field(self):
        calls = [{"timestamp": self._ts(1)}]
        result = self.mod.filter_by_window(calls, 7)
        self.assertEqual(len(result), 1)


class TestComputeStats(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def _call(self, duration=60, hour=10, purpose="demo", caller="+14251234567",
              is_meeting=False, is_owner=False):
        from datetime import timezone
        dt = datetime.now(timezone.utc).replace(hour=hour, minute=0, second=0, microsecond=0)
        return {
            "duration_seconds": duration,
            "start_time": dt.isoformat(),
            "purpose": purpose,
            "caller": caller,
            "is_meeting": is_meeting,
            "is_owner": is_owner,
        }

    def test_total_count(self):
        calls = [self._call(), self._call(), self._call()]
        stats = self.mod.compute_stats(calls)
        self.assertEqual(stats["total"], 3)

    def test_avg_duration(self):
        calls = [self._call(duration=60), self._call(duration=120)]
        stats = self.mod.compute_stats(calls)
        self.assertEqual(stats["avg_duration_seconds"], 90.0)

    def test_longest_shortest(self):
        calls = [self._call(duration=30), self._call(duration=90), self._call(duration=60)]
        stats = self.mod.compute_stats(calls)
        self.assertEqual(stats["longest_seconds"], 90)
        self.assertEqual(stats["shortest_seconds"], 30)

    def test_total_minutes(self):
        calls = [self._call(duration=120), self._call(duration=60)]
        stats = self.mod.compute_stats(calls)
        self.assertEqual(stats["total_minutes"], 3.0)

    def test_meetings_count(self):
        calls = [self._call(is_meeting=True), self._call(is_meeting=False)]
        stats = self.mod.compute_stats(calls)
        self.assertEqual(stats["meetings"], 1)

    def test_owner_calls_count(self):
        calls = [self._call(is_owner=True), self._call(is_owner=True), self._call()]
        stats = self.mod.compute_stats(calls)
        self.assertEqual(stats["owner_calls"], 2)

    def test_zero_duration_excluded_from_stats(self):
        calls = [self._call(duration=0), self._call(duration=60)]
        stats = self.mod.compute_stats(calls)
        self.assertEqual(stats["with_duration"], 1)
        self.assertEqual(stats["avg_duration_seconds"], 60.0)

    def test_empty_calls(self):
        stats = self.mod.compute_stats([])
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["avg_duration_seconds"], 0)
        self.assertIsNone(stats["peak_hour"])

    def test_top_purposes(self):
        calls = [self._call(purpose="sales")] * 3 + [self._call(purpose="demo")] * 2
        stats = self.mod.compute_stats(calls)
        self.assertEqual(stats["top_purposes"][0][0], "sales")
        self.assertEqual(stats["top_purposes"][0][1], 3)

    def test_top_callers_masked(self):
        calls = [self._call(caller="+14251234567")] * 2
        stats = self.mod.compute_stats(calls)
        top_num, _ = stats["top_callers"][0]
        self.assertIn("XXX", top_num)
        self.assertNotIn("1234567", top_num)


if __name__ == "__main__":
    unittest.main()
