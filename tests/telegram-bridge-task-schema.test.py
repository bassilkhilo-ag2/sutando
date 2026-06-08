#!/usr/bin/env python3
"""Structural regression test: telegram-bridge task file schema (#1381 item 1).

Pins that every task file written by the Telegram bridge includes the fields
required for access-control parity with the Discord and Slack bridges:
  - access_tier: owner  (agents gate on this; without it, access control is
                         undefined for Telegram tasks)
  - user_id: <sender>   (schema parity with discord/slack task files)
  - task: ...           (must appear AFTER the metadata fields, not before)

Does NOT test TOFU or the allowlist logic — those live in
telegram-bridge-access.test.py.  This is a static structural check on the
source that guards against accidental regression (e.g. dropping a field
during a merge conflict resolution).

Run: python3 tests/telegram-bridge-task-schema.test.py
Exit: 0 = pass, 1 = failure
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = (REPO / "src" / "telegram-bridge.py").read_text()

# Locate the task_file.write_text(...) block so assertions are anchored to the
# right section (not accidentally matched somewhere else in the file).
# The block spans multiple lines; find the closing "                )" that ends
# the call by looking for the indented lone ) after the opening.
_WRITE_START = SRC.index("task_file.write_text(")
# Find the standalone closing paren line: "                )\n"
_WRITE_END = SRC.index("\n                )\n", _WRITE_START)
WRITE_BLOCK = SRC[_WRITE_START:_WRITE_END + 20]


class TestTelegramTaskSchema(unittest.TestCase):

    def test_access_tier_owner_present(self):
        """access_tier: owner must be written to every Telegram task file."""
        self.assertIn(
            "access_tier: owner",
            WRITE_BLOCK,
            "telegram-bridge must write access_tier: owner — required for agent access control (#1381 item 1)",
        )

    def test_user_id_present(self):
        """user_id: <sender_id> must be written for schema parity."""
        self.assertRegex(
            WRITE_BLOCK,
            r"user_id.*sender_id",
            "telegram-bridge must write user_id: {sender_id} — schema parity with discord/slack task files",
        )

    def test_task_field_is_last(self):
        """task: must appear after all metadata fields (access_tier, user_id, source, chat_id)."""
        task_pos = WRITE_BLOCK.find('"task:')
        for field in ("access_tier", "user_id", "source", "chat_id", "priority"):
            field_pos = WRITE_BLOCK.find(field)
            self.assertGreater(
                task_pos,
                field_pos,
                f"task: field must come after {field} in the task file — metadata before payload",
            )

    def test_source_telegram_present(self):
        """source: telegram must be in the task file."""
        self.assertIn(
            "source: telegram",
            WRITE_BLOCK,
            "telegram-bridge must write source: telegram",
        )

    def test_chat_id_retained(self):
        """chat_id: must still be written — notify.py reads it for Telegram delivery."""
        self.assertIn(
            "chat_id:",
            WRITE_BLOCK,
            "telegram-bridge must keep chat_id: — task-progress/notify.py maps telegram → --chat-id",
        )


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False)
    sys.exit(0 if result.result.wasSuccessful() else 1)
