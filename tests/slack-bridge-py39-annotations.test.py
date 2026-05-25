#!/usr/bin/env python3
"""Regression guard: slack-bridge.py has from __future__ import annotations.

slack-bridge.py uses str | None union syntax (lines 200, 231, 245, 272, 405,
415, 462, 485) which requires Python 3.10+ without this import. With it, all
annotations are lazy-evaluated and compatible with Python 3.9.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = (REPO / "src" / "slack-bridge.py").read_text(encoding="utf-8")


def test_future_annotations_present():
    assert "from __future__ import annotations" in SRC, (
        "slack-bridge.py is missing 'from __future__ import annotations' — "
        "str | None union syntax breaks on Python 3.9"
    )


def test_future_annotations_at_top():
    lines = SRC.splitlines()
    # Must appear in the first 5 lines (after shebang, docstring, or blank lines)
    top = "\n".join(lines[:5])
    assert "from __future__ import annotations" in top, (
        "from __future__ import annotations must be near the top of the file "
        "(PEP 236 requires it before any other imports that use the annotations)"
    )


def test_pipe_union_syntax_present():
    """Confirm the union syntax that triggered this fix is still in the file."""
    assert "str | None" in SRC or "| None" in SRC, (
        "str | None syntax not found — the fix may no longer be needed "
        "or the code was refactored; verify this test is still relevant"
    )


def main():
    tests = [
        test_future_annotations_present,
        test_future_annotations_at_top,
        test_pipe_union_syntax_present,
    ]
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            failures.append(f"{fn.__name__}: {e}")
            print(f"  ✗ {fn.__name__}: {e}")
    print()
    if failures:
        print(f"{len(failures)} test(s) failed ({len(tests) - len(failures)} passed).")
        sys.exit(1)
    print(f"All {len(tests)} slack-bridge-py39 tests passed.")


if __name__ == "__main__":
    main()
