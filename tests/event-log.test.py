"""Unit tests for src/event_log.py.

Run: `python3 tests/event-log.test.py`
"""
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "event_log.py"

sys.path.insert(0, str(ROOT / "src"))


def _load(workspace: Path):
    """Load event_log with SUTANDO_WORKSPACE overridden."""
    os.environ["SUTANDO_WORKSPACE"] = str(workspace)
    spec = importlib.util.spec_from_file_location("event_log", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestGetLogPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_default_returns_today(self):
        path = self.mod.get_log_path()
        today = time.strftime("%Y-%m-%d", time.localtime())
        self.assertEqual(path.name, f"events-{today}.jsonl")
        self.assertEqual(path.parent, self.ws / "logs")

    def test_explicit_timestamp(self):
        # 2024-01-15 00:00:00 UTC → local date depends on TZ, but the function
        # uses localtime, so we derive the expected date the same way.
        ts = 1705276800.0  # 2024-01-15 00:00:00 UTC
        expected = time.strftime("%Y-%m-%d", time.localtime(ts))
        path = self.mod.get_log_path(when=ts)
        self.assertEqual(path.name, f"events-{expected}.jsonl")

    def test_different_timestamps_different_files(self):
        # Two timestamps 25 hours apart should produce different file names.
        ts1 = 1705276800.0
        ts2 = ts1 + 25 * 3600
        p1 = self.mod.get_log_path(when=ts1)
        p2 = self.mod.get_log_path(when=ts2)
        self.assertNotEqual(p1.name, p2.name)

    def test_path_under_logs_dir(self):
        path = self.mod.get_log_path()
        self.assertEqual(path.parent, self.mod.LOGS_DIR)


class TestLogEvent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def _read_events(self):
        path = self.mod.get_log_path()
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_writes_jsonl_line(self):
        self.mod.log_event("test.basic")
        events = self._read_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["kind"], "test.basic")

    def test_event_has_required_fields(self):
        self.mod.log_event("test.fields", foo="bar")
        events = self._read_events()
        ev = events[0]
        self.assertIn("ts", ev)
        self.assertIn("node", ev)
        self.assertIn("kind", ev)
        self.assertIn("foo", ev)
        self.assertEqual(ev["foo"], "bar")

    def test_ts_is_float(self):
        self.mod.log_event("test.ts")
        ev = self._read_events()[0]
        self.assertIsInstance(ev["ts"], float)

    def test_multiple_events_appended(self):
        self.mod.log_event("test.a")
        self.mod.log_event("test.b")
        events = self._read_events()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["kind"], "test.a")
        self.assertEqual(events[1]["kind"], "test.b")

    def test_logs_dir_created_automatically(self):
        logs = self.ws / "logs"
        self.assertFalse(logs.exists())
        self.mod.log_event("test.mkdir")
        self.assertTrue(logs.exists())

    def test_never_raises_on_bad_kind(self):
        # Should not raise even with bizarre inputs.
        try:
            self.mod.log_event("")
            self.mod.log_event("\x00\x01\x02")
            self.mod.log_event("ok")
        except Exception as exc:
            self.fail(f"log_event raised unexpectedly: {exc}")

    def test_non_serializable_value_stringified(self):
        class Unserializable:
            def __repr__(self):
                return "<Unserializable>"

        self.mod.log_event("test.repr", obj=Unserializable())
        ev = self._read_events()[0]
        self.assertIn("obj", ev)
        self.assertIsInstance(ev["obj"], str)
        self.assertIn("Unserializable", ev["obj"])

    def test_extra_fields_preserved(self):
        self.mod.log_event("test.extras", task_id="t-123", tier="owner", count=42)
        ev = self._read_events()[0]
        self.assertEqual(ev["task_id"], "t-123")
        self.assertEqual(ev["tier"], "owner")
        self.assertEqual(ev["count"], 42)

    def test_line_is_valid_json(self):
        self.mod.log_event("test.json", val="hello")
        path = self.mod.get_log_path()
        raw = path.read_text().splitlines()[0]
        parsed = json.loads(raw)  # raises if invalid
        self.assertEqual(parsed["kind"], "test.json")


class TestMachineIdCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        # Reset the global cache so each test starts fresh.
        self.mod._CACHED_MACHINE = None

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_returns_string(self):
        mid = self.mod._machine_id()
        self.assertIsInstance(mid, str)
        self.assertGreater(len(mid), 0)

    def test_caches_result(self):
        id1 = self.mod._machine_id()
        id2 = self.mod._machine_id()
        self.assertEqual(id1, id2)
        # Verify it's the same object (cached), not a recomputed copy.
        self.assertIs(self.mod._CACHED_MACHINE, id1)

    def test_cache_populated_after_first_call(self):
        self.assertIsNone(self.mod._CACHED_MACHINE)
        self.mod._machine_id()
        self.assertIsNotNone(self.mod._CACHED_MACHINE)

    def test_falls_back_on_missing_identity_file(self):
        # No stand-identity.json in workspace → falls back to hostname.
        mid = self.mod._machine_id()
        self.assertIsInstance(mid, str)
        self.assertNotEqual(mid, "")


if __name__ == "__main__":
    unittest.main()
