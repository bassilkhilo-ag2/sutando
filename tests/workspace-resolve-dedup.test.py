#!/usr/bin/env python3
"""Structural tests for workspace resolution deduplication (#1378).

obsidian-mirror.py and skills/screen-companion/tools.ts previously each
defined their own inline resolveWorkspace / resolve_workspace that duplicated
the canonical logic in src/workspace_default.{py,ts}. This test pins the
#1378 refactor that replaced both with imports from the canonical module.

Tests are structural (source-level) — no subprocess or import side-effects.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MIRROR = (REPO / "src" / "obsidian-mirror.py").read_text()
SCREEN = (REPO / "skills" / "screen-companion" / "tools.ts").read_text()

_PASS = []
_FAIL = []


def ok(name: str, cond: bool, msg: str = "") -> None:
    if cond:
        _PASS.append(name)
        print(f"  ✓ {name}")
    else:
        _FAIL.append(name)
        print(f"  ✗ {name}" + (f": {msg}" if msg else ""))


# ── obsidian-mirror.py ───────────────────────────────────────────────────────

ok(
    "obsidian-mirror: imports resolve_workspace from workspace_default",
    "from workspace_default import resolve_workspace" in MIRROR,
    "obsidian-mirror.py must import resolve_workspace from workspace_default, not define its own",
)

ok(
    "obsidian-mirror: no longer defines inline resolve_workspace",
    "def resolve_workspace()" not in MIRROR,
    "obsidian-mirror.py must not define its own resolve_workspace() — use the canonical import",
)

ok(
    "obsidian-mirror: sys.path insert for src/ present",
    "sys.path.insert(0, str(Path(__file__).parent))" in MIRROR,
    "obsidian-mirror.py must add src/ to sys.path so the workspace_default import resolves",
)

# ── skills/screen-companion/tools.ts ─────────────────────────────────────────

ok(
    "screen-companion: imports resolveWorkspace from workspace_default.js",
    "import { resolveWorkspace } from '../../src/workspace_default.js'" in SCREEN,
    "screen-companion/tools.ts must import resolveWorkspace from the canonical workspace_default.js",
)

ok(
    "screen-companion: no longer defines inline resolveWorkspace",
    "function resolveWorkspace()" not in SCREEN,
    "screen-companion/tools.ts must not define its own resolveWorkspace() — use the canonical import",
)

# ── summary ───────────────────────────────────────────────────────────────────

print(f"\nResults: {len(_PASS)} passed, {len(_FAIL)} failed")
if _FAIL:
    print("Failures:")
    for f in _FAIL:
        print(f"  - {f}")
    sys.exit(1)
