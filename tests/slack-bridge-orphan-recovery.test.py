#!/usr/bin/env python3
"""
Tests for slack-bridge _recover_orphan_sending_files (startup orphan recovery).

Guards:
  - Single orphan is recovered (renamed .sending → .txt)
  - No-op when no orphans exist
  - Multiple orphans recovered in one pass
  - Non-proactive .sending files are not touched
  - Collision: target .txt already exists → skip, don't overwrite
  - Idempotent: second call is a no-op
  - Missing results/ dir returns 0 (no crash)
  - Structural: _recover_orphan_sending_files present in slack-bridge.py
  - Structural: called in main() before result_watcher thread start

Run: python3 tests/slack-bridge-orphan-recovery.test.py
Exit: 0 on pass, 1 on fail.
"""

from __future__ import annotations
import sys
import tempfile
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "slack-bridge.py"

PASS = 0
FAIL = 0


def ok(name: str):
    global PASS
    PASS += 1
    print(f"  ✓ {name}")


def fail(name: str, reason: str):
    global FAIL
    FAIL += 1
    print(f"  ✗ {name}: {reason}")


# ---------------------------------------------------------------------------
# Load _recover_orphan_sending_files without importing the full bridge
# (which requires slack_bolt + env vars).
# ---------------------------------------------------------------------------

def _load_recover_fn():
    """Extract and exec just the _recover_orphan_sending_files function."""
    src = SRC.read_text()
    # Find the function definition
    start = src.find("def _recover_orphan_sending_files()")
    if start == -1:
        return None
    # Find the next top-level def/class after this one
    rest = src[start:]
    lines = rest.split("\n")
    func_lines = [lines[0]]
    for line in lines[1:]:
        if line and not line[0].isspace() and not line.startswith("#"):
            break
        func_lines.append(line)
    func_src = "\n".join(func_lines)

    mod = types.ModuleType("_slack_recover")
    mod.Path = Path
    # We need to patch RESULTS_DIR at call time — the function closes over it.
    # Re-exec with a patched RESULTS_DIR per test.
    return func_src


FUNC_SRC = _load_recover_fn()


def run_recover(results_dir: Path) -> int:
    """Run _recover_orphan_sending_files with a custom RESULTS_DIR."""
    if FUNC_SRC is None:
        return -1
    ns = {"Path": Path, "RESULTS_DIR": results_dir}
    exec(FUNC_SRC, ns)
    return ns["_recover_orphan_sending_files"]()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_single_orphan_recovered():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        orphan = d / "proactive-12345.sending"
        orphan.write_text("hello owner")
        n = run_recover(d)
        recovered = d / "proactive-12345.txt"
        if n == 1 and recovered.exists() and not orphan.exists():
            ok("single orphan recovered")
        else:
            fail("single orphan", f"n={n} recovered={recovered.exists()} orphan_still={orphan.exists()}")


def test_no_orphans_noop():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "proactive-99.txt").write_text("normal file")
        n = run_recover(d)
        if n == 0:
            ok("no orphans → no-op (returns 0)")
        else:
            fail("no orphans noop", f"returned {n}")


def test_multiple_orphans():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        for i in range(3):
            (d / f"proactive-{i}.sending").write_text(f"msg {i}")
        n = run_recover(d)
        recovered = [d / f"proactive-{i}.txt" for i in range(3)]
        if n == 3 and all(f.exists() for f in recovered):
            ok("multiple orphans all recovered")
        else:
            fail("multiple orphans", f"n={n}")


def test_non_proactive_sending_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "task-12345.sending").write_text("task result")
        (d / "result-abc.sending").write_text("other")
        n = run_recover(d)
        if n == 0 and (d / "task-12345.sending").exists():
            ok("non-proactive .sending files not touched")
        else:
            fail("non-proactive .sending", f"n={n}, file_exists={(d / 'task-12345.sending').exists()}")


def test_collision_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        orphan = d / "proactive-collision.sending"
        target = d / "proactive-collision.txt"
        orphan.write_text("orphan content")
        target.write_text("existing content")
        n = run_recover(d)
        # Should skip (not overwrite) — both files should still exist
        if n == 0 and target.read_text() == "existing content" and orphan.exists():
            ok("collision skipped — existing .txt not overwritten")
        else:
            fail("collision skip", f"n={n} target={target.read_text()!r} orphan={orphan.exists()}")


def test_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "proactive-idem.sending").write_text("hi")
        run_recover(d)  # first call recovers
        n2 = run_recover(d)  # second call: no .sending files left
        if n2 == 0:
            ok("idempotent — second call is no-op")
        else:
            fail("idempotent", f"second call returned {n2}")


def test_missing_results_dir():
    with tempfile.TemporaryDirectory() as tmp:
        nonexistent = Path(tmp) / "does-not-exist"
        n = run_recover(nonexistent)
        if n == 0:
            ok("missing results dir → returns 0 (no crash)")
        else:
            fail("missing results dir", f"returned {n}")


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------

def test_function_present_in_source():
    src = SRC.read_text()
    if "def _recover_orphan_sending_files" in src:
        ok("_recover_orphan_sending_files defined in slack-bridge.py")
    else:
        fail("function present", "def _recover_orphan_sending_files not found")


def test_called_in_main_before_result_watcher():
    src = SRC.read_text()
    # Find main() and check call order
    main_idx = src.find("\ndef main():")
    if main_idx == -1:
        fail("call in main", "def main() not found"); return
    main_body = src[main_idx:]
    recover_idx = main_body.find("_recover_orphan_sending_files()")
    watcher_idx = main_body.find("result_watcher")
    if recover_idx == -1:
        fail("call in main", "_recover_orphan_sending_files not called in main()")
    elif watcher_idx != -1 and recover_idx < watcher_idx:
        ok("_recover_orphan_sending_files called in main() before result_watcher")
    else:
        fail("call order", f"recover_idx={recover_idx} watcher_idx={watcher_idx}")


if __name__ == "__main__":
    if FUNC_SRC is None:
        print("FAIL: could not extract _recover_orphan_sending_files from slack-bridge.py")
        sys.exit(1)

    print("slack-bridge orphan recovery tests")
    print()
    print("functional:")
    test_single_orphan_recovered()
    test_no_orphans_noop()
    test_multiple_orphans()
    test_non_proactive_sending_ignored()
    test_collision_skipped()
    test_idempotent()
    test_missing_results_dir()

    print()
    print("structural:")
    test_function_present_in_source()
    test_called_in_main_before_result_watcher()

    print()
    if FAIL == 0:
        print(f"━━━ slack-bridge orphan recovery: {PASS} passed / 0 failed ━━━")
    else:
        print(f"━━━ FAILED: {FAIL} failed / {PASS} passed ━━━")
        sys.exit(1)
