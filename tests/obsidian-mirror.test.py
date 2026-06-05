"""Unit tests for src/obsidian-mirror.py.

Run: `python3 tests/obsidian-mirror.test.py`
"""
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "obsidian-mirror.py"

sys.path.insert(0, str(ROOT / "src"))


def _load(workspace: Path):
    os.environ["SUTANDO_WORKSPACE"] = str(workspace)
    spec = importlib.util.spec_from_file_location("obsidian_mirror", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestParseSince(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_minutes(self):
        self.assertEqual(self.mod._parse_since("30m"), 1800)

    def test_hours(self):
        self.assertEqual(self.mod._parse_since("1h"), 3600)
        self.assertEqual(self.mod._parse_since("6h"), 21600)

    def test_days(self):
        self.assertEqual(self.mod._parse_since("1d"), 86400)

    def test_seconds_suffix(self):
        self.assertEqual(self.mod._parse_since("120s"), 120)

    def test_plain_integer(self):
        self.assertEqual(self.mod._parse_since("60"), 60)

    def test_uppercase_suffix(self):
        self.assertEqual(self.mod._parse_since("2H"), 7200)


class TestTaskIdFromPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_valid_task_filename(self):
        self.assertEqual(self.mod._task_id_from_path(Path("task-abc123.txt")), "task-abc123")

    def test_numeric_id(self):
        self.assertEqual(self.mod._task_id_from_path(Path("task-1780000000.txt")), "task-1780000000")

    def test_non_task_filename_returns_none(self):
        self.assertIsNone(self.mod._task_id_from_path(Path("result-123.txt")))

    def test_proactive_filename_returns_none(self):
        self.assertIsNone(self.mod._task_id_from_path(Path("proactive-morning-123.txt")))


class TestParseTaskFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_parses_known_fields(self):
        f = self.ws / "task-test.txt"
        f.write_text(
            "id: task-test\n"
            "timestamp: 2024-01-01T00:00:00Z\n"
            "task: Fix the login bug\n"
            "source: slack\n"
            "access_tier: owner\n"
        )
        info = self.mod._parse_task_file(f)
        self.assertEqual(info["id"], "task-test")
        self.assertEqual(info["source"], "slack")
        self.assertEqual(info["task"], "Fix the login bug")
        self.assertEqual(info["access_tier"], "owner")

    def test_missing_file_returns_empty_info(self):
        info = self.mod._parse_task_file(self.ws / "missing.txt")
        self.assertEqual(info["raw"], "")

    def test_raw_field_preserved(self):
        f = self.ws / "task-raw.txt"
        content = "id: task-raw\ntask: Do thing\n"
        f.write_text(content)
        info = self.mod._parse_task_file(f)
        self.assertEqual(info["raw"], content)

    def test_unknown_keys_ignored(self):
        f = self.ws / "task-x.txt"
        f.write_text("id: task-x\nfoo: bar\n")
        info = self.mod._parse_task_file(f)
        self.assertNotIn("foo", info)


class TestEnsureVault(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_creates_required_directories(self):
        vault = self.ws / "vault"
        self.mod._ensure_vault(vault)
        self.assertTrue((vault / ".obsidian").exists())
        self.assertTrue((vault / "Sutando" / "Agent" / "Tasks").exists())
        self.assertTrue((vault / "Sutando" / "Agent" / "Notes").exists())

    def test_idempotent_on_second_call(self):
        vault = self.ws / "vault"
        self.mod._ensure_vault(vault)
        self.mod._ensure_vault(vault)  # should not raise
        self.assertTrue((vault / "Sutando" / "Agent" / "Tasks").exists())


class TestWriteTaskMirror(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        self.vault = self.ws / "vault"
        self.mod._ensure_vault(self.vault)
        self.tasks = self.ws / "tasks"
        self.tasks.mkdir()

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def _task(self, name: str, content: str) -> Path:
        p = self.tasks / name
        p.write_text(content)
        return p

    def test_creates_mirror_file(self):
        p = self._task("task-abc.txt", "id: task-abc\ntask: Do thing\nsource: slack\n")
        wrote = self.mod._write_task_mirror(self.vault, p)
        mirror = self.vault / "Sutando" / "Agent" / "Tasks" / "task-abc.md"
        self.assertTrue(wrote)
        self.assertTrue(mirror.exists())

    def test_mirror_contains_pending_status(self):
        p = self._task("task-def.txt", "id: task-def\ntask: Other thing\n")
        self.mod._write_task_mirror(self.vault, p)
        content = (self.vault / "Sutando" / "Agent" / "Tasks" / "task-def.md").read_text()
        self.assertIn("status: pending", content)

    def test_mirror_contains_raw_task_text(self):
        p = self._task("task-ghi.txt", "id: task-ghi\ntask: Fix login bug\n")
        self.mod._write_task_mirror(self.vault, p)
        content = (self.vault / "Sutando" / "Agent" / "Tasks" / "task-ghi.md").read_text()
        self.assertIn("Fix login bug", content)

    def test_idempotent_returns_false(self):
        p = self._task("task-idem.txt", "id: task-idem\ntask: Do thing\n")
        self.mod._write_task_mirror(self.vault, p)
        wrote2 = self.mod._write_task_mirror(self.vault, p)
        self.assertFalse(wrote2)

    def test_non_task_filename_returns_false(self):
        p = self.tasks / "proactive-123.txt"
        p.write_text("not a task")
        self.assertFalse(self.mod._write_task_mirror(self.vault, p))

    def test_preserves_existing_result_block(self):
        # Create task mirror with a result already appended
        p = self._task("task-res.txt", "id: task-res\ntask: Thing\n")
        self.mod._write_task_mirror(self.vault, p)
        mirror = self.vault / "Sutando" / "Agent" / "Tasks" / "task-res.md"
        mirror.write_text(mirror.read_text() + "\n## Result\n\nDone!\n")
        # Re-write the task mirror — result block should survive
        self.mod._write_task_mirror(self.vault, p)
        self.assertIn("## Result", mirror.read_text())
        self.assertIn("Done!", mirror.read_text())


class TestWriteResultMirror(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        self.vault = self.ws / "vault"
        self.mod._ensure_vault(self.vault)
        self.results = self.ws / "results"
        self.results.mkdir()

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_appends_result_to_existing_task_mirror(self):
        # First create a task mirror
        tasks = self.ws / "tasks"
        tasks.mkdir()
        tp = tasks / "task-jkl.txt"
        tp.write_text("id: task-jkl\ntask: Do it\n")
        self.mod._write_task_mirror(self.vault, tp)
        # Now mirror the result
        rp = self.results / "task-jkl.txt"
        rp.write_text("Task completed successfully.")
        wrote = self.mod._write_result_mirror(self.vault, rp)
        mirror = (self.vault / "Sutando" / "Agent" / "Tasks" / "task-jkl.md").read_text()
        self.assertTrue(wrote)
        self.assertIn("## Result", mirror)
        self.assertIn("Task completed successfully.", mirror)
        self.assertIn("status: completed", mirror)

    def test_creates_mirror_when_no_task_file_seen(self):
        rp = self.results / "task-orphan.txt"
        rp.write_text("Orphan result here.")
        wrote = self.mod._write_result_mirror(self.vault, rp)
        mirror = self.vault / "Sutando" / "Agent" / "Tasks" / "task-orphan.md"
        self.assertTrue(wrote)
        self.assertTrue(mirror.exists())
        self.assertIn("status: completed", mirror.read_text())

    def test_second_call_does_not_duplicate_result_block(self):
        rp = self.results / "task-idem2.txt"
        rp.write_text("Done.")
        self.mod._write_result_mirror(self.vault, rp)
        self.mod._write_result_mirror(self.vault, rp)
        mirror = (self.vault / "Sutando" / "Agent" / "Tasks" / "task-idem2.md").read_text()
        self.assertEqual(mirror.count("## Result"), 1)

    def test_non_task_filename_returns_false(self):
        rp = self.results / "proactive-morning-123.txt"
        rp.write_text("briefing")
        self.assertFalse(self.mod._write_result_mirror(self.vault, rp))


class TestMirrorAsks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        self.vault = self.ws / "vault"
        self.mod._ensure_vault(self.vault)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_missing_source_returns_false(self):
        self.assertFalse(self.mod._mirror_asks(self.vault, self.ws))

    def test_creates_asks_file(self):
        (self.ws / "pending-questions.md").write_text("## Q1\n\nOpen.\n")
        wrote = self.mod._mirror_asks(self.vault, self.ws)
        asks = self.vault / "Sutando" / "Agent" / "Asks.md"
        self.assertTrue(wrote)
        self.assertIn("Q1", asks.read_text())

    def test_idempotent_returns_false(self):
        (self.ws / "pending-questions.md").write_text("## Q1\n\nOpen.\n")
        self.mod._mirror_asks(self.vault, self.ws)
        self.assertFalse(self.mod._mirror_asks(self.vault, self.ws))


class TestMirrorNote(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        self.vault = self.ws / "vault"
        self.mod._ensure_vault(self.vault)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_creates_note_mirror(self):
        note = self.ws / "notes" / "my-note.md"
        note.parent.mkdir(exist_ok=True)
        note.write_text("# My Note\nContent here.\n")
        wrote = self.mod._mirror_note(self.vault, note)
        dest = self.vault / "Sutando" / "Agent" / "Notes" / "my-note.md"
        self.assertTrue(wrote)
        self.assertIn("Content here.", dest.read_text())

    def test_non_md_file_not_mirrored(self):
        txt = self.ws / "notes" / "data.txt"
        txt.parent.mkdir(exist_ok=True)
        txt.write_text("data")
        self.assertFalse(self.mod._mirror_note(self.vault, txt))

    def test_idempotent_returns_false(self):
        note = self.ws / "notes" / "repeat.md"
        note.parent.mkdir(exist_ok=True)
        note.write_text("# Repeat\n")
        self.mod._mirror_note(self.vault, note)
        self.assertFalse(self.mod._mirror_note(self.vault, note))


class TestWithinWindow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_recent_file_in_window(self):
        f = self.ws / "recent.txt"
        f.write_text("x")
        self.assertTrue(self.mod._within_window(f, time.time() - 60))

    def test_old_file_not_in_window(self):
        f = self.ws / "old.txt"
        f.write_text("x")
        os.utime(f, (time.time() - 7200, time.time() - 7200))
        self.assertFalse(self.mod._within_window(f, time.time() - 60))

    def test_missing_file_returns_false(self):
        self.assertFalse(self.mod._within_window(self.ws / "missing.txt", time.time() - 60))


class TestSweep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        self.vault = self.ws / "vault"

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_empty_workspace_returns_zero_counts(self):
        counts = self.mod.sweep(self.vault, self.ws)
        self.assertEqual(counts["tasks"], 0)
        self.assertEqual(counts["results"], 0)
        self.assertEqual(counts["notes"], 0)
        self.assertEqual(counts["asks"], 0)

    def test_task_file_counted(self):
        tasks = self.ws / "tasks"
        tasks.mkdir()
        (tasks / "task-sweep1.txt").write_text("id: task-sweep1\ntask: Test\n")
        counts = self.mod.sweep(self.vault, self.ws)
        self.assertEqual(counts["tasks"], 1)

    def test_note_file_counted(self):
        notes = self.ws / "notes"
        notes.mkdir()
        (notes / "plan.md").write_text("# Plan\n")
        counts = self.mod.sweep(self.vault, self.ws)
        self.assertEqual(counts["notes"], 1)

    def test_since_window_excludes_old_files(self):
        tasks = self.ws / "tasks"
        tasks.mkdir()
        old_task = tasks / "task-old.txt"
        old_task.write_text("id: task-old\ntask: Old\n")
        os.utime(old_task, (time.time() - 7200, time.time() - 7200))
        # Only sync files modified in last 60 seconds
        counts = self.mod.sweep(self.vault, self.ws, since_seconds=60)
        self.assertEqual(counts["tasks"], 0)

    def test_since_window_includes_recent_files(self):
        tasks = self.ws / "tasks"
        tasks.mkdir()
        (tasks / "task-new.txt").write_text("id: task-new\ntask: New\n")
        counts = self.mod.sweep(self.vault, self.ws, since_seconds=60)
        self.assertEqual(counts["tasks"], 1)


class TestMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        os.environ.pop("SUTANDO_OBSIDIAN_MIRROR", None)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        os.environ.pop("SUTANDO_OBSIDIAN_MIRROR", None)
        self.tmp.cleanup()

    def test_gated_without_env_var(self):
        vault = self.ws / "vault"
        ret = self.mod.main(["--vault", str(vault)])
        self.assertEqual(ret, 0)
        self.assertFalse(vault.exists())

    def test_force_bypasses_gate(self):
        vault = self.ws / "vault"
        ret = self.mod.main(["--vault", str(vault), "--force"])
        self.assertEqual(ret, 0)
        self.assertTrue(vault.exists())

    def test_env_var_enables_sync(self):
        os.environ["SUTANDO_OBSIDIAN_MIRROR"] = "1"
        vault = self.ws / "vault"
        ret = self.mod.main(["--vault", str(vault)])
        self.assertEqual(ret, 0)
        self.assertTrue(vault.exists())

    def test_env_var_true_string(self):
        os.environ["SUTANDO_OBSIDIAN_MIRROR"] = "true"
        vault = self.ws / "vault"
        ret = self.mod.main(["--vault", str(vault)])
        self.assertEqual(ret, 0)


if __name__ == "__main__":
    unittest.main()
