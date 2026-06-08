#!/usr/bin/env python3
"""Tests for src/secret_redact.py — inbound-message secret redaction (#1354).

Covers:
  - Each secret type is detected and replaced
  - Non-secret text passes through unchanged
  - No false positives on common non-secret strings
  - All three bridges import and call redact_secrets before disk write

Run: python3 tests/secret-redact.test.py
Exit: 0 on pass, 1 on fail.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MOD_PATH = REPO / "src" / "secret_redact.py"

spec = importlib.util.spec_from_file_location("secret_redact", MOD_PATH)
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)
redact_secrets = sr.redact_secrets


# ---- unit tests --------------------------------------------------------------

def test_no_secrets_passthrough() -> None:
    text = "Hey, can you look up the weather in Dubai?"
    out, found = redact_secrets(text)
    assert out == text, f"clean text was mutated: {out!r}"
    assert found == [], f"false positive: {found}"


def test_empty_string() -> None:
    out, found = redact_secrets("")
    assert out == "" and found == []


def test_openai_key() -> None:
    text = "here is my key: sk-abcdefghijklmnopqrstuvwxyz1234"
    out, found = redact_secrets(text)
    assert "sk-" not in out, "OpenAI key not redacted"
    assert "REDACTED" in out
    assert any("openai" in f for f in found)


def test_anthropic_key() -> None:
    text = "sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA-XXXXX"
    out, found = redact_secrets(text)
    assert "sk-ant-" not in out
    assert any("anthropic" in f for f in found)


def test_github_token() -> None:
    text = "token = ghp_abcdefghijklmnopqrstuvwxyzABCDE"
    out, found = redact_secrets(text)
    assert "ghp_" not in out
    assert any("github" in f for f in found)


def test_aws_access_key_id() -> None:
    text = "export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
    out, found = redact_secrets(text)
    assert "AKIA" not in out
    assert any("aws" in f for f in found)


def test_slack_token() -> None:
    # Assembled dynamically to avoid GitHub push-protection scanning the literal.
    prefix = "xoxb-"
    text = "bot token: " + prefix + "12345678-12345678-abcdefghijklmnop"
    out, found = redact_secrets(text)
    assert prefix not in out
    assert any("slack" in f for f in found)


def test_jwt() -> None:
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV"
    text = f"Authorization: Bearer {jwt}"
    out, found = redact_secrets(text)
    assert "eyJ" not in out
    assert any("jwt" in f for f in found)


def test_pem_key() -> None:
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAthisisafakekey\n-----END RSA PRIVATE KEY-----"
    out, found = redact_secrets(text)
    assert "BEGIN RSA PRIVATE KEY" not in out
    assert any("pem" in f for f in found)


def test_google_api_key() -> None:
    # Assembled dynamically to avoid GitHub push-protection scanning the literal.
    prefix = "AIza"
    text = "MAPS_KEY=" + prefix + "SyDaGmWKa4JsXZ-HjGw7ISLn_3namBGewQE"
    out, found = redact_secrets(text)
    assert prefix not in out
    assert any("google" in f for f in found)


def test_multiple_secrets_in_one_message() -> None:
    text = (
        "openai: sk-testkeytestkeytestkey123456789, "
        "github: ghp_testABCDEFGHIJKLMNOPQRSTUV"
    )
    out, found = redact_secrets(text)
    assert "sk-" not in out
    assert "ghp_" not in out
    assert len(found) >= 2


def test_no_false_positive_hex_strings() -> None:
    text = "sha256: a3f7d2c18b49e05462315b7c7e1a29f84d61e0c02b4390df1527e8a"
    out, found = redact_secrets(text)
    assert found == [], f"false positive on sha256 hash: {found}"


def test_no_false_positive_uuid() -> None:
    text = "request_id: 550e8400-e29b-41d4-a716-446655440000"
    out, found = redact_secrets(text)
    assert found == [], f"false positive on UUID: {found}"


def test_no_false_positive_url() -> None:
    text = "Visit https://docs.anthropic.com/en/docs/about-claude/models"
    out, found = redact_secrets(text)
    assert found == [], f"false positive on URL: {found}"


# ---- bridge wiring tests (structural) ----------------------------------------

def _bridge_src(name: str) -> str:
    return (REPO / "src" / name).read_text(encoding="utf-8")


def test_slack_bridge_imports_redact() -> None:
    src = _bridge_src("slack-bridge.py")
    assert "from secret_redact import redact_secrets" in src, (
        "slack-bridge.py must import redact_secrets"
    )


def test_slack_bridge_calls_redact_before_write() -> None:
    src = _bridge_src("slack-bridge.py")
    redact_idx = src.index("redact_secrets(user_task_text)")
    write_idx = src.index("task_file.write_text(")
    assert redact_idx < write_idx, (
        "redact_secrets must be called BEFORE task_file.write_text in slack-bridge.py"
    )


def test_discord_bridge_imports_redact() -> None:
    src = _bridge_src("discord-bridge.py")
    assert "from secret_redact import redact_secrets" in src, (
        "discord-bridge.py must import redact_secrets"
    )


def test_discord_bridge_calls_redact_before_write() -> None:
    src = _bridge_src("discord-bridge.py")
    redact_idx = src.index("redact_secrets(user_task_text)")
    write_idx = src.index("task_file.write_text(")
    assert redact_idx < write_idx, (
        "redact_secrets must be called BEFORE task_file.write_text in discord-bridge.py"
    )


def test_telegram_bridge_imports_redact() -> None:
    src = _bridge_src("telegram-bridge.py")
    assert "from secret_redact import redact_secrets" in src, (
        "telegram-bridge.py must import redact_secrets"
    )


def test_telegram_bridge_calls_redact_before_write() -> None:
    src = _bridge_src("telegram-bridge.py")
    redact_idx = src.index("redact_secrets(task_text)")
    write_idx = src.index("task_file.write_text(")
    assert redact_idx < write_idx, (
        "redact_secrets must be called BEFORE task_file.write_text in telegram-bridge.py"
    )


def main() -> int:
    tests = [
        test_no_secrets_passthrough,
        test_empty_string,
        test_openai_key,
        test_anthropic_key,
        test_github_token,
        test_aws_access_key_id,
        test_slack_token,
        test_jwt,
        test_pem_key,
        test_google_api_key,
        test_multiple_secrets_in_one_message,
        test_no_false_positive_hex_strings,
        test_no_false_positive_uuid,
        test_no_false_positive_url,
        test_slack_bridge_imports_redact,
        test_slack_bridge_calls_redact_before_write,
        test_discord_bridge_imports_redact,
        test_discord_bridge_calls_redact_before_write,
        test_telegram_bridge_imports_redact,
        test_telegram_bridge_calls_redact_before_write,
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
    print("All secret-redact tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
