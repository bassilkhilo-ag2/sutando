#!/usr/bin/env python3
"""Structural tests for #1425 fix: selection-first on the push-mode path.

PR #1409 added selection-first to the pull path (vision_query).
#1425 / this fix patches captureAndSend() — the shared push-path function
called by tick() on every frame tick.

These are source-level assertions (read file as text) rather than runtime
tests, to avoid subprocess side effects and TypeScript import overhead.

Run: python3 tests/vision-push-mode-selection-first.test.py
Exit: 0 on pass, 1 on fail.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VISION_TOOLS = REPO / "src" / "vision-tools.ts"


def _src() -> str:
    return VISION_TOOLS.read_text(encoding="utf-8")


def test_probeSelectedText_function_exists() -> None:
    """probeSelectedText() must be defined — it's the AX/Chrome probe."""
    src = _src()
    assert "function probeSelectedText()" in src, (
        "probeSelectedText() not found in vision-tools.ts — #1425 fix missing"
    )


def test_probeSelectedText_uses_execFileSync() -> None:
    """probeSelectedText must use execFileSync, not execSync (shell-injection safe)."""
    src = _src()
    # Locate the function body
    start = src.index("function probeSelectedText()")
    # Find the end by counting braces from the function start
    depth = 0
    end = start
    for i, ch in enumerate(src[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    fn_body = src[start:end + 1]
    assert "execFileSync" in fn_body, (
        "probeSelectedText() must use execFileSync (not execSync) — shell-injection safety"
    )
    assert "execSync(" not in fn_body, (
        "probeSelectedText() must not use bare execSync — use execFileSync instead"
    )


def test_probeSelectedText_probes_ax_and_chrome() -> None:
    """Must probe both AX (native apps) and Chrome JS selection."""
    src = _src()
    start = src.index("function probeSelectedText()")
    depth = 0
    end = start
    for i, ch in enumerate(src[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    fn_body = src[start:end + 1]
    assert "AXSelectedText" in fn_body, (
        "probeSelectedText() must probe AX selection attribute for native apps"
    )
    assert "Google Chrome" in fn_body, (
        "probeSelectedText() must probe Chrome JS selection as fallback"
    )
    assert "getSelection().toString()" in fn_body, (
        "probeSelectedText() must use window.getSelection().toString() for Chrome"
    )


def test_captureAndSend_calls_probeSelectedText() -> None:
    """captureAndSend() must call probeSelectedText() on each tick.

    The push path (tick → captureAndSend) is where #1425 is fixed.
    We verify probeSelectedText() is called INSIDE the captureAndSend
    body by checking it appears AFTER the function declaration and
    BEFORE the `return { ok: true }` that closes it.
    """
    src = _src()
    start = src.index("async function captureAndSend(")
    # Find the closing `return { ok: true }` which is the last statement
    end = src.index("return { ok: true };", start)
    fn_slice = src[start:end]
    assert "probeSelectedText()" in fn_slice, (
        "captureAndSend() must call probeSelectedText() — push path is patched in this function"
    )


def test_dedup_state_variable_exists() -> None:
    """lastInjectedSelection dedup variable must exist to avoid re-injecting unchanged selections."""
    src = _src()
    assert "lastInjectedSelection" in src, (
        "lastInjectedSelection dedup variable not found — same selection would be injected on every tick"
    )


def test_injection_uses_sendContent() -> None:
    """Selected text injection must use transport.sendContent (not sendFile)."""
    src = _src()
    assert "sendContent" in src, (
        "transport.sendContent not found — selection injection path missing"
    )
    # The injection context message must be a user-role turn
    assert "selected text" in src.lower(), (
        "Selection injection context string not found in vision-tools.ts"
    )


def test_injection_is_non_audio_turn() -> None:
    """sendContent must be called with turnComplete=false to avoid triggering audio."""
    src = _src()
    # Find the sendContent call — it's inside captureAndSend.
    # The argument list spans multiple lines; look for the closing `], false)`
    # which carries the turnComplete=false flag.
    assert "], false)" in src, (
        "sendContent call must end with '], false)' — second arg is turnComplete=false; "
        "without it the model generates an audio response on every frame tick"
    )


def test_selection_cleared_when_empty() -> None:
    """When probeSelectedText returns '', lastInjectedSelection must be reset."""
    src = _src()
    # The else branch should reset lastInjectedSelection to ''
    assert "lastInjectedSelection = ''" in src, (
        "lastInjectedSelection must be reset to '' when selection is empty — prevents stale dedup state"
    )


def main() -> int:
    tests = [
        test_probeSelectedText_function_exists,
        test_probeSelectedText_uses_execFileSync,
        test_probeSelectedText_probes_ax_and_chrome,
        test_captureAndSend_calls_probeSelectedText,
        test_dedup_state_variable_exists,
        test_injection_uses_sendContent,
        test_injection_is_non_audio_turn,
        test_selection_cleared_when_empty,
    ]
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            failures.append(f"{fn.__name__}: {e}")
            print(f"  ✗ {fn.__name__}: {e}")
    if failures:
        print(f"\n{len(failures)} failure(s).")
        return 1
    print("All vision-push-mode-selection-first tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
