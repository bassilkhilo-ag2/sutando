#!/usr/bin/env python3
"""Tests for pure-logic functions in src/morning-briefing.py.

Covers functions that don't require AppleScript, network, or subprocess:
  - synthesize()            (text assembly — fully pure)
  - get_pending_questions() (file parsing — tested with tempfiles)

Run: python3 tests/morning-briefing-pure.test.py
Exit code: 0 on pass, 1 on fail.
"""

import importlib.util
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ.setdefault("SUTANDO_WORKSPACE", "/tmp/morning-briefing-test-ws")

spec = importlib.util.spec_from_file_location(
    "morning_briefing",
    Path(__file__).resolve().parent.parent / "src" / "morning-briefing.py",
)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)

synthesize = _mod.synthesize

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


def _synth(hour: int, **kwargs) -> str:
    """Call synthesize() with a mocked datetime hour."""
    mock_dt = MagicMock()
    mock_dt.now.return_value.hour = hour
    with patch.object(_mod, "datetime", mock_dt):
        return synthesize(
            kwargs.get("weather", ""),
            kwargs.get("events", []),
            kwargs.get("reminders", []),
            kwargs.get("discord_msgs", []),
            kwargs.get("pending_qs", []),
            kwargs.get("health_issues", []),
            kwargs.get("insight", None),
        )


# ============================================================
# synthesize — greeting
# ============================================================

print("\n--- synthesize: greeting ---")

check("hour=6 → Good morning", _synth(6).startswith("Good morning."))
check("hour=11 → Good morning", _synth(11).startswith("Good morning."))
check("hour=12 → Good afternoon", _synth(12).startswith("Good afternoon."))
check("hour=16 → Good afternoon", _synth(16).startswith("Good afternoon."))
check("hour=17 → Good evening", _synth(17).startswith("Good evening."))
check("hour=23 → Good evening", _synth(23).startswith("Good evening."))


# ============================================================
# synthesize — weather
# ============================================================

print("\n--- synthesize: weather ---")

check("weather present → 'It's X.'",
      "It's partly cloudy." in _synth(9, weather="partly cloudy"))
check("empty weather → not mentioned",
      "It's" not in _synth(9, weather=""))
check("None weather → not mentioned",
      "It's" not in _synth(9, weather=None))


# ============================================================
# synthesize — calendar events
# ============================================================

print("\n--- synthesize: calendar events ---")

check("no events → 'Your calendar is clear today.'",
      "Your calendar is clear today." in _synth(9))

check("1 event → 'One meeting today: X.'",
      "One meeting today: 10:00am Standup." in _synth(
          9, events=[{"raw": "10:00am Standup", "calendar": "Work"}]))

check("2 events → 'N meetings today. First up: X.'",
      "2 meetings today. First up: 9:00am Sync." in _synth(
          9, events=[
              {"raw": "9:00am Sync", "calendar": "Work"},
              {"raw": "11:00am Review", "calendar": "Work"},
          ]))

check("3 events → count is 3",
      "3 meetings today." in _synth(
          9, events=[
              {"raw": "9:00am A", "calendar": "Work"},
              {"raw": "10:00am B", "calendar": "Work"},
              {"raw": "11:00am C", "calendar": "Work"},
          ]))

# First event is shown in multi-event case
check("multi events → first event title shown",
      "First up: 8:00am Earlybird." in _synth(
          9, events=[
              {"raw": "8:00am Earlybird", "calendar": "Work"},
              {"raw": "9:00am Latebird", "calendar": "Work"},
          ]))


# ============================================================
# synthesize — reminders
# ============================================================

print("\n--- synthesize: reminders ---")

check("no reminders → not mentioned",
      "Reminders" not in _synth(9))

check("1 reminder → listed",
      "Reminders due: Buy milk." in _synth(9, reminders=["Buy milk"]))

check("3 reminders → all listed",
      "Reminders due: A, B, C." in _synth(9, reminders=["A", "B", "C"]))

check("4 reminders → only first 3 shown",
      "D" not in _synth(9, reminders=["A", "B", "C", "D"]))

check("2 reminders → joined with comma-space",
      "Reminders due: X, Y." in _synth(9, reminders=["X", "Y"]))


# ============================================================
# synthesize — pending questions
# ============================================================

print("\n--- synthesize: pending questions ---")

check("no pending qs → not mentioned",
      "pending question" not in _synth(9))

check("1 pending q → 'One pending question waiting: X.'",
      "One pending question waiting: What to do?" in _synth(
          9, pending_qs=["What to do?"]))

check("2 pending qs → 'N pending questions. Top item: X.'",
      "2 pending questions. Top item: First." in _synth(
          9, pending_qs=["First", "Second"]))

check("3 pending qs → count is 3",
      "3 pending questions." in _synth(
          9, pending_qs=["A", "B", "C"]))

check("multi pending qs → top item is first",
      "Top item: Alpha." in _synth(9, pending_qs=["Alpha", "Beta"]))


# ============================================================
# synthesize — discord messages
# ============================================================

print("\n--- synthesize: discord messages ---")

check("no discord → not mentioned",
      "Discord" not in _synth(9))

check("1 discord msg → singular 'message'",
      "1 Discord message." in _synth(9, discord_msgs=["msg1"]))

check("2 discord msgs → plural 'messages'",
      "2 Discord messages." in _synth(9, discord_msgs=["msg1", "msg2"]))

check("5 discord msgs → count correct",
      "5 Discord messages." in _synth(9, discord_msgs=["a", "b", "c", "d", "e"]))


# ============================================================
# synthesize — health issues
# ============================================================

print("\n--- synthesize: health issues ---")

check("no health issues → not mentioned",
      "System note" not in _synth(9))

check("1 health issue → 'System note: X.'",
      "System note: disk full." in _synth(9, health_issues=["disk full"]))

check("2 health issues → joined with semicolon",
      "System note: issue A; issue B." in _synth(
          9, health_issues=["issue A", "issue B"]))

check("3 health issues → only first 2 shown",
      "issue C" not in _synth(9, health_issues=["issue A", "issue B", "issue C"]))


# ============================================================
# synthesize — insight
# ============================================================

print("\n--- synthesize: insight ---")

check("no insight → not mentioned",
      "Insight" not in _synth(9))

check("valid insight → 'Insight: first sentence.'",
      "Insight: The team shipped" in _synth(
          9, insight="The team shipped three features. Also a bug fix."))

check("insight with raw data ('{') → skipped",
      "Insight" not in _synth(
          9, insight="{tasks: 5, completed: 3}. Good day."))

check("insight with many colons (> 2) → skipped",
      "Insight" not in _synth(
          9, insight="key: val: another: extra"))

check("insight first sentence too short (≤20 chars) → skipped",
      "Insight" not in _synth(9, insight="Short. More text here."))

check("insight first sentence long enough (> 20 chars) → included",
      "Insight" in _synth(
          9, insight="This is a long enough insight sentence. Extra."))

check("insight: only first sentence used (stops at first dot)",
      "Also a bug fix" not in _synth(
          9, insight="The team shipped three features. Also a bug fix."))


# ============================================================
# synthesize — clean-slate closing
# ============================================================

print("\n--- synthesize: clean closing ---")

check("all empty → closing message",
      "Everything looks clean." in _synth(9))

check("has events → no closing message",
      "Everything looks clean." not in _synth(
          9, events=[{"raw": "9:00am Meeting", "calendar": "Work"}]))

check("has reminders → no closing message",
      "Everything looks clean." not in _synth(9, reminders=["task"]))

check("has pending qs → no closing message",
      "Everything looks clean." not in _synth(9, pending_qs=["question?"]))

check("has health issues → no closing message",
      "Everything looks clean." not in _synth(9, health_issues=["warn"]))

# discord alone does NOT suppress the closing message (discord is cosmetic,
# not an actionable item checked by the condition)
check("discord only → closing still shown",
      "Everything looks clean." in _synth(9, discord_msgs=["msg"]))


# ============================================================
# get_pending_questions — file parsing
# ============================================================

print("\n--- get_pending_questions ---")

with tempfile.TemporaryDirectory() as _td:
    ws = Path(_td)
    # Patch WORKSPACE on the module so it reads from our temp dir
    orig_ws = _mod.WORKSPACE
    _mod.WORKSPACE = ws

    # missing file → []
    check("missing file → []", _mod.get_pending_questions() == [])

    pq = ws / "pending-questions.md"

    # empty file → []
    pq.write_text("# Pending Questions\n")
    check("empty (header only) → []", _mod.get_pending_questions() == [])

    # one question
    pq.write_text("# Pending Questions\n\n## Should we refactor auth?\n\nSome detail.\n")
    result = _mod.get_pending_questions()
    check("1 question → 1 item", len(result) == 1)
    check("1 question → title extracted", result[0] == "Should we refactor auth?")

    # two questions
    pq.write_text(
        "# Pending Questions\n\n"
        "## First question\n\n"
        "## Second question\n\n"
    )
    result = _mod.get_pending_questions()
    check("2 questions → 2 items", len(result) == 2)
    check("order preserved (first is first)", result[0] == "First question")
    check("order preserved (second is second)", result[1] == "Second question")

    # date-prefix stripping: "[2026-05-27] Title here"
    pq.write_text("# Pending Questions\n\n## [2026-05-27] Title here\n\n")
    result = _mod.get_pending_questions()
    check("date prefix stripped", result == ["Title here"])

    # date prefix with different year/format
    pq.write_text("# Pending Questions\n\n## [2025-12-31] Year end review\n\n")
    result = _mod.get_pending_questions()
    check("date prefix stripped (different date)", result == ["Year end review"])

    # titles truncated to 60 chars
    long_title = "A" * 80
    pq.write_text(f"# Pending Questions\n\n## {long_title}\n\n")
    result = _mod.get_pending_questions()
    check("title truncated to 60 chars", len(result[0]) == 60)

    # Resolved section is excluded
    pq.write_text(
        "# Pending Questions\n\n"
        "## Active question\n\n"
        "# Resolved\n\n"
        "## Old resolved question\n\n"
    )
    result = _mod.get_pending_questions()
    check("resolved section excluded", len(result) == 1)
    check("active question preserved", result[0] == "Active question")
    check("resolved question excluded", "Old resolved question" not in result)

    # Questions after resolved divider are ignored even with multiple questions
    pq.write_text(
        "# Pending Questions\n\n"
        "## Q1\n\n## Q2\n\n"
        "# Resolved\n\n"
        "## R1\n\n## R2\n\n"
    )
    result = _mod.get_pending_questions()
    check("multiple active, multiple resolved — only active returned", result == ["Q1", "Q2"])

    _mod.WORKSPACE = orig_ws


# ============================================================

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
