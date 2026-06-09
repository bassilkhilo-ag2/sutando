#!/usr/bin/env python3
"""Tests for single_instance.py and task_archive.py.

Run: python3 tests/single-instance-task-archive.test.py
Exit code: 0 on pass, 1 on fail.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = str(Path(__file__).resolve().parent.parent / "src")
sys.path.insert(0, SRC)

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
# task_archive.find_task_file
# ============================================================

from task_archive import find_task_file

print("\n--- task_archive.find_task_file ---")

with tempfile.TemporaryDirectory() as _td:
    td = Path(_td)

    # bare file exists
    (td / "task-123.txt").write_text("id: task-123")
    result = find_task_file(td, "task-123")
    check("bare file exists → returned", result == td / "task-123.txt")

    # bare missing, claimed file exists
    claimed = td / "task-456.claimed-core-1.txt"
    claimed.write_text("id: task-456")
    result = find_task_file(td, "task-456")
    check("claimed-core-1 found when bare absent", result == claimed)

    # bare missing, multiple claimed files → first lexicographic
    c2 = td / "task-789.claimed-core-10.txt"
    c3 = td / "task-789.claimed-core-2.txt"
    c2.write_text("")
    c3.write_text("")
    result = find_task_file(td, "task-789")
    check("multiple claimed → first lexicographic", result == c2)

    # neither exists → None
    result = find_task_file(td, "task-999")
    check("missing task → None", result is None)

    # bare takes priority over claimed
    bare2 = td / "task-200.txt"
    bare2.write_text("")
    claimed2 = td / "task-200.claimed-core-1.txt"
    claimed2.write_text("")
    result = find_task_file(td, "task-200")
    check("bare takes priority over claimed", result == bare2)

    # multi-digit core number
    mc = td / "task-300.claimed-core-99.txt"
    mc.write_text("")
    result = find_task_file(td, "task-300")
    check("claimed-core-99 (multi-digit) found", result == mc)

    # voice-style task id
    vt = td / "task-voice-1700000000.txt"
    vt.write_text("")
    result = find_task_file(td, "task-voice-1700000000")
    check("voice-style task id → bare found", result == vt)

    # task id that partially matches another file (no false positives)
    (td / "task-10.txt").write_text("")
    result = find_task_file(td, "task-1")
    check("task-1 does not match task-10 (no false positive)", result is None)

    # claimed glob doesn't match different task id prefix
    (td / "task-abc.claimed-core-1.txt").write_text("")
    result = find_task_file(td, "task-ab")
    check("claimed glob prefix is exact (no partial match)", result is None)

    # empty tasks dir → None
    empty = Path(_td) / "empty-tasks"
    empty.mkdir()
    result = find_task_file(empty, "task-404")
    check("empty dir → None", result is None)


# ============================================================
# single_instance.acquire — happy path
# ============================================================

print("\n--- single_instance.acquire (happy path) ---")

with tempfile.TemporaryDirectory() as _ws:
    os.environ["SUTANDO_WORKSPACE"] = _ws

    import importlib
    import single_instance
    importlib.reload(single_instance)  # pick up new SUTANDO_WORKSPACE

    initial_fds = list(single_instance._held_fds)
    single_instance.acquire("test-lock-happy")

    lock_path = Path(_ws) / "state" / "locks" / "test-lock-happy.lock"
    check("lock file created in state/locks/", lock_path.exists())

    pid_in_file = int(lock_path.read_text().strip())
    check("PID written to lock file", pid_in_file == os.getpid())
    check("fd appended to _held_fds", len(single_instance._held_fds) > len(initial_fds))

    # lock dir created even if state/ didn't exist
    check("state/locks/ dir created", (Path(_ws) / "state" / "locks").is_dir())

    # second acquire of a different name succeeds (separate lock file)
    fds_before = len(single_instance._held_fds)
    single_instance.acquire("test-lock-different")
    lock2 = Path(_ws) / "state" / "locks" / "test-lock-different.lock"
    check("different name acquires separate lock", lock2.exists())
    check("second acquire appends another fd", len(single_instance._held_fds) > fds_before)

    # lock files contain correct PID (both)
    for name in ("test-lock-happy", "test-lock-different"):
        p = Path(_ws) / "state" / "locks" / f"{name}.lock"
        check(f"{name} lock PID == our PID", int(p.read_text().strip()) == os.getpid())


# ============================================================
# single_instance.acquire — contention (subprocess)
# ============================================================

print("\n--- single_instance.acquire (contention) ---")

with tempfile.TemporaryDirectory() as _ws:
    os.environ["SUTANDO_WORKSPACE"] = _ws
    importlib.reload(single_instance)

    # acquire the lock in THIS process
    single_instance.acquire("test-contention-lock")

    # subprocess tries to acquire the same lock — must exit 0, not reach sys.exit(42)
    contender_script = f"""
import os, sys
os.environ['SUTANDO_WORKSPACE'] = {repr(_ws)}
sys.path.insert(0, {repr(SRC)})
from single_instance import acquire
acquire("test-contention-lock")
sys.exit(42)   # must NOT reach here on contention
"""
    result = subprocess.run(
        [sys.executable, "-c", contender_script],
        capture_output=True, timeout=10,
    )
    check("contention exits 0 (launchd-friendly, not 42)", result.returncode == 0)
    check("contention prints 'another instance' to stderr",
          b"another instance" in result.stderr)

    # subprocess acquires a DIFFERENT name — succeeds, reaches sys.exit(42)
    free_script = f"""
import os, sys
os.environ['SUTANDO_WORKSPACE'] = {repr(_ws)}
sys.path.insert(0, {repr(SRC)})
from single_instance import acquire
acquire("test-free-lock")
sys.exit(42)   # must reach here (no contention)
"""
    result2 = subprocess.run(
        [sys.executable, "-c", free_script],
        capture_output=True, timeout=10,
    )
    check("different lock name — subprocess exits 42 (acquired, reached exit)", result2.returncode == 42)

    # contention message contains the lock name
    contender2_script = f"""
import os, sys
os.environ['SUTANDO_WORKSPACE'] = {repr(_ws)}
sys.path.insert(0, {repr(SRC)})
from single_instance import acquire
acquire("test-contention-lock")
"""
    result3 = subprocess.run(
        [sys.executable, "-c", contender2_script],
        capture_output=True, timeout=10,
    )
    check("contention stderr contains lock name", b"test-contention-lock" in result3.stderr)


# ============================================================
# single_instance.acquire — idempotent lock dir creation
# ============================================================

print("\n--- single_instance.acquire (lock dir) ---")

with tempfile.TemporaryDirectory() as _ws:
    os.environ["SUTANDO_WORKSPACE"] = _ws
    importlib.reload(single_instance)

    # pre-create locks dir — acquire must not fail
    locks_dir = Path(_ws) / "state" / "locks"
    locks_dir.mkdir(parents=True)
    single_instance.acquire("test-prexisting-dir")
    lp = locks_dir / "test-prexisting-dir.lock"
    check("pre-existing locks dir — acquire succeeds", lp.exists())

    # only state/ exists, no locks/ sub-dir
    with tempfile.TemporaryDirectory() as _ws2:
        os.environ["SUTANDO_WORKSPACE"] = _ws2
        importlib.reload(single_instance)
        (Path(_ws2) / "state").mkdir()
        single_instance.acquire("test-no-locks-subdir")
        lp2 = Path(_ws2) / "state" / "locks" / "test-no-locks-subdir.lock"
        check("state/ exists but locks/ missing — created on demand", lp2.exists())


# ============================================================

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
