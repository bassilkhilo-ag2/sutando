#!/usr/bin/env python3
"""
Tests for src/archive-stale-results.py

Covers main() — the retention sweep:
  - Missing results/ dir → no-op exit 0
  - Fresh files (within cutoff) → not archived
  - Stale files (past cutoff) → moved to archive-YYYY-MM-DD/
  - DRY_RUN mode → print only, no move
  - Non-.txt files → skipped
  - Files inside archive-* subdirs → never touched
  - RETENTION_HOURS env override → custom cutoff respected
  - Exit code 0 on success, 1 on errors

Run: python3 tests/archive-stale-results.test.py
Exit code: 0 on pass, 1 on fail.
"""

from __future__ import annotations
import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "archive_stale_results", REPO / "src" / "archive-stale-results.py"
)
asr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(asr)

PASS = 0
FAIL = 0


def ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  PASS  {label}")


def fail(label: str, msg: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  FAIL  {label}: {msg}")


def _run(ws: Path, dry_run: bool = False, retention_hours: int = 24) -> int:
    """Run main() with patched WORKSPACE, RESULTS, DRY_RUN, RETENTION_HOURS."""
    results = ws / "results"
    with patch.object(asr, "WORKSPACE", ws), \
         patch.object(asr, "RESULTS", results), \
         patch.object(asr, "DRY_RUN", dry_run), \
         patch.object(asr, "RETENTION_HOURS", retention_hours):
        return asr.main()


def _make_stale(path: Path, hours_old: float = 25.0) -> None:
    """Write a file and backdate its mtime."""
    path.write_text("content")
    old_time = time.time() - hours_old * 3600
    os.utime(path, (old_time, old_time))


# ── missing results dir ──────────────────────────────────────────────────────

def test_missing_results_dir():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        # results/ does not exist
        rc = _run(ws)
    if rc == 0:
        ok("(ar-a) missing results/ → exit 0 (no-op)")
    else:
        fail("(ar-a) missing results/ → exit 0 (no-op)", f"got rc={rc}")


# ── fresh files not archived ─────────────────────────────────────────────────

def test_fresh_file_not_archived():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        results = ws / "results"
        results.mkdir()
        # mtime = now (well within 24h cutoff)
        (results / "task-001.txt").write_text("fresh")
        rc = _run(ws)
        remaining = list(results.glob("task-*.txt"))
    if rc == 0 and len(remaining) == 1:
        ok("(ar-b) fresh file → not archived")
    else:
        fail("(ar-b) fresh file → not archived",
             f"rc={rc} remaining={remaining}")


# ── stale files moved ────────────────────────────────────────────────────────

def test_stale_file_archived():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        results = ws / "results"
        results.mkdir()
        _make_stale(results / "task-002.txt", hours_old=25)
        rc = _run(ws)
        archive_dirs = [d for d in results.iterdir() if d.is_dir() and d.name.startswith("archive-")]
        archived_files = list(archive_dirs[0].glob("*.txt")) if archive_dirs else []
        still_in_results = list(results.glob("task-*.txt"))
    if rc == 0 and len(archived_files) == 1 and not still_in_results:
        ok("(ar-c) stale file (25h) → moved to archive-*/")
    else:
        fail("(ar-c) stale file (25h) → moved to archive-*/",
             f"rc={rc} archived={archived_files} remaining={still_in_results}")


def test_archive_dir_named_by_date():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        results = ws / "results"
        results.mkdir()
        _make_stale(results / "task-003.txt", hours_old=26)
        _run(ws)
        archive_dirs = [d for d in results.iterdir() if d.is_dir()]
    today = time.strftime("archive-%Y-%m-%d")
    if len(archive_dirs) == 1 and archive_dirs[0].name == today:
        ok("(ar-d) archive subdir named archive-YYYY-MM-DD")
    else:
        fail("(ar-d) archive subdir named archive-YYYY-MM-DD",
             f"dirs={[d.name for d in archive_dirs]} expected={today}")


def test_multiple_stale_files_all_archived():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        results = ws / "results"
        results.mkdir()
        for i in range(5):
            _make_stale(results / f"task-{i:03d}.txt", hours_old=30)
        _run(ws)
        archive_dirs = [d for d in results.iterdir() if d.is_dir()]
        archived = list(archive_dirs[0].glob("*.txt")) if archive_dirs else []
        remaining = list(results.glob("task-*.txt"))
    if len(archived) == 5 and not remaining:
        ok("(ar-e) 5 stale files → all archived")
    else:
        fail("(ar-e) 5 stale files → all archived",
             f"archived={len(archived)} remaining={len(remaining)}")


# ── DRY_RUN mode ─────────────────────────────────────────────────────────────

def test_dry_run_does_not_move():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        results = ws / "results"
        results.mkdir()
        _make_stale(results / "task-004.txt", hours_old=30)
        _run(ws, dry_run=True)
        still_there = (results / "task-004.txt").exists()
        archive_dirs = [d for d in results.iterdir() if d.is_dir()]
    if still_there and not archive_dirs:
        ok("(ar-f) DRY_RUN=1 → file stays, no archive dir created")
    else:
        fail("(ar-f) DRY_RUN=1 → file stays, no archive dir created",
             f"still_there={still_there} archive_dirs={archive_dirs}")


# ── non-.txt files skipped ───────────────────────────────────────────────────

def test_non_txt_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        results = ws / "results"
        results.mkdir()
        # .json and .log files — should not be archived even if stale
        _make_stale(results / "task-005.json", hours_old=48)
        _make_stale(results / "calls.log", hours_old=48)
        _run(ws)
        archive_dirs = [d for d in results.iterdir() if d.is_dir()]
    if not archive_dirs:
        ok("(ar-g) non-.txt files → not archived (no archive dir)")
    else:
        fail("(ar-g) non-.txt files → not archived",
             f"unexpected archive dirs: {[d.name for d in archive_dirs]}")


# ── archive-* subdirs not touched ───────────────────────────────────────────

def test_archive_subdir_contents_not_re_archived():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        results = ws / "results"
        results.mkdir()
        # Pre-existing archive directory with a stale file inside
        existing_archive = results / "archive-2026-01-01"
        existing_archive.mkdir()
        old_file = existing_archive / "task-old.txt"
        _make_stale(old_file, hours_old=500)
        _run(ws)
        # The file should still be where it was — not moved again
        still_there = old_file.exists()
        new_dirs = [d for d in results.iterdir() if d.is_dir() and d.name != "archive-2026-01-01"]
    if still_there and not new_dirs:
        ok("(ar-h) files in archive-* subdirs not re-archived")
    else:
        fail("(ar-h) files in archive-* subdirs not re-archived",
             f"still_there={still_there} new_dirs={new_dirs}")


# ── RETENTION_HOURS override ─────────────────────────────────────────────────

def test_retention_hours_custom():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        results = ws / "results"
        results.mkdir()
        # 2h old file — stale under 1h retention, fresh under 24h
        _make_stale(results / "task-006.txt", hours_old=2)
        _run(ws, retention_hours=1)  # 1h cutoff → should archive
        archive_dirs = [d for d in results.iterdir() if d.is_dir()]
        archived = list(archive_dirs[0].glob("*.txt")) if archive_dirs else []
    if len(archived) == 1:
        ok("(ar-i) RETENTION_HOURS=1 archives 2h-old file")
    else:
        fail("(ar-i) RETENTION_HOURS=1 archives 2h-old file",
             f"archived={archived}")


def test_retention_hours_keeps_file_within_window():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        results = ws / "results"
        results.mkdir()
        # 2h old file — within 48h retention window
        _make_stale(results / "task-007.txt", hours_old=2)
        _run(ws, retention_hours=48)
        archive_dirs = [d for d in results.iterdir() if d.is_dir()]
    if not archive_dirs:
        ok("(ar-j) RETENTION_HOURS=48 keeps 2h-old file")
    else:
        fail("(ar-j) RETENTION_HOURS=48 keeps 2h-old file",
             f"unexpected archive dirs: {[d.name for d in archive_dirs]}")


# ── exit code ────────────────────────────────────────────────────────────────

def test_exit_code_0_on_success():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "results").mkdir()
        rc = _run(ws)
    if rc == 0:
        ok("(ar-k) clean run → exit code 0")
    else:
        fail("(ar-k) clean run → exit code 0", f"got rc={rc}")


def test_mixed_fresh_and_stale():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        results = ws / "results"
        results.mkdir()
        # 1 fresh, 2 stale
        (results / "task-fresh.txt").write_text("fresh")
        _make_stale(results / "task-old1.txt", hours_old=30)
        _make_stale(results / "task-old2.txt", hours_old=48)
        _run(ws)
        archive_dirs = [d for d in results.iterdir() if d.is_dir()]
        archived = list(archive_dirs[0].glob("*.txt")) if archive_dirs else []
        remaining_txt = list(results.glob("task-*.txt"))
    if len(archived) == 2 and len(remaining_txt) == 1 and remaining_txt[0].name == "task-fresh.txt":
        ok("(ar-l) mixed: 2 stale archived, 1 fresh kept")
    else:
        fail("(ar-l) mixed: 2 stale archived, 1 fresh kept",
             f"archived={len(archived)} remaining={[f.name for f in remaining_txt]}")


if __name__ == "__main__":
    print("archive-stale-results tests")
    print("=" * 40)
    test_missing_results_dir()
    test_fresh_file_not_archived()
    test_stale_file_archived()
    test_archive_dir_named_by_date()
    test_multiple_stale_files_all_archived()
    test_dry_run_does_not_move()
    test_non_txt_skipped()
    test_archive_subdir_contents_not_re_archived()
    test_retention_hours_custom()
    test_retention_hours_keeps_file_within_window()
    test_exit_code_0_on_success()
    test_mixed_fresh_and_stale()
    print("=" * 40)
    print(f"Results: {PASS} passed, {FAIL} failed")
    sys.exit(0 if FAIL == 0 else 1)
