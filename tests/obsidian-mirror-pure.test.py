#!/usr/bin/env python3
"""Tests for pure-logic functions in src/obsidian-mirror.py.

Covers functions that don't touch the Obsidian vault or OS subprocess:
  - _parse_since   (duration string → seconds)
  - _task_id_from_path  (filename → task id, using TASK_ID_RE)
  - _parse_task_file    (task file content → dict)
  - _within_window      (mtime cutoff check)

Run: python3 tests/obsidian-mirror-pure.test.py
Exit code: 0 on pass, 1 on fail.
"""

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Import the private helpers directly
import importlib.util, os
os.environ.setdefault("SUTANDO_WORKSPACE", "/tmp/obsidian-mirror-test-ws")
spec = importlib.util.spec_from_file_location(
    "obsidian_mirror",
    Path(__file__).resolve().parent.parent / "src" / "obsidian-mirror.py",
)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)

_parse_since = _mod._parse_since
_task_id_from_path = _mod._task_id_from_path
_parse_task_file = _mod._parse_task_file
_within_window = _mod._within_window

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        print(f"PASS: {name}")
        PASS += 1
    else:
        print(f"FAIL: {name}" + (f" — {detail}" if detail else ""))
        FAIL += 1


# ============================================================
# _parse_since
# ============================================================

print("\n--- _parse_since ---")

check("30m → 1800", _parse_since("30m") == 1800)
check("1h → 3600", _parse_since("1h") == 3600)
check("2h → 7200", _parse_since("2h") == 7200)
check("6h → 21600", _parse_since("6h") == 21600)
check("1d → 86400", _parse_since("1d") == 86400)
check("2d → 172800", _parse_since("2d") == 172800)
check("30s → 30", _parse_since("30s") == 30)
check("uppercase H → 3600", _parse_since("1H") == 3600)
check("uppercase M → 60", _parse_since("1M") == 60)
check("uppercase D → 86400", _parse_since("1D") == 86400)
check("plain integer string → seconds", _parse_since("120") == 120)
check("empty string → 0", _parse_since("") == 0)
check("large value: 24h → 86400", _parse_since("24h") == 86400)


# ============================================================
# _task_id_from_path  (uses TASK_ID_RE = r"^task-(.+)\.txt$")
# ============================================================

print("\n--- _task_id_from_path ---")

check("bare task-123.txt → task-123",
      _task_id_from_path(Path("task-123.txt")) == "task-123")
check("numeric id",
      _task_id_from_path(Path("task-1700000000.txt")) == "task-1700000000")
check("voice-style id",
      _task_id_from_path(Path("task-voice-123.txt")) == "task-voice-123")
check("chat-style id",
      _task_id_from_path(Path("task-chat-1700000000.txt")) == "task-chat-1700000000")

# claimed files end with .txt so the regex DOES match — (.+) captures the compound suffix
check("claimed-core-1 → compound id (regex matches .txt suffix)",
      _task_id_from_path(Path("task-123.claimed-core-1.txt")) == "task-123.claimed-core-1")

# result files don't match
check("result file → None",
      _task_id_from_path(Path("result-123.txt")) is None)
check("proactive file → None",
      _task_id_from_path(Path("proactive-1700000000.txt")) is None)

# scoped result file (dvoice prefix) → None
check("scoped result → None",
      _task_id_from_path(Path("dvoice-123.task-456.txt")) is None)

# no extension → None
check("no extension → None",
      _task_id_from_path(Path("task-123")) is None)

# sub-path (only filename part is checked)
check("path with parent dir → only filename matched",
      _task_id_from_path(Path("/workspace/tasks/task-789.txt")) == "task-789")

# alpha-numeric compound id
check("compound alpha-numeric id",
      _task_id_from_path(Path("task-abc123def.txt")) == "task-abc123def")


# ============================================================
# _parse_task_file
# ============================================================

print("\n--- _parse_task_file ---")

with tempfile.TemporaryDirectory() as _td:
    td = Path(_td)

    # standard task file
    t1 = td / "task-1.txt"
    t1.write_text(
        "id: task-1700000000\n"
        "timestamp: 2026-06-09T10:00:00Z\n"
        "task: check PRs 1084 and 1467\n"
        "source: slack\n"
        "channel_id: D0B5L7X2TK2\n"
        "user_id: U123\n"
        "access_tier: owner\n"
        "priority: normal\n"
    )
    info = _parse_task_file(t1)
    check("id parsed", info.get("id") == "task-1700000000")
    check("task field parsed", info.get("task") == "check PRs 1084 and 1467")
    check("source parsed", info.get("source") == "slack")
    check("channel_id parsed", info.get("channel_id") == "D0B5L7X2TK2")
    check("access_tier parsed", info.get("access_tier") == "owner")
    check("priority parsed", info.get("priority") == "normal")
    check("raw field populated", "check PRs" in info.get("raw", ""))

    # unknown fields are not included
    t2 = td / "task-2.txt"
    t2.write_text("id: task-2\nunknown_field: should_be_ignored\nsource: discord\n")
    info2 = _parse_task_file(t2)
    check("unknown field not in result", "unknown_field" not in info2)
    check("known field alongside unknown still parsed", info2.get("source") == "discord")

    # value with colon in it — partition() at first colon, rest preserved
    t3 = td / "task-3.txt"
    t3.write_text("task: check https://example.com/path\n")
    info3 = _parse_task_file(t3)
    check("colon in value: partition keeps full remainder incl. subsequent colons",
          info3.get("task") == "check https://example.com/path")

    # file not found → empty dict with raw=""
    info4 = _parse_task_file(td / "nonexistent.txt")
    check("missing file → raw is empty string", info4.get("raw") == "")
    check("missing file → no id key", "id" not in info4)

    # empty file
    t5 = td / "task-5.txt"
    t5.write_text("")
    info5 = _parse_task_file(t5)
    check("empty file → raw is empty string", info5.get("raw") == "")
    check("empty file → no keys beyond raw", set(info5.keys()) == {"raw"})

    # line without colon is skipped
    t6 = td / "task-6.txt"
    t6.write_text("id: task-6\nsome line with no colon here\ntask: do a thing\n")
    info6 = _parse_task_file(t6)
    check("line without colon is skipped, others parsed", info6.get("task") == "do a thing")


# ============================================================
# _within_window
# ============================================================

print("\n--- _within_window ---")

with tempfile.TemporaryDirectory() as _td:
    td = Path(_td)

    # file modified just now → within any recent cutoff
    recent = td / "recent.txt"
    recent.write_text("hi")
    now = time.time()
    check("recently modified file → within window (cutoff = 1h ago)",
          _within_window(recent, now - 3600))
    check("recently modified file → within window (cutoff = now-1s)",
          _within_window(recent, now - 1))

    # file older than cutoff: set mtime to 2h ago
    old = td / "old.txt"
    old.write_text("hi")
    old_mtime = now - 7200  # 2h ago
    os_result = __import__("os").utime(str(old), (old_mtime, old_mtime))
    check("file 2h old → outside 1h window",
          not _within_window(old, now - 3600))
    check("file 2h old → within 3h window",
          _within_window(old, now - 10800))

    # exactly at cutoff: mtime == cutoff (>= comparison)
    boundary = td / "boundary.txt"
    boundary.write_text("hi")
    cutoff_ts = now - 60
    __import__("os").utime(str(boundary), (cutoff_ts, cutoff_ts))
    check("mtime == cutoff → within window (>= is inclusive)",
          _within_window(boundary, cutoff_ts))

    # nonexistent file → False
    check("nonexistent file → False",
          not _within_window(td / "ghost.txt", now - 3600))

    # cutoff = 0 → every file is within (mtime always >= 0)
    check("cutoff=0 → any file is within", _within_window(recent, 0))

    # future cutoff → file is outside (mtime < future)
    check("future cutoff → outside window",
          not _within_window(recent, now + 9999))


# ============================================================

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
