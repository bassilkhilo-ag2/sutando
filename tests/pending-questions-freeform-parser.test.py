#!/usr/bin/env python3
"""Structural tests for pending-questions.md free-form parser alignment (#1404).

Three consumers previously required **Status:** markers that the file never
has (free-form convention per #1265), causing them to undercount to 0:
- src/friction-detector.py  check_pending_questions()
- src/agent-api.py          pending-questions block (~L407)
- src/dashboard.py          get_pending_count()   ← already fixed pre-#1404

These tests pin the #1404 fixes: no-status sections are now treated as open,
resolved sections are excluded via the `# Resolved` divider, and the old
"**Status:** required" gate is gone from agent-api.py.

Tests are structural (source-level) to avoid import-time side-effects from
the three modules — consistent with the existing test-suite pattern.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FRICTION = (REPO / "src" / "friction-detector.py").read_text()
AGENT_API = (REPO / "src" / "agent-api.py").read_text()
DASHBOARD = (REPO / "src" / "dashboard.py").read_text()

_PASS = []
_FAIL = []


def ok(name: str, cond: bool, msg: str = "") -> None:
    if cond:
        _PASS.append(name)
        print(f"  ✓ {name}")
    else:
        _FAIL.append(name)
        print(f"  ✗ {name}" + (f": {msg}" if msg else ""))


# ── friction-detector.py ────────────────────────────────────────────────────

# flush() must fire when current_status is None (no **Status:** field)
ok(
    "friction-detector: flush fires on None status (not in resolved statuses)",
    "current_status not in _RESOLVED_STATUSES" in FRICTION,
    "flush() must check `current_status not in _RESOLVED_STATUSES` so free-form sections are counted",
)

ok(
    "friction-detector: _RESOLVED_STATUSES set defined",
    '_RESOLVED_STATUSES = {"resolved", "answered", "done", "complete"}' in FRICTION,
    "must define _RESOLVED_STATUSES to avoid hardcoded status strings in flush()",
)

ok(
    "friction-detector: strips # Resolved divider",
    "re.split(r'^#\\s+Resolved\\b'" in FRICTION or "_re.split(r'^#\\s+Resolved\\b'" in FRICTION,
    "must strip content at `# Resolved` divider so answered questions aren't re-counted",
)

ok(
    "friction-detector: no longer requires Status==unanswered",
    'current_status == "unanswered"' not in FRICTION,
    "old `current_status == 'unanswered'` gate must be removed — too strict for free-form file",
)

# ── agent-api.py ─────────────────────────────────────────────────────────────

ok(
    "agent-api: removes **Status:** required gate",
    ("'**Status:**' not in body and '**Options:**' not in body" not in AGENT_API
     and "\"**Status:**\" not in body and \"**Options:**\" not in body" not in AGENT_API),
    "agent-api must not skip sections that lack **Status:** — free-form sections are open by default",
)

ok(
    "agent-api: still skips resolved/answered via regex",
    "resolved|answered|done|complete" in AGENT_API,
    "agent-api must still skip sections whose **Status:** matches resolved/answered/done/complete",
)

ok(
    "agent-api: strips # Resolved divider",
    "re.split(r'^#\\s+Resolved\\b'" in AGENT_API,
    "agent-api must strip content at `# Resolved` divider before parsing sections",
)

# ── dashboard.py ─────────────────────────────────────────────────────────────

ok(
    "dashboard: counts ## sections (not **Status:** Waiting)",
    "re.findall(r'^## '" in DASHBOARD or "re.findall(r'^## '," in DASHBOARD,
    "dashboard get_pending_count() must count ## sections, not require **Status:** field",
)

ok(
    "dashboard: honors # Resolved divider via partition",
    "partition('\\n# Resolved')" in DASHBOARD,
    "dashboard must strip resolved section via partition before counting",
)

ok(
    "dashboard: no longer uses Status.*Waiting regex",
    # The old regex `r'\*\*Status:\*\* Waiting'` was removed. The string may
    # still appear in a comment; check for the actual regex pattern instead.
    r"re.findall(r'\*\*Status:\*\* Waiting'" not in DASHBOARD
    and "re.findall(r'\\*\\*Status:\\*\\* Waiting'" not in DASHBOARD,
    "dashboard must not use old **Status:** Waiting regex — that always matched 0",
)

# ── summary ──────────────────────────────────────────────────────────────────

print(f"\nResults: {len(_PASS)} passed, {len(_FAIL)} failed")
if _FAIL:
    print("Failures:")
    for f in _FAIL:
        print(f"  - {f}")
    sys.exit(1)
