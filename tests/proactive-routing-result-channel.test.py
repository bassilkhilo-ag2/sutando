#!/usr/bin/env python3
"""Tests for proactive_routing.py and result_channel_key.py.

Run: python3 tests/proactive-routing-result-channel.test.py
Exit code: 0 on pass, 1 on fail.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from proactive_routing import should_claim_proactive, BRIDGE_CHANNELS
from result_channel_key import (
    sanitize_key,
    result_filename,
    parse_result_filename,
    result_belongs_to,
    discord_voice_key,
    phone_call_key,
)

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
# proactive_routing.should_claim_proactive
# ============================================================

def write_activity(tmp_dir: Path, channel: str) -> Path:
    p = tmp_dir / "last-owner-activity.json"
    p.write_text(json.dumps({"ts": 1700000000, "channel": channel, "summary": "hi"}))
    return p


print("\n--- proactive_routing ---")

with tempfile.TemporaryDirectory() as _td:
    td = Path(_td)

    # file missing → discord default
    missing = td / "nonexistent.json"
    check("missing file → discord claims", should_claim_proactive(missing, "discord"))
    check("missing file → telegram does not claim", not should_claim_proactive(missing, "telegram"))

    # file is corrupt JSON
    corrupt = td / "corrupt.json"
    corrupt.write_text("{not valid json")
    check("corrupt JSON → discord claims", should_claim_proactive(corrupt, "discord"))
    check("corrupt JSON → telegram does not claim", not should_claim_proactive(corrupt, "telegram"))

    # file contains non-dict
    list_file = td / "list.json"
    list_file.write_text("[1, 2, 3]")
    check("non-dict JSON → discord claims", should_claim_proactive(list_file, "discord"))

    # no channel field
    no_channel = td / "no_channel.json"
    no_channel.write_text(json.dumps({"ts": 1700000000}))
    check("no channel field → discord claims", should_claim_proactive(no_channel, "discord"))
    check("no channel field → telegram does not claim", not should_claim_proactive(no_channel, "telegram"))

    # empty channel
    empty_ch = td / "empty_ch.json"
    empty_ch.write_text(json.dumps({"ts": 1700000000, "channel": ""}))
    check("empty channel → discord claims", should_claim_proactive(empty_ch, "discord"))

    # channel = integer (wrong type)
    int_ch = td / "int_ch.json"
    int_ch.write_text(json.dumps({"ts": 1700000000, "channel": 42}))
    check("non-string channel → discord claims", should_claim_proactive(int_ch, "discord"))

    # last channel = discord
    f = write_activity(td, "discord")
    check("last=discord, caller=discord → claims", should_claim_proactive(f, "discord"))
    check("last=discord, caller=telegram → does not claim", not should_claim_proactive(f, "telegram"))

    # last channel = telegram
    f = write_activity(td, "telegram")
    check("last=telegram, caller=telegram → claims", should_claim_proactive(f, "telegram"))
    check("last=telegram, caller=discord → does not claim", not should_claim_proactive(f, "discord"))

    # last channel = voice (non-bridge) → discord default
    f = write_activity(td, "voice")
    check("last=voice (non-bridge), caller=discord → claims (default)", should_claim_proactive(f, "discord"))
    check("last=voice (non-bridge), caller=telegram → does not claim", not should_claim_proactive(f, "telegram"))

    # last channel = github-commits (non-bridge) → discord default
    f = write_activity(td, "github-commits")
    check("last=github-commits, caller=discord → claims (default)", should_claim_proactive(f, "discord"))

    # last channel = slack (not in BRIDGE_CHANNELS today) → discord default
    f = write_activity(td, "slack")
    check("last=slack (not in BRIDGE_CHANNELS), caller=discord → claims", should_claim_proactive(f, "discord"))

    # verify BRIDGE_CHANNELS contains exactly discord and telegram
    check("BRIDGE_CHANNELS contains discord", "discord" in BRIDGE_CHANNELS)
    check("BRIDGE_CHANNELS contains telegram", "telegram" in BRIDGE_CHANNELS)
    check("BRIDGE_CHANNELS has exactly 2 entries", len(BRIDGE_CHANNELS) == 2)

    # unknown caller channel, last = discord
    f = write_activity(td, "discord")
    check("last=discord, caller=unknown → does not claim", not should_claim_proactive(f, "unknown"))


# ============================================================
# result_channel_key.sanitize_key
# ============================================================

print("\n--- result_channel_key.sanitize_key ---")

check("None → 'unknown'", sanitize_key(None) == "unknown")
check("empty string → 'unknown'", sanitize_key("") == "unknown")
check("whitespace only → 'unknown'", sanitize_key("   ") == "unknown")
check("normal alphanum preserved", sanitize_key("dvoice-12345") == "dvoice-12345")
check("slash collapsed to dash", sanitize_key("a/b") == "a-b")
check("dot collapsed to dash", sanitize_key("a.b") == "a-b")
check("space collapsed to dash", sanitize_key("my channel") == "my-channel")
check("underscore preserved", sanitize_key("my_key") == "my_key")
check("mixed special chars", sanitize_key("a!b@c#d$") == "a-b-c-d-")
check("leading/trailing spaces stripped", sanitize_key("  abc  ") == "abc")


# ============================================================
# result_channel_key.result_filename
# ============================================================

print("\n--- result_channel_key.result_filename ---")

check("basic filename", result_filename("dvoice-123", "task-456") == "dvoice-123.task-456.txt")
check("sanitizes key in filename", result_filename("a/b", "task-1") == "a-b.task-1.txt")
check("phone key filename", result_filename("phone-CA123", "task-999") == "phone-CA123.task-999.txt")


# ============================================================
# result_channel_key.parse_result_filename
# ============================================================

print("\n--- result_channel_key.parse_result_filename ---")

key, task_id = parse_result_filename("dvoice-123.task-456.txt")
check("scoped .txt → key parsed", key == "dvoice-123")
check("scoped .txt → task_id parsed", task_id == "task-456")

key, task_id = parse_result_filename("dvoice-123.task-456")
check("scoped no .txt → key parsed", key == "dvoice-123")
check("scoped no .txt → task_id parsed", task_id == "task-456")

key, task_id = parse_result_filename("task-789.txt")
check("flat task → key is None", key is None)
check("flat task → task_id is base name", task_id == "task-789")

key, task_id = parse_result_filename("proactive-1700000000.txt")
check("proactive file → key is None", key is None)

key, task_id = parse_result_filename("voice-1700000000.txt")
check("voice file → key is None", key is None)

# .sending files ARE parseable by parse_result_filename (it only strips .txt).
# Protection against atomic-write temps is in result_belongs_to (endswith .txt guard).
key, task_id = parse_result_filename("phone-CA123.task-456.txt.sending")
check(".sending suffix → key is parsed (belongs_to guards, not parse)", key == "phone-CA123")

# key containing only valid chars
key, task_id = parse_result_filename("my_key-123.task-abc.txt")
check("underscore in key preserved", key == "my_key-123")
check("task_id with letters parsed", task_id == "task-abc")


# ============================================================
# result_channel_key.result_belongs_to
# ============================================================

print("\n--- result_channel_key.result_belongs_to ---")

check("scoped file belongs to matching key", result_belongs_to("dvoice-123.task-456.txt", "dvoice-123"))
check("scoped file does not belong to different key", not result_belongs_to("dvoice-123.task-456.txt", "phone-CA9"))
check("flat task-*.txt does not belong to any channel", not result_belongs_to("task-456.txt", "dvoice-123"))
check("proactive file does not belong to channel", not result_belongs_to("proactive-1700000.txt", "dvoice-123"))
check("no .txt suffix → False", not result_belongs_to("dvoice-123.task-456", "dvoice-123"))
check(".sending suffix → False", not result_belongs_to("dvoice-123.task-456.txt.sending", "dvoice-123"))
check(".tmp suffix → False", not result_belongs_to("dvoice-123.task-456.txt.tmp", "dvoice-123"))
check("key sanitization applied in belongs_to", result_belongs_to("a-b.task-1.txt", "a/b"))

# task_id must start with task-
check("non-task_id scoped form → False",
      not result_belongs_to("dvoice-123.voice-456.txt", "dvoice-123"))


# ============================================================
# result_channel_key typed constructors
# ============================================================

print("\n--- typed key constructors ---")

check("discord_voice_key normal", discord_voice_key("987654321") == "dvoice-987654321")
check("discord_voice_key None → unknown sentinel", discord_voice_key(None) == "dvoice-unknown")
check("discord_voice_key sanitizes slash", discord_voice_key("a/b") == "dvoice-a-b")

check("phone_call_key normal", phone_call_key("CAabc123") == "phone-CAabc123")
check("phone_call_key None → unknown sentinel", phone_call_key(None) == "phone-unknown")
check("phone_call_key sanitizes dot", phone_call_key("CA.abc") == "phone-CA-abc")

# round-trip: key from constructor → result_filename → parse → belongs_to
vc_key = discord_voice_key("111222333")
fname = result_filename(vc_key, "task-555")
parsed_key, parsed_task = parse_result_filename(fname)
check("round-trip: discord_voice_key constructs parseable filename", parsed_key == vc_key)
check("round-trip: result_belongs_to with constructor key", result_belongs_to(fname, vc_key))

# ============================================================

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
