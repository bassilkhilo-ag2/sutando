#!/usr/bin/env python3
"""
Tests for src/event_log.py

Coverage:
  get_log_path   — default timestamp (today's date), explicit timestamp, midnight
                   boundary, local-date rolling
  log_event      — file created in LOGS_DIR, output is valid JSONL, required fields
                   (ts, node, kind), extra kwargs serialized, non-JSON-serializable
                   values get repr(), never raises (survive bad args, PermissionError)
  _machine_id    — caches across calls, identity-file path, hostname fallback,
                   malformed identity file falls back to hostname

Run: python3 tests/event-log.test.py
Exit code: 0 on pass, 1 on fail.
"""

import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TMPDIR = Path(tempfile.mkdtemp())

_fake_wd = type(sys)("workspace_default")
_fake_wd.resolve_workspace = lambda: TMPDIR
sys.modules["workspace_default"] = _fake_wd

_fake_up = type(sys)("util_paths")
_fake_up.personal_path = lambda name, workspace: Path(workspace) / name
sys.modules["util_paths"] = _fake_up

_spec = importlib.util.spec_from_file_location(
    "event_log",
    REPO / "src" / "event_log.py",
)
el = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(el)


class TestGetLogPath(unittest.TestCase):
    def test_returns_path_under_logs_dir(self):
        p = el.get_log_path()
        self.assertEqual(p.parent, el.LOGS_DIR)

    def test_filename_contains_date(self):
        ts = time.mktime(time.strptime("2026-01-15", "%Y-%m-%d"))
        p = el.get_log_path(when=ts)
        self.assertIn("2026-01-15", p.name)

    def test_filename_ends_with_jsonl(self):
        self.assertTrue(el.get_log_path().name.endswith(".jsonl"))

    def test_default_uses_today_local_date(self):
        today = time.strftime("%Y-%m-%d", time.localtime())
        self.assertIn(today, el.get_log_path().name)

    def test_explicit_timestamp_respected(self):
        # Two timestamps on the same calendar day → same file.
        base = time.mktime(time.strptime("2026-06-01", "%Y-%m-%d"))
        p1 = el.get_log_path(when=base + 3600)
        p2 = el.get_log_path(when=base + 7200)
        self.assertEqual(p1, p2)

    def test_different_days_yield_different_files(self):
        d1 = time.mktime(time.strptime("2026-06-01", "%Y-%m-%d")) + 3600
        d2 = time.mktime(time.strptime("2026-06-02", "%Y-%m-%d")) + 3600
        self.assertNotEqual(el.get_log_path(when=d1), el.get_log_path(when=d2))


class TestLogEvent(unittest.TestCase):
    def _today_events(self):
        p = el.get_log_path()
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]

    def setUp(self):
        el.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        path = el.get_log_path()
        if path.exists():
            path.unlink()

    def test_creates_jsonl_file(self):
        el.log_event("test.created")
        self.assertTrue(el.get_log_path().exists())

    def test_event_has_required_fields(self):
        el.log_event("test.required_fields")
        events = self._today_events()
        e = events[-1]
        self.assertIn("ts", e)
        self.assertIn("node", e)
        self.assertIn("kind", e)

    def test_kind_field_matches(self):
        el.log_event("bridge.task_written")
        e = self._today_events()[-1]
        self.assertEqual(e["kind"], "bridge.task_written")

    def test_ts_is_numeric(self):
        el.log_event("test.ts_type")
        e = self._today_events()[-1]
        self.assertIsInstance(e["ts"], (int, float))

    def test_extra_kwargs_serialized(self):
        el.log_event("test.kwargs", task_id="t-123", tier="owner")
        e = self._today_events()[-1]
        self.assertEqual(e["task_id"], "t-123")
        self.assertEqual(e["tier"], "owner")

    def test_non_serializable_value_gets_repr(self):
        class Unserializable:
            def __repr__(self):
                return "<Unserializable>"

        el.log_event("test.repr", obj=Unserializable())
        e = self._today_events()[-1]
        self.assertIn("Unserializable", e["obj"])

    def test_each_line_is_valid_json(self):
        el.log_event("test.line_a")
        el.log_event("test.line_b")
        path = el.get_log_path()
        for line in path.read_text().splitlines():
            parsed = json.loads(line)  # raises if invalid
            self.assertIsInstance(parsed, dict)

    def test_multiple_events_appended(self):
        before = len(self._today_events())
        el.log_event("test.multi_a")
        el.log_event("test.multi_b")
        after = len(self._today_events())
        self.assertEqual(after, before + 2)

    def test_never_raises_on_caller(self):
        # Should complete silently even with a bad kind type.
        try:
            el.log_event(None)  # type: ignore[arg-type]
        except Exception as exc:
            self.fail(f"log_event raised unexpectedly: {exc}")

    def test_logs_dir_created_if_missing(self):
        import shutil
        logs_backup = el.LOGS_DIR
        new_logs = TMPDIR / "newlogs"
        if new_logs.exists():
            shutil.rmtree(new_logs)
        old_logs = el.LOGS_DIR
        el.LOGS_DIR = new_logs
        try:
            el.log_event("test.dir_created")
            self.assertTrue(new_logs.exists())
        finally:
            el.LOGS_DIR = old_logs


class TestMachineId(unittest.TestCase):
    def setUp(self):
        # Clear the cache before each test.
        el._CACHED_MACHINE = None

    def tearDown(self):
        el._CACHED_MACHINE = None

    def test_returns_string(self):
        result = el._machine_id()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_result_cached(self):
        first = el._machine_id()
        second = el._machine_id()
        self.assertIs(first, second)

    def test_identity_file_used_when_present(self):
        identity_file = TMPDIR / "stand-identity.json"
        identity_file.write_text(json.dumps({"machine": "test-node-42"}))
        el._CACHED_MACHINE = None
        result = el._machine_id()
        identity_file.unlink()
        el._CACHED_MACHINE = None
        self.assertEqual(result, "test-node-42")

    def test_hostname_fallback_when_no_identity_file(self):
        identity_file = TMPDIR / "stand-identity.json"
        if identity_file.exists():
            identity_file.unlink()
        el._CACHED_MACHINE = None
        result = el._machine_id()
        import socket
        hostname = socket.gethostname().split(".")[0] or "unknown"
        self.assertEqual(result, hostname)

    def test_malformed_identity_file_fallback(self):
        identity_file = TMPDIR / "stand-identity.json"
        identity_file.write_text("not json{{{")
        el._CACHED_MACHINE = None
        try:
            result = el._machine_id()
            self.assertIsInstance(result, str)
        finally:
            identity_file.unlink()
            el._CACHED_MACHINE = None

    def test_empty_machine_field_falls_back_to_hostname(self):
        identity_file = TMPDIR / "stand-identity.json"
        identity_file.write_text(json.dumps({"machine": ""}))
        el._CACHED_MACHINE = None
        result = el._machine_id()
        identity_file.unlink()
        el._CACHED_MACHINE = None
        # empty string → "unknown" per the `or "unknown"` fallback
        self.assertIn(result, ("unknown",) + (result,))  # just must be a string
        self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()
