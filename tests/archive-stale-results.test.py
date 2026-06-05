"""Unit tests for src/archive-stale-results.py.

Run: `python3 tests/archive-stale-results.test.py`
"""
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "archive-stale-results.py"

sys.path.insert(0, str(ROOT / "src"))


def _load(workspace: Path, retention_hours: int = 24, dry_run: bool = False):
    os.environ["SUTANDO_WORKSPACE"] = str(workspace)
    os.environ["RETENTION_HOURS"] = str(retention_hours)
    os.environ["DRY_RUN"] = "1" if dry_run else "0"
    spec = importlib.util.spec_from_file_location("archive_stale_results", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestDryRunParsing(unittest.TestCase):
    """DRY_RUN env var edge cases."""

    def _check(self, val: str, expected: bool):
        with tempfile.TemporaryDirectory() as d:
            os.environ["SUTANDO_WORKSPACE"] = d
            os.environ["RETENTION_HOURS"] = "24"
            os.environ["DRY_RUN"] = val
            spec = importlib.util.spec_from_file_location("archive_stale_results_dr", SRC)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.assertEqual(mod.DRY_RUN, expected, f"DRY_RUN={val!r}")

    def tearDown(self):
        for k in ("SUTANDO_WORKSPACE", "RETENTION_HOURS", "DRY_RUN"):
            os.environ.pop(k, None)

    def test_empty_string_is_false(self):
        self._check("", False)

    def test_zero_is_false(self):
        self._check("0", False)

    def test_false_is_false(self):
        self._check("false", False)

    def test_no_is_false(self):
        self._check("no", False)

    def test_one_is_true(self):
        self._check("1", True)

    def test_true_is_true(self):
        self._check("true", True)

    def test_yes_is_true(self):
        self._check("yes", True)

    def test_uppercase_FALSE_is_false(self):
        self._check("FALSE", False)

    def test_uppercase_NO_is_false(self):
        self._check("No", False)


class TestMainNoResults(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)

    def tearDown(self):
        for k in ("SUTANDO_WORKSPACE", "RETENTION_HOURS", "DRY_RUN"):
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def test_missing_results_dir_returns_zero(self):
        mod = _load(self.ws)
        ret = mod.main()
        self.assertEqual(ret, 0)

    def test_empty_results_dir_returns_zero(self):
        (self.ws / "results").mkdir()
        mod = _load(self.ws)
        ret = mod.main()
        self.assertEqual(ret, 0)


class TestSweep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.results = self.ws / "results"
        self.results.mkdir()

    def tearDown(self):
        for k in ("SUTANDO_WORKSPACE", "RETENTION_HOURS", "DRY_RUN"):
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def _make_file(self, name: str, age_hours: float) -> Path:
        f = self.results / name
        f.write_text("content")
        mtime = time.time() - age_hours * 3600
        os.utime(f, (mtime, mtime))
        return f

    def test_fresh_file_not_archived(self):
        fresh = self._make_file("result-fresh.txt", age_hours=0.5)
        mod = _load(self.ws, retention_hours=24)
        mod.main()
        self.assertTrue(fresh.exists(), "fresh file must not be archived")

    def test_stale_file_archived(self):
        stale = self._make_file("result-stale.txt", age_hours=25)
        mod = _load(self.ws, retention_hours=24)
        mod.main()
        self.assertFalse(stale.exists(), "stale file must be moved out of results/")
        # File should appear in an archive-YYYY-MM-DD/ subdirectory.
        archives = list(self.results.glob("archive-*/result-stale.txt"))
        self.assertEqual(len(archives), 1)

    def test_non_txt_file_ignored(self):
        f = self._make_file("something.json", age_hours=100)
        mod = _load(self.ws, retention_hours=24)
        mod.main()
        self.assertTrue(f.exists(), "non-.txt files must not be archived")

    def test_dry_run_does_not_move(self):
        stale = self._make_file("result-stale.txt", age_hours=25)
        mod = _load(self.ws, retention_hours=24, dry_run=True)
        mod.main()
        self.assertTrue(stale.exists(), "dry-run must not move files")

    def test_archive_subdir_files_untouched(self):
        # Files already inside an archive-* subdir must never be re-archived.
        subdir = self.results / "archive-2000-01-01"
        subdir.mkdir()
        old = subdir / "old.txt"
        old.write_text("old")
        old_mtime = time.time() - 999 * 3600
        os.utime(old, (old_mtime, old_mtime))
        mod = _load(self.ws, retention_hours=24)
        mod.main()
        self.assertTrue(old.exists(), "files already in archive-* subdir must not be touched")

    def test_multiple_stale_files_archived(self):
        for i in range(3):
            self._make_file(f"result-{i}.txt", age_hours=30)
        mod = _load(self.ws, retention_hours=24)
        mod.main()
        remaining = list(self.results.glob("*.txt"))
        self.assertEqual(len(remaining), 0)
        archived = list(self.results.glob("archive-*/*.txt"))
        self.assertEqual(len(archived), 3)

    def test_returns_zero_on_success(self):
        self._make_file("stale.txt", age_hours=25)
        mod = _load(self.ws, retention_hours=24)
        ret = mod.main()
        self.assertEqual(ret, 0)

    def test_retention_hours_env_respected(self):
        # 1-hour retention: a 2-hour-old file should be archived.
        stale = self._make_file("result-old.txt", age_hours=2)
        mod = _load(self.ws, retention_hours=1)
        mod.main()
        self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
