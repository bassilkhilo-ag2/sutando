#!/usr/bin/env python3
"""Regression test for obsidian-mirror claimed-task-glob bug.

Before fix: TASK_ID_RE = r"^task-(.+)\.txt$" — (.+) is greedy and matches
  "123.claimed-core-1" in task-123.claimed-core-1.txt, so sweep() would create
  an Obsidian note named Agent/Tasks/task-123.claimed-core-1.md instead of
  ignoring the file entirely.

After fix: TASK_ID_RE = r"^task-([^.]+)\.txt$" — [^.]+ stops at the first dot,
  so task-123.claimed-core-1.txt does NOT match (no bare .txt follows the id)
  and _task_id_from_path returns None.

Run: python3 tests/obsidian-mirror-claimed-task-glob.test.py
"""

import sys
import os
import importlib.util
from pathlib import Path

os.environ.setdefault("SUTANDO_WORKSPACE", "/tmp/obsidian-mirror-claimed-test")
spec = importlib.util.spec_from_file_location(
    "obsidian_mirror",
    Path(__file__).resolve().parent.parent / "src" / "obsidian-mirror.py",
)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)

_task_id_from_path = _mod._task_id_from_path

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


# --- claimed files must return None (not a compound id) ---

check("claimed-core-1 → None",
      _task_id_from_path(Path("task-123.claimed-core-1.txt")) is None)
check("claimed-core-10 (multi-digit) → None",
      _task_id_from_path(Path("task-456.claimed-core-10.txt")) is None)
check("voice task claimed → None",
      _task_id_from_path(Path("task-voice-1700000000.claimed-core-2.txt")) is None)
check("chat task claimed → None",
      _task_id_from_path(Path("task-chat-1700000000.claimed-core-1.txt")) is None)

# --- bare task files still work ---

check("bare numeric task → correct id",
      _task_id_from_path(Path("task-1700000000.txt")) == "task-1700000000")
check("bare voice task → correct id",
      _task_id_from_path(Path("task-voice-1700000000.txt")) == "task-voice-1700000000")
check("bare chat task → correct id",
      _task_id_from_path(Path("task-chat-1700000000.txt")) == "task-chat-1700000000")

# --- non-task filenames still return None ---

check("result file → None",
      _task_id_from_path(Path("result-123.txt")) is None)
check("proactive file → None",
      _task_id_from_path(Path("proactive-1700000000.txt")) is None)
check("scoped result → None",
      _task_id_from_path(Path("dvoice-123.task-456.txt")) is None)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
